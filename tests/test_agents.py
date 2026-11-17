"""P11 steps 3+4: REINFORCE with a learned baseline for F0-R1 and Dueling Double DQN with
prioritized replay and n-step returns for F1-R1 (src/ub_rl/agents.py), per docs/p11_plan.md
section 1. Toy runs only: tiny networks, a few hundred calls, contexts drawn from train.csv - no
V, no test file, no results. The learning smoke test is explicitly NOT a result and tunes nothing;
the agents never read env.calls or info["calls"].
"""
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from ub_rl import agents, baselines, envs, harness, splits
from ub_rl.baselines import CountingChecker
from ub_rl.checker import Checker
from ub_rl.envs import F0Env, F1Env, F2Env

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def kc(C):
    return CountingChecker(Checker(C))


def _train_ctxs(n):
    return splits.load_split("train", root=ROOT / "data" / "splits")[1][:n]


def _cfg(seed=3, budget=60, batch=8, hidden=(8, 8), lr=0.01, eval_contexts=None, **over):
    d = {"entry": "f0_r1", "seed": seed, "budget": budget, "checkpoints": [10],
         "budget_includes_eval": False, "eval_contexts": eval_contexts,
         "network": {"hidden": list(hidden), "lr": lr},
         "f0": {"batch_size": batch, "normalize_advantage": False}}
    d.update(over)
    return harness.RunConfig.from_dict(d)


def _agent(cfg, kc):
    return agents.make_f0_agent(cfg, F0Env(kc))


# ------------------------------------------------------------------ registration and interface
def test_f0_agent_registered_and_follows_the_contract(kc):
    assert "f0_r1" in harness.AGENTS
    agent = _agent(_cfg(), kc)
    env = F0Env(kc)
    ctx = _train_ctxs(1)[0]
    env.reset(ctx)
    a = agent.act(env)
    assert 0 <= a <= 90
    obs, r, done, info = env.step(a)
    assert done and info["feasible"] in (True, False)
    assert agent.observe(obs, a, r, done, info) is None
    assert agent.update() is None  # the batch is not full yet
    assert 0 <= agent.greedy_act(env) <= 90
    state = agent.checkpoint_state()
    assert set(state) == {"policy", "value", "optimizer", "rng", "batch"}


# ------------------------------------------------------------------ determinism through harness.run
def test_same_seed_identical_greedy_outputs_and_call_sequence(tmp_path, kc):
    """The P11 acceptance line: two runs with the same seed reproduce the greedy outputs and the
    episode/call sequence (the agent samples with its own seeded generator, never the global RNG)."""
    ctxs = _train_ctxs(4)
    cfg = _cfg(seed=3, budget=24, batch=8, checkpoints=[8, 16], eval_contexts=ctxs)
    harness.run(cfg, _agent(cfg, kc), kc, tmp_path / "a")
    harness.run(cfg, _agent(cfg, kc), kc, tmp_path / "b")
    for th in (8, 16):
        ev_a = (tmp_path / "a" / f"eval_{th}.csv").read_text()
        ev_b = (tmp_path / "b" / f"eval_{th}.csv").read_text()
        assert ev_a == ev_b
        assert len(ev_a.splitlines()) == 5  # header + 4 contexts
    episodes = lambda p: [l for l in (tmp_path / p / "run.jsonl").read_text().splitlines()
                          if json.loads(l)["event"] == "episode"]
    assert episodes("a") == episodes("b")  # same rewards, calls and ctx indices per episode


def test_budget_stops_exactly(tmp_path, kc):
    cfg = _cfg(budget=37, checkpoints=())
    summary = harness.run(cfg, _agent(cfg, kc), kc, tmp_path)
    assert summary["training_calls"] == 37 and summary["n_episodes"] == 37


def test_greedy_output_is_a_valid_section_index(tmp_path, kc):
    cfg = _cfg(budget=20, checkpoints=[10], eval_contexts=_train_ctxs(4))
    harness.run(cfg, _agent(cfg, kc), kc, tmp_path)
    rows = (tmp_path / "eval_10.csv").read_text().splitlines()[1:]
    assert len(rows) == 4
    assert all(0 <= int(r.split(",")[1]) <= 90 for r in rows)


