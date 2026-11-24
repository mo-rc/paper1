"""Focused unit tests for the unregistered P12b F1 R-C variant."""
import numpy as np
import pytest
import torch

from ub_rl import agents, harness
from ub_rl.agent_rc import RCF1Agent, RCF1Env
from ub_rl.context import Context
from ub_rl.envs import F1Env, r1_log_return


def _config(seed=7, n=1, batch_size=32, eval_contexts=None):
    return harness.RunConfig.from_dict({
        "entry": "f1_r1", "seed": seed, "budget": 100, "checkpoints": [],
        "budget_includes_eval": False, "eval_contexts": eval_contexts,
        "network": {"hidden": [8], "lr": 0.001},
        "f1": {"n": n, "epsilon": 0.2, "gamma": 0.9, "alpha": 0.6,
               "beta_anneal_steps": 100, "batch_size": batch_size,
               "replay_size": 64, "target_sync": 10},
    })


class _ToyCatalog:
    def __init__(self):
        self.series = ["A", "B", "C"]
        self.cols = {
            "b": np.asarray([150.0, 160.0, 170.0]),
            "tw": np.asarray([6.0, 6.0, 6.0]),
            "tf": np.asarray([8.0, 8.0, 8.0]),
        }

    def __getitem__(self, key):
        return self.cols[key]


class _ToyKC:
    def __init__(self):
        self.cat = _ToyCatalog()
        self.mass = np.asarray([50.0, 60.0, 70.0])
        self.h = np.asarray([500.0, 600.0, 700.0])
        self.Wpl = np.asarray([1.0e9, 1.1e9, 1.2e9])
        self.sections = 0
        self.util = np.asarray([1.4, 1.2, 0.8])

    def __len__(self):
        return len(self.mass)

    def evaluate_context(self, ctx, indices):
        indices = np.atleast_1d(np.asarray(indices, dtype=int))
        self.sections += len(indices)
        u = np.asarray([[self.util[i]] * 7 for i in indices], dtype=float)
        return {"feasible": self.util[indices] <= 1.0, "U": u}


def _context():
    return Context(span=9.0, width=4.0, dead=2.5, live=2.0)


def _observe_action(agent, env, action):
    old_obs = env.obs().copy()
    obs, reward, done, info = env.step(action)
    agent.last_obs = np.asarray(old_obs, dtype=np.float32)
    agent.observe(obs, action, reward, done, info)
    return reward, done, info


def _accept_episode(agent, env):
    env.reset(_context())
    return _observe_action(agent, env, "accept")


def _run_episodes(agent, env, count):
    traces = []
    for _ in range(count):
        env.reset(_context())
        done = False
        episode = []
        while not done:
            action = agent.act(env)
            obs, reward, done, info = env.step(action)
            episode.append((action, float(reward), bool(done)))
            agent.observe(obs, action, reward, done, info)
            agent.update()
        traces.append(episode)
    return traces


def test_exact_dual_update_uses_block_mean_and_logs_histories(caplog):
    kc = _ToyKC()
    env = RCF1Env(kc)
    agent = RCF1Agent(_config(), env, lambda_init=0.2, eta=0.5, update_cadence=2)
    with caplog.at_level("INFO", logger="ub_rl.agent_rc"):
        _accept_episode(agent, env)
        assert agent.lambda_history == []
        _accept_episode(agent, env)
    assert agent.lambda_value == pytest.approx(0.4)  # .2 + .5 * mean(.4, .4)
    assert agent.lambda_history == pytest.approx([0.4])
    assert agent.mean_c_history == pytest.approx([0.4])
    assert "lambda=0.4 mean_c=0.4" in caplog.text


def test_lambda_is_nonnegative_and_parameters_are_validated():
    env = RCF1Env(_ToyKC())
    agent = RCF1Agent(_config(), env, lambda_init=0.0, eta=1.0, update_cadence=1)
    _accept_episode(agent, env)
    assert agent.lambda_value >= 0
    with pytest.raises(ValueError):
        RCF1Agent(_config(), RCF1Env(_ToyKC()), lambda_init=-1, eta=0, update_cadence=1)
    with pytest.raises(ValueError):
        RCF1Agent(_config(), RCF1Env(_ToyKC()), lambda_init=0, eta=-1, update_cadence=1)
    with pytest.raises(ValueError):
        RCF1Agent(_config(), RCF1Env(_ToyKC()), lambda_init=0, eta=0, update_cadence=0)


def test_terminal_only_penalty_and_environment_reward_remains_r1():
    kc = _ToyKC()
    env = RCF1Env(kc)
    agent = RCF1Agent(_config(n=1), env, lambda_init=2.0, eta=0.0, update_cadence=1)
    env.reset(_context())
    _, nonterminal_done, _ = _observe_action(agent, env, "up")
    assert not nonterminal_done
    assert agent.replay.ret[0] == pytest.approx(0.0)  # nonterminal R1 remains zero

    accepted_index = env.i
    reward, done, _ = _observe_action(agent, env, "accept")
    assert done
    r1 = r1_log_return(kc.mass[accepted_index], env.m_trial, env._m_max,
                       env.visited[accepted_index][0], env.steps)
    c = max(0.0, float(env.visited[accepted_index][1].max()) - 1.0)
    assert reward == pytest.approx(r1)  # env.step returns unmodified R1
    assert agent.replay.ret[1] == pytest.approx(r1 - 2.0 * c)
    assert agent.terminal_records[-1]["training_terminal_reward"] == pytest.approx(r1 - 2.0 * c)