# ------------------------------------------------------------------ the finite-value guard
def test_finite_guard_fires_on_poisoned_logits(kc):
    agent = _agent(_cfg(batch=2), kc)
    env = F0Env(kc)
    ctx = _train_ctxs(1)[0]
    for _ in range(2):  # a full batch (each F0 episode is one step, so reset per sample)
        env.reset(ctx)
        a = agent.act(env)
        obs, r, done, info = env.step(a)
        agent.observe(obs, a, r, done, info)
    with torch.no_grad():
        agent.policy.net[-1].weight[0, :] = float("nan")
    with pytest.raises(RuntimeError, match="non-finite"):
        agent.update()


# ------------------------------------------------------------------ checkpoint round trip
def test_checkpoint_roundtrip_restores_behaviour(kc):
    """checkpoint_state -> a fresh agent's load_state: the next greedy output and the next sampled
    action are identical (networks, optimizer, the sampling RNG and the batch buffer restored)."""
    cfg = _cfg(batch=4)
    ctx = _train_ctxs(1)[0]
    env_a = F0Env(kc)
    agent_a = _agent(cfg, kc)
    for _ in range(2):  # two transitions into the batch buffer (one step per episode)
        env_a.reset(ctx)
        a = agent_a.act(env_a)
        obs, r, done, info = env_a.step(a)
        agent_a.observe(obs, a, r, done, info)
    state = agent_a.checkpoint_state()

    agent_b = _agent(cfg, kc)
    assert agent_b.checkpoint_state()["batch"] != state["batch"]  # actually differs before loading
    agent_b.load_state(state)
    env_b = F0Env(kc)
    env_b.reset(ctx)
    env_a.reset(ctx)
    assert agent_b.greedy_act(env_b) == agent_a.greedy_act(env_a)
    env_b.reset(ctx)
    env_a.reset(ctx)
    assert agent_b.act(env_b) == agent_a.act(env_a)  # the restored generator draws the same action
    for b in agent_b.checkpoint_state()["batch"]:  # the buffer survived too
        assert any(torch.equal(b[0], o) and b[1] == a and b[2] == r
                   for o, a, r in state["batch"])


# ------------------------------------------------------------------ learning smoke (not a result)
def test_expected_return_improves_after_training(kc, C):
    """A learning smoke test, explicitly NOT a result: on one fixed train.csv context the policy's
    exact expected R1 return E_pi[R] = sum_i p_i R_i rises over ~300 sampled transitions, and the
    baseline's all-section MSE falls. The 91 exact returns come from a separate fresh
    CountingChecker, so no call touches the training budget. If this fails, the printed numbers
    flag a possible sign or logic bug in agents.py - never tuned to pass."""
    ctx = _train_ctxs(1)[0]
    fresh = CountingChecker(Checker(C))  # separate counter: the training budget is untouched
    fe = fresh.evaluate_context(ctx)["feasible"]
    t = baselines.trial_index(fresh, ctx)  # no checker call
    rets = np.asarray([envs.r1_log_return(float(fresh.mass[i]), float(fresh.mass[t]),
                                           float(fresh.mass[-1]), bool(fe[i]), 0)
                       for i in range(len(fresh))])
    cfg = _cfg(seed=0, budget=1000, batch=16, hidden=(8, 8), lr=0.05)
    env = F0Env(kc)
    agent = _agent(cfg, kc)

    def metrics():
        obs = torch.as_tensor(np.asarray(env.obs(), dtype=np.float32))
        probs = torch.softmax(agent.policy(obs), -1).detach().numpy()
        value = float(agent.value(obs).item())
        return float(probs @ rets), float(np.mean((value - rets) ** 2))

    env.reset(ctx)
    e_before, b_before = metrics()
    for _ in range(300):  # ~300 sampled transitions (one checker call each, on the toy kc)
        env.reset(ctx)
        a = agent.act(env)
        obs, r, done, info = env.step(a)
        agent.observe(obs, a, r, done, info)
        agent.update()
    e_after, b_after = metrics()
    print(f"expected return: {e_before:.6f} -> {e_after:.6f}; "
          f"baseline MSE: {b_before:.6f} -> {b_after:.6f}")
    assert e_after > e_before
    assert b_after < b_before