def test_nstep_terminal_window_has_penalty_but_earlier_window_does_not():
    gamma, lam = 0.9, 2.0
    kc = _ToyKC()
    env = RCF1Env(kc)
    agent = RCF1Agent(_config(n=2), env, lambda_init=lam, eta=0.0, update_cadence=10)
    env.reset(_context())

    # R1 gives zero on each movement before terminal acceptance.
    _observe_action(agent, env, "up")
    _observe_action(agent, env, "down")  # returns to toy row 0, with c=0.4 when accepted
    accepted_index = env.i
    reward, done, _ = _observe_action(agent, env, "accept")

    c = max(0.0, float(env.visited[accepted_index][1].max()) - 1.0)
    r_prev = 0.0  # R1 intermediate movement reward, from F1Env.step.
    # Window ending before terminal: r0 + gamma*r1 = 0 + .9*0 = 0.
    assert agent.replay.ret[0] == pytest.approx(0.0)
    # Terminal window: r_prev + gamma*(R1-lambda*c) = 0 + .9*(R1-2*c).
    assert done
    assert agent.replay.ret[1] == pytest.approx(r_prev + gamma * (reward - lam * c))


def test_evaluation_path_does_not_depend_on_lambda(tmp_path):
    ctx = _context()
    outputs = []
    for suffix, multiplier in (("a", 0.0), ("b", 9.0)):
        kc = _ToyKC()
        env = RCF1Env(kc)
        agent = RCF1Agent(_config(eval_contexts=[ctx]), env, lambda_init=multiplier,
                          eta=0.0, update_cadence=2)
        outdir = tmp_path / suffix
        outdir.mkdir()
        harness._evaluate(_config(eval_contexts=[ctx]), agent, env, kc, outdir, 1, lambda _: None)
        outputs.append((outdir / "eval_1.csv").read_text())
    assert outputs[0] == outputs[1]
    fields = outputs[0].splitlines()[1].split(",")
    output_index, feasible = int(fields[1]), bool(int(fields[2]))
    expected_feasible = _ToyKC().util[output_index] <= 1.0
    assert feasible is bool(expected_feasible)  # verified checker result, never penalised return


def test_lambda_snapshot_used_for_replay_is_episode_end_value():
    kc = _ToyKC()
    env = RCF1Env(kc)
    agent = RCF1Agent(_config(n=1), env, lambda_init=1.0, eta=1.0, update_cadence=1)
    reward, done, _ = _accept_episode(agent, env)
    assert done
    record = agent.terminal_records[-1]
    assert record["lambda_at_end"] == pytest.approx(1.0)
    assert agent.lambda_value > record["lambda_at_end"]  # dual update occurs after replay storage
    assert agent.replay.ret[0] == pytest.approx(
        reward - record["lambda_at_end"] * record["c"])


def test_same_seed_reproduces_rc_trace_weights_and_replay():
    cfg = _config(seed=13, n=2, batch_size=2)
    runs = []
    for _ in range(2):
        env = RCF1Env(_ToyKC())
        agent = RCF1Agent(cfg, env, lambda_init=0.1, eta=0.2, update_cadence=2)
        trace = _run_episodes(agent, env, 4)
        runs.append((agent, trace))
    (left, trace_left), (right, trace_right) = runs
    assert trace_left == trace_right
    assert left.lambda_history == right.lambda_history
    assert left.mean_c_history == right.mean_c_history
    assert left.lambda_value == right.lambda_value
    for a, b in zip(left.online.parameters(), right.online.parameters()):
        assert torch.equal(a, b)
    for key, value in left.replay.state().items():
        other = right.replay.state()[key]
        if isinstance(value, np.ndarray):
            assert np.array_equal(value, other)
        else:
            assert value == other


def test_zero_penalty_reproduces_existing_f1_network_and_replay():
    cfg = _config(seed=19, n=2, batch_size=2)
    kc_base, kc_rc = _ToyKC(), _ToyKC()
    base_env, rc_env = F1Env(kc_base), RCF1Env(kc_rc)
    base = agents.F1Agent(cfg, base_env)
    rc = RCF1Agent(cfg, rc_env, lambda_init=0.0, eta=0.0, update_cadence=2)
    assert _run_episodes(base, base_env, 4) == _run_episodes(rc, rc_env, 4)
    for a, b in zip(base.online.parameters(), rc.online.parameters()):
        assert torch.equal(a, b)
    base_replay, rc_replay = base.replay.state(), rc.replay.state()
    for key, value in base_replay.items():
        other = rc_replay[key]
        if isinstance(value, np.ndarray):
            assert np.array_equal(value, other)
        else:
            assert value == other


def test_plain_f1_environment_is_rejected():
    with pytest.raises(TypeError, match="requires an RCF1Env"):
        RCF1Agent(_config(), F1Env(_ToyKC()), lambda_init=0.0, eta=0.0,
                  update_cadence=1)


def test_immediate_accept_cost_uses_verified_record():
    env = RCF1Env(_ToyKC())
    env.reset(_context())
    accepted = env.i
    assert env.max_u == []  # explicit accept has no movement-derived info entry
    _, _, done, info = env.step("accept")
    assert done and info["max_utilisation"] == []
    # Reset selects toy row 0; all seven utilisations are 1.4, so c=max(0,1.4-1)=0.4.
    assert accepted == 0
    assert env.accepted_cost() == pytest.approx(0.4)