# ================================================================== F1: Dueling Double DQN
def _cfg_f1(seed=3, budget=60, **over):
    d = {"entry": "f1_r1", "seed": seed, "budget": budget, "checkpoints": [10],
         "budget_includes_eval": False, "eval_contexts": None,
         "network": {"hidden": [8, 8], "lr": 0.01},
         "f1": {"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                "batch_size": 8, "replay_size": 64, "target_sync": 10}}
    d.update(over)
    return harness.RunConfig.from_dict(d)


def _agent_f1(cfg, kc):
    return agents.make_f1_agent(cfg, F1Env(kc))


def test_f1_agent_registered_and_follows_the_contract(kc):
    assert "f1_r1" in harness.AGENTS
    cfg = _cfg_f1()
    agent = _agent_f1(cfg, kc)
    env = F1Env(kc)
    env.reset(_train_ctxs(1)[0])
    a = agent.act(env)  # a string action
    assert a in agents.F1_ACTIONS
    obs, r, done, info = env.step(a)
    assert agent.observe(obs, a, r, done, info) is None
    assert agent.update() is None  # the replay is below batch_size
    assert agent.greedy_act(env) in agents.F1_ACTIONS
    state = agent.checkpoint_state()
    assert set(state) >= {"online", "target", "optimizer", "torch_rng", "np_rng", "replay",
                          "builder", "steps", "last_obs"}


def test_dueling_q_mean_equals_value():
    """The dueling aggregation: mean over actions of Q equals V exactly."""
    torch.manual_seed(0)
    net = agents.DuelingNet(22, [8], 5)
    x = torch.randn(7, 22)
    q = net(x)
    v = net.value_of(x)
    assert torch.allclose(q.mean(dim=-1), v.squeeze(-1), atol=1e-6)


def test_f1_double_dqn_target_uses_online_argmax_and_target_value():
    """A fabricated case where the online net's argmax (action 1) differs from the target net's
    (action 0): the bootstrap uses the target net's value at the ONLINE net's action; a terminal
    window gets no bootstrap."""
    def make(bias):
        net = agents.DuelingNet(22, [], 5)  # no hidden layer: direct linear (fabricated)
        with torch.no_grad():
            net.value.weight.zero_()
            net.value.bias.zero_()
            net.advantage.weight.zero_()
            net.advantage.bias.copy_(torch.tensor(bias))
        return net

    online = make([0.0, 5.0, 0.0, 0.0, 0.0])  # Q: [-1, 4, -1, -1, -1] -> argmax action 1
    target = make([9.0, 1.0, 0.0, 0.0, 0.0])  # Q: [7, -1, -2, -2, -2] -> argmax action 0
    x = torch.zeros(2, 22)
    rets = torch.tensor([0.5, 0.25])
    term = torch.tensor([False, True])
    t = agents.double_dqn_target(online, target, x, rets, x, term, gamma_n=0.5)
    assert t[0] == pytest.approx(0.5 + 0.5 * (-1.0), abs=1e-6)  # online picks 1, target gives -1
    assert t[1] == pytest.approx(0.25, abs=1e-6)  # terminal: no bootstrap


def test_f1_learning_direction_without_checker_calls(kc):
    """No checker calls: a synthetic replay of terminal transitions with a known return (the n-step
    target is the return itself). After ~200 gradient steps Q(s, a) is closer to the target than
    before - a sign check, explicitly NOT a result."""
    cfg = _cfg_f1(seed=0, network={"hidden": [8, 8], "lr": 0.02},
                  f1={"n": 1, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                      "batch_size": 32, "replay_size": 64, "target_sync": 1000})
    agent = _agent_f1(cfg, kc)
    obs = np.zeros((32, 22), dtype=np.float32)
    for i in range(32):
        obs[i, i % 22] = 1.0
    for i in range(32):
        agent.replay.add((obs[i], i % 5, 1.0, obs[i], True), 1.0)
    before = float(agent.online(torch.as_tensor(obs[0]))[0])
    for _ in range(200):
        assert agent.update() is not None
    after = float(agent.online(torch.as_tensor(obs[0]))[0])
    print(f"Q(s0, a0): {before:.4f} -> {after:.4f} (target 1.0)")
    assert abs(after - 1.0) < abs(before - 1.0)


def test_f1_greedy_picks_the_argmax_q(kc):
    cfg = _cfg_f1()
    agent = _agent_f1(cfg, kc)
    net = agents.DuelingNet(22, [], 5)
    with torch.no_grad():
        net.value.weight.zero_()
        net.value.bias.zero_()
        net.advantage.weight.zero_()
        net.advantage.bias.copy_(torch.tensor([0.0, 0.0, 5.0, 0.0, 0.0]))
    agent.online = net
    env = F1Env(kc)
    env.reset(_train_ctxs(1)[0])
    assert agent.greedy_act(env) == "deeper"  # action 2 has the max Q


def test_f1_finite_guard_fires_on_poisoned_weights(kc):
    cfg = _cfg_f1(f1={"n": 1, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                      "batch_size": 4, "replay_size": 8, "target_sync": 10})
    agent = _agent_f1(cfg, kc)
    obs = np.zeros((4, 22), dtype=np.float32)
    for i in range(4):
        obs[i, i] = 1.0
        agent.replay.add((obs[i], 0, 1.0, obs[i], True), 1.0)
    with torch.no_grad():
        agent.online.advantage.weight[0, :] = float("nan")
    with pytest.raises(RuntimeError, match="non-finite"):
        agent.update()


def test_f1_same_seed_identical_greedy_outputs_and_call_sequence(tmp_path, kc):
    """The P11 acceptance line for F1: two runs with the same seed reproduce the greedy outputs and
    the episode/call sequence (epsilon and replay sampling use the seeded numpy Generator)."""
    ctxs = _train_ctxs(4)
    cfg = _cfg_f1(seed=3, budget=40, checkpoints=[10, 20], eval_contexts=ctxs)
    harness.run(cfg, _agent_f1(cfg, kc), kc, tmp_path / "a")
    harness.run(cfg, _agent_f1(cfg, kc), kc, tmp_path / "b")
    for th in (10, 20):
        ev_a = (tmp_path / "a" / f"eval_{th}.csv").read_text()
        ev_b = (tmp_path / "b" / f"eval_{th}.csv").read_text()
        assert ev_a == ev_b
        assert len(ev_a.splitlines()) == 5  # header + 4 contexts
    episodes = lambda p: [l for l in (tmp_path / p / "run.jsonl").read_text().splitlines()
                          if json.loads(l)["event"] == "episode"]
    assert episodes("a") == episodes("b")


def test_f1_budget_stops_exactly(tmp_path, kc):
    cfg = _cfg_f1(budget=37, checkpoints=())
    summary = harness.run(cfg, _agent_f1(cfg, kc), kc, tmp_path)
    assert summary["training_calls"] == 37


def test_f1_checkpoint_roundtrip_restores_behaviour(kc):
    """checkpoint_state -> a fresh agent's load_state: the next greedy action, the next sampled
    action AND the next replay sample are identical (networks, optimizer, torch and numpy RNG
    states, the full replay incl. sum-tree priorities, the n-step window and the counters)."""
    cfg = _cfg_f1(seed=3, f1={"n": 3, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6,
                              "beta_anneal_steps": 100, "batch_size": 4, "replay_size": 32,
                              "target_sync": 10})
    ctx = _train_ctxs(1)[0]
    env_a = F1Env(kc)
    agent_a = _agent_f1(cfg, kc)
    guard = 0
    while len(agent_a.replay) < 4 and guard < 10:  # terminal flushes fill the replay
        env_a.reset(ctx)
        done = False
        while not done:
            a = agent_a.act(env_a)
            obs, r, done, info = env_a.step(a)
            agent_a.observe(obs, a, r, done, info)
            agent_a.update()
        guard += 1
    assert len(agent_a.replay) >= 4
    state = agent_a.checkpoint_state()

    agent_b = _agent_f1(cfg, kc)
    agent_b.load_state(state)
    env_a.reset(ctx)
    env_b = F1Env(kc)
    env_b.reset(ctx)
    assert agent_b.greedy_act(env_b) == agent_a.greedy_act(env_a)
    assert agent_b.act(env_b) == agent_a.act(env_a)
    slots_a, batch_a, w_a = agent_a.replay.sample(4, 0.5)
    slots_b, batch_b, w_b = agent_b.replay.sample(4, 0.5)
    assert np.array_equal(slots_a, slots_b)
    assert np.array_equal(w_a, w_b)
    assert np.array_equal(batch_a[0], batch_b[0]) and np.array_equal(batch_a[1], batch_b[1])
    assert np.array_equal(batch_a[2], batch_b[2]) and np.array_equal(batch_a[4], batch_b[4])


# ================================================================== F2: conditional GFlowNet
def _cfg_f2(seed=3, budget=60, **over):
    d = {"entry": "f2_r3", "seed": seed, "budget": budget, "checkpoints": [10],
         "budget_includes_eval": False, "eval_contexts": None,
         "network": {"hidden": [8, 8], "lr": 0.01},
         "f2": {"beta": 50, "batch_size": 8, "logz_lr": 0.01}}
    d.update(over)
    return harness.RunConfig.from_dict(d)


def _agent_f2(cfg, kc):
    return agents.make_f2_agent(cfg, F2Env(kc))


def test_f2_agent_registered_and_follows_the_contract(kc):
    assert "f2_r3" in harness.AGENTS
    cfg = _cfg_f2()
    env = F2Env(kc)
    agent = agents.make_f2_agent(cfg, env)
    env.reset(_train_ctxs(1)[0])
    k, j = agent.act(env)
    assert 0 <= k < len(env.series)
    assert 0 <= j < len(env.variants[env.series[k]])
    obs, r, done, info = env.step(k, j, cfg.extra["f2"]["beta"])
    assert done
    assert agent.observe(obs, (k, j), r, done, info) is None
    assert agent.update() is None  # the batch is not full yet
    gk, gj = agent.greedy_act(env)
    assert 0 <= gk < len(env.series) and 0 <= gj < len(env.variants[env.series[gk]])
    state = agent.checkpoint_state()
    assert set(state) >= {"net", "optimizer", "logz_optimizer", "rng", "batch"}


def test_f2_joint_probs_lockstep_with_the_env_mapping(kc):
    """The masked-head lockstep: joint_probs sums to 1; a section's joint equals P(series) *
    P(variant | series) exactly as F2Env.series/variants map it; a variant outside the chosen
    series has zero probability under the masked head."""
    env = F2Env(kc)
    agent = _agent_f2(_cfg_f2(seed=1), kc)
    env.reset(_train_ctxs(1)[0])
    obs = env.obs()
    joint = agent.joint_probs(obs)
    assert abs(float(joint.sum()) - 1.0) < 1e-6
    with torch.no_grad():
        s_logits, v_logits, _ = agent.net(torch.as_tensor(np.asarray(obs, dtype=np.float32)))
    p_s = torch.softmax(s_logits, dim=-1).detach().numpy()
    for k, s in enumerate(env.series):
        idx = env.variants[s]
        sub = torch.softmax(v_logits.index_select(0, torch.as_tensor(idx, dtype=torch.long)),
                            dim=-1).detach().numpy()
        for pos, i in enumerate(idx):
            assert joint[i] == pytest.approx(p_s[k] * sub[pos], abs=1e-6)
        mask = torch.full((env.n,), float("-inf"))
        mask[torch.as_tensor(idx, dtype=torch.long)] = v_logits[idx]
        full = torch.softmax(mask, dim=-1).numpy()
        outside = [i for i in range(env.n) if i not in idx]
        assert np.all(full[outside] == 0.0)  # masked to zero outside the series


def test_f2_tb_loss_is_zero_at_the_analytic_solution(kc):
    """The trajectory-balance loss is ~0 (1e-9) at the exact solution: policy = softmax(log R) over
    the 91 sections (hierarchically: P(series) = sum of p* over the series, P(variant|series) =
    p*/sum over the series), logZ = logsumexp(log R). Fabricated network: linear heads with the
    exact logits as biases."""
    env = F2Env(kc)
    cfg = _cfg_f2(f2={"beta": 50, "batch_size": 16, "logz_lr": 0.01})
    agent = agents.make_f2_agent(cfg, env)
    log_r = -0.05 * np.arange(91) + 0.2 * np.sin(np.arange(91))  # a fabricated log R
    log_z_star = float(np.log(np.exp(log_r).sum()))
    log_p_star = log_r - log_z_star
    s_logits = np.array([float(np.log(np.exp(log_p_star[env.variants[s]]).sum()))
                         for s in env.series])
    net = agents.F2Net(9, [], len(env.series), env.n)
    with torch.no_grad():
        net.series_head.weight.zero_()
        net.series_head.bias.copy_(torch.tensor(s_logits))
        net.variant_head.weight.zero_()
        net.variant_head.bias.copy_(torch.tensor(log_p_star))
        net.logz_head.weight.zero_()
        net.logz_head.bias.copy_(torch.tensor([log_z_star]))
    agent.net = net
    env.reset(_train_ctxs(1)[0])
    obs = np.asarray(env.obs(), dtype=np.float32)
    for _ in range(16):  # on-policy trajectories sampled from the exact policy, no checker calls
        k, j = agent.act(env)
        i = env.variants[env.series[k]][j]
        agent.observe(obs, (k, j), float(log_r[i]), True, {})
    out = agent.update()
    assert out is not None
    assert out["loss"] < 1e-9


def test_f2_learning_direction_without_checker_calls(kc):
    """A sign check, explicitly NOT a result: on one fabricated fixed log R, ~300 TB samples lower
    the KL(softmax(logR) || joint) and shrink the learned logZ error - no checker calls."""
    env = F2Env(kc)
    cfg = _cfg_f2(seed=0, f2={"beta": 50, "batch_size": 16, "logz_lr": 0.05},
                  network={"hidden": [8], "lr": 0.05})
    agent = agents.make_f2_agent(cfg, env)
    env.reset(_train_ctxs(1)[0])
    obs = np.asarray(env.obs(), dtype=np.float32)
    log_r = -(0.05 * np.arange(91) + 0.3 * np.sin(np.arange(91)))  # a fixed fabricated log R
    p_star = np.exp(log_r) / np.exp(log_r).sum()
    log_z_star = float(np.log(np.exp(log_r).sum()))

    def metrics():
        joint = agent.joint_probs(obs)
        kl = float((p_star * np.log((p_star + 1e-300) / (joint + 1e-300))).sum())
        logz = float(agent.net(torch.as_tensor(obs))[2])
        return kl, abs(logz - log_z_star)

    kl0, dz0 = metrics()
    for _ in range(300):  # ~300 TB samples; the trajectory log R is the fabricated value
        k, j = agent.act(env)
        i = env.variants[env.series[k]][j]
        agent.observe(obs, (k, j), float(log_r[i]), True, {})
        agent.update()
    kl1, dz1 = metrics()
    print(f"KL(target || joint): {kl0:.4f} -> {kl1:.4f}; |logZ error|: {dz0:.4f} -> {dz1:.4f}")
    assert kl1 < kl0
    assert dz1 < dz0


def test_f2_learning_direction_3000_gradient_steps(kc):
    """The strengthened sign check, explicitly NOT a result: "steps" means GRADIENT steps. On the
    same fabricated fixed log R (one fixed context, batch 16, hidden [8], lr 0.05, logz_lr 0.05,
    seed 0), 3,000 gradient steps = 48,000 on-policy samples with NO checker calls. The
    trajectory-balance objective must drive the policy to softmax(logR) and logZ to
    logsumexp(logR): |logZ error| < 0.1 and KL < 0.25 x the initial KL. If this fails, the printed
    numbers flag a possible bug in F2Agent (gradient only reaching logZ, a wrong mask or a wrong
    sign) - the thresholds are never tuned."""
    env = F2Env(kc)
    cfg = _cfg_f2(seed=0, f2={"beta": 50, "batch_size": 16, "logz_lr": 0.05},
                  network={"hidden": [8], "lr": 0.05})
    agent = agents.make_f2_agent(cfg, env)
    env.reset(_train_ctxs(1)[0])
    obs = np.asarray(env.obs(), dtype=np.float32)
    log_r = -(0.05 * np.arange(91) + 0.3 * np.sin(np.arange(91)))  # a fixed fabricated log R
    p_star = np.exp(log_r) / np.exp(log_r).sum()
    log_z_star = float(np.log(np.exp(log_r).sum()))

    def metrics():
        joint = agent.joint_probs(obs)
        kl = float((p_star * np.log((p_star + 1e-300) / (joint + 1e-300))).sum())
        logz = float(agent.net(torch.as_tensor(obs))[2])
        return kl, abs(logz - log_z_star)

    kl0, dz0 = metrics()
    print(f"step {0:5d}: KL {kl0:.6f}, |logZ error| {dz0:.6f}")
    for step in range(1, 3001):
        for _ in range(16):  # one full batch per gradient step, sampled on-policy
            k, j = agent.act(env)
            i = env.variants[env.series[k]][j]
            agent.observe(obs, (k, j), float(log_r[i]), True, {})
        assert agent.update() is not None
        if step in (300, 1000, 3000):
            kl, dz = metrics()
            print(f"step {step:5d}: KL {kl:.6f}, |logZ error| {dz:.6f}")
    kl_end, dz_end = metrics()
    assert dz_end < 0.1
    assert kl_end < 0.25 * kl0


def test_f2_greedy_equals_argmax_of_joint(kc):
    env = F2Env(kc)
    agent = _agent_f2(_cfg_f2(seed=1), kc)
    env.reset(_train_ctxs(1)[0])
    for _ in range(3):
        joint = agent.joint_probs(env.obs())
        k, j = agent.greedy_act(env)
        i = env.variants[env.series[k]][j]
        assert i == int(np.argmax(joint))  # env.greedy ties to the lowest mass index = argmax
        assert 0 <= k < len(env.series) and 0 <= j < len(env.variants[env.series[k]])


def test_f2_same_seed_identical_greedy_outputs_and_call_sequence(tmp_path, kc):
    """The P11 acceptance line for F2: two runs with the same seed reproduce the greedy outputs and
    the episode/call sequence (the series and variant draws use the seeded torch Generator)."""
    ctxs = _train_ctxs(4)
    cfg = _cfg_f2(seed=3, budget=40, checkpoints=[10, 20], eval_contexts=ctxs)
    harness.run(cfg, _agent_f2(cfg, kc), kc, tmp_path / "a")
    harness.run(cfg, _agent_f2(cfg, kc), kc, tmp_path / "b")
    for th in (10, 20):
        ev_a = (tmp_path / "a" / f"eval_{th}.csv").read_text()
        ev_b = (tmp_path / "b" / f"eval_{th}.csv").read_text()
        assert ev_a == ev_b
        assert len(ev_a.splitlines()) == 5  # header + 4 contexts
    episodes = lambda p: [l for l in (tmp_path / p / "run.jsonl").read_text().splitlines()
                          if json.loads(l)["event"] == "episode"]
    assert episodes("a") == episodes("b")


def test_f2_budget_stops_exactly(tmp_path, kc):
    cfg = _cfg_f2(budget=37, checkpoints=())
    summary = harness.run(cfg, _agent_f2(cfg, kc), kc, tmp_path)
    assert summary["training_calls"] == 37


def test_f2_checkpoint_roundtrip_restores_behaviour(kc):
    """checkpoint_state -> a fresh agent's load_state: the next greedy (k, j) and the next sampled
    (k, j) are identical (network, both optimizers, the sampling RNG and the batch buffer)."""
    cfg = _cfg_f2(seed=3, f2={"beta": 50, "batch_size": 4, "logz_lr": 0.01})
    ctx = _train_ctxs(1)[0]
    env_a = F2Env(kc)
    agent_a = agents.make_f2_agent(cfg, env_a)
    env_a.reset(ctx)
    for _ in range(2):
        k, j = agent_a.act(env_a)
        i = env_a.variants[env_a.series[k]][j]
        agent_a.observe(env_a.obs(), (k, j), 0.0, True, {})  # an arbitrary log R (no update runs)
        env_a.reset(ctx)
    state = agent_a.checkpoint_state()

    agent_b = agents.make_f2_agent(cfg, F2Env(kc))
    agent_b.load_state(state)
    env_a.reset(ctx)
    env_b = F2Env(kc)
    env_b.reset(ctx)
    assert agent_b.greedy_act(env_b) == agent_a.greedy_act(env_a)
    assert agent_b.act(env_b) == agent_a.act(env_a)
    assert len(agent_b.batch) == len(agent_a.batch) == 2
    for b in agent_b.batch:
        assert any(torch.equal(b[0], o) and b[1] == k and b[2] == j and b[3] == r
                   for o, k, j, r in agent_a.batch)


def test_f2_finite_guard_fires_on_poisoned_weights(kc):
    cfg = _cfg_f2(f2={"beta": 50, "batch_size": 2, "logz_lr": 0.01})
    env = F2Env(kc)
    agent = agents.make_f2_agent(cfg, env)
    env.reset(_train_ctxs(1)[0])
    obs = np.asarray(env.obs(), dtype=np.float32)
    for _ in range(2):
        agent.observe(obs, (0, 0), -1.0, True, {})
    with torch.no_grad():
        agent.net.series_head.weight[0, :] = float("nan")
    with pytest.raises(RuntimeError, match="non-finite"):
        agent.update()
