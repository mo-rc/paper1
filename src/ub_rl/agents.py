"""P11 steps 3-5: the Stage 1 agents. F0-R1: REINFORCE with a learned baseline (step 3); F1-R1:
Dueling Double DQN with prioritized replay and n-step returns (step 4); F2-R3: conditional
GFlowNet with trajectory balance (step 5). All three entries are registered here.

F0 (spec section 9 as amended by A5; docs/p11_plan.md section 1): policy = an MLP over the 9-dim
scaled context (F0Env.obs; the shape is asserted in tests/test_envs.py) with a softmax over the 91
catalogue sections; baseline = a separate value MLP over the same context, trained by MSE on the
R1 log-return. Update: REINFORCE weighted by (return - baseline); the advantage is not normalised
across contexts unless the config flag f0.normalize_advantage says so. Batch size B contexts per
update (config f0.batch_size, provisional default 64): observe() accumulates, update() runs one
gradient step when the batch is full and returns the losses (None otherwise); an incomplete batch
at the budget stop is discarded. greedy_act is the argmax of the probabilities (torch.argmax
breaks exact ties to the lowest index); the sampled action uses a torch.Generator seeded from
cfg.seed - never the global RNG - so the same seed reproduces the same run.

F1 (docs/p11_plan.md section 1): actions in the fixed order up/down/deeper/shallower/accept over
the 22-dim F1Env.obs. Dueling network: shared trunk, value stream V and advantage stream A,
Q = V + (A - mean A). Dueling Double DQN: the ONLINE net picks argmax a' at the n-step bootstrap
state, the TARGET net gives its value; no bootstrap on a terminal window. Prioritized replay
(src/ub_rl/replay.py): proportional (|TD| + eps)^alpha with a sum tree, max priority for new
transitions, importance weights with beta annealed linearly to 1 over f1.beta_anneal_steps,
priorities updated from the new TD errors after each gradient step; all sampling from a seeded
numpy Generator, never the global RNG. Epsilon-greedy with the constant config f1.epsilon; a hard
target sync every f1.target_sync updates; Huber loss (smooth L1) and gradient-norm clipping at the
fixed provisional constants GRAD_CLIP / HUBER_BETA (not tuned). act() remembers the observation it
acted on (observe() receives the post-step observation); the env's done flag (accept or the
13th-move auto-accept) terminates windows, and a truncated episode's pending windows are discarded
when the next episode starts (detected by the steps/13 feature being 0). Learning starts when the
buffer holds at least f1.batch_size transitions; update() does one gradient step per call and
returns a dict of losses, else None. greedy_act = argmax Q, lowest index on ties.

F2 (docs/p11_plan.md section 1): the constructive GFlowNet tree, two choices - series then variant
within the series. Network: a shared trunk over the 9-dim context, a series head (logits over the
series), ONE variant head (logits over all 91 sections, masked to the chosen series' variants, so
P(variant | series) is the softmax over that series' sub-vector) and a learned logZ(context) head.
The section <-> (series k, variant j) mapping comes only from F2Env.series / F2Env.variants. act()
samples the series and then the variant with a torch.Generator seeded from cfg.seed (never the
global RNG) and returns (k, j); the harness passes the R3 beta to env.step. The reward observed is
the R3 log-reward, i.e. log R. Trajectory balance, on-policy, no replay: loss =
mean((logZ(c) + log P(series|c) + log P(variant|c, series) - log R)^2) over a batch of
f2.batch_size samples (provisional default 64); Adam with a separate learning rate f2.logz_lr for
the logZ head (provisional default: the network lr); gradient-norm clip at the fixed provisional
constant TB_GRAD_CLIP. An incomplete final batch is discarded. greedy_act returns the (k, j) of the
section with the largest joint probability via F2Env.greedy (exact ties to the lowest mass index,
plan decision 3e).

The harness agent contract is followed exactly; env.calls and info["calls"] are never read. Non-
finite logits, Q values, TD errors, losses, logZ or observations raise RuntimeError: silent NaN
learning is never allowed.
"""
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from . import harness
from .replay import OBS_DIM, PER_EPS, NStepBuilder, PrioritizedReplay

OBS_DIM_F0 = 9  # the scaled context of F0Env.obs (P11 plan section 1)
F1_ACTIONS = ("up", "down", "deeper", "shallower", "accept")  # the fixed action order
F1_A2I = {a: i for i, a in enumerate(F1_ACTIONS)}
GRAD_CLIP = 10.0   # fixed provisional constant (not tuned): gradient-norm clipping
HUBER_BETA = 1.0   # fixed provisional constant (not tuned): smooth-L1 (Huber) loss beta
TB_GRAD_CLIP = 10.0  # fixed provisional constant (not tuned): F2 trajectory-balance grad clip


class _MLP(nn.Module):
    """A small ReLU MLP: in_dim -> hidden layers -> out_dim."""

    def __init__(self, in_dim, hidden, out_dim):
        super().__init__()
        layers, d = [], in_dim
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU()]
            d = h
        layers.append(nn.Linear(d, out_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class F0Agent:
    """REINFORCE with a learned baseline over the F0 bandit: one sampled section per context, one
    checker call per sample, scored with the R1 log-return (no step cost)."""

    def __init__(self, cfg, env):
        torch.manual_seed(cfg.seed)  # deterministic construction per seed; afterwards the agent
        # uses only self.gen, never the global RNG
        self.gen = torch.Generator(device="cpu").manual_seed(cfg.seed)
        self.cfg = cfg
        self.n_actions = env.n
        hidden = [int(h) for h in cfg.network["hidden"]]
        self.policy = _MLP(OBS_DIM_F0, hidden, self.n_actions)
        self.value = _MLP(OBS_DIM_F0, hidden, 1)
        self.optimizer = torch.optim.Adam(
            list(self.policy.parameters()) + list(self.value.parameters()),
            lr=float(cfg.network["lr"]))
        self.batch_size = int(cfg.extra["f0"]["batch_size"])
        self.normalize_advantage = bool(cfg.extra["f0"]["normalize_advantage"])
        self.batch = []

    def _probs(self, obs):
        logits = self.policy(torch.as_tensor(np.asarray(obs, dtype=np.float32)))
        return torch.softmax(logits, dim=-1)

    def act(self, env):
        """The sampled (training) action: a categorical draw with self.gen, never the global RNG."""
        return int(torch.multinomial(self._probs(env.obs()), 1, generator=self.gen).item())

    def greedy_act(self, env):
        """Argmax of the probabilities; torch.argmax breaks exact ties to the lowest index."""
        return int(torch.argmax(self._probs(env.obs())).item())

    def observe(self, obs, action, reward, done, info):
        """Accumulate one transition; no learning happens here (and no call arithmetic is read)."""
        self.batch.append((torch.as_tensor(np.asarray(obs, dtype=np.float32)),
                           int(action), float(reward)))

    def update(self):
        """One REINFORCE gradient step when the batch is full, else None. Non-finite logits or
        losses raise RuntimeError. The batch is cleared before the step: an incomplete final batch
        at the budget stop is simply never updated (discarded)."""
        if len(self.batch) < self.batch_size:
            return None
        obs = torch.stack([b[0] for b in self.batch])
        acts = torch.tensor([b[1] for b in self.batch], dtype=torch.long)
        rets = torch.tensor([b[2] for b in self.batch], dtype=torch.float32)
        self.batch = []
        logits = self.policy(obs)
        if not torch.isfinite(logits).all():
            raise RuntimeError("non-finite logits in the REINFORCE update")
        log_probs = torch.log_softmax(logits, dim=-1)
        selected = log_probs[torch.arange(len(acts)), acts]
        baseline = self.value(obs).squeeze(-1)
        advantage = rets - baseline.detach()
        if self.normalize_advantage:
            advantage = (advantage - advantage.mean()) / (advantage.std() + 1e-8)
        policy_loss = -torch.mean(selected * advantage)
        baseline_loss = torch.mean((baseline - rets) ** 2)
        loss = policy_loss + baseline_loss
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite loss in the REINFORCE update")
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        return {"loss": float(loss), "policy_loss": float(policy_loss),
                "baseline_loss": float(baseline_loss)}

    def checkpoint_state(self):
        """Everything needed to resume: networks, optimizer, the sampling RNG and the batch buffer."""
        return {"policy": self.policy.state_dict(), "value": self.value.state_dict(),
                "optimizer": self.optimizer.state_dict(), "rng": self.gen.get_state(),
                "batch": [(o.clone(), a, r) for o, a, r in self.batch]}

    def load_state(self, state):
        self.policy.load_state_dict(state["policy"])
        self.value.load_state_dict(state["value"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.gen.set_state(state["rng"])
        self.batch = [(o.clone(), a, r) for o, a, r in state["batch"]]


def make_f0_agent(cfg, env):
    """The registered factory: harness main() calls it as AGENTS[entry](cfg, env)."""
    return F0Agent(cfg, env)


# ------------------------------------------------------------------ F1: Dueling Double DQN
class DuelingNet(nn.Module):
    """Dueling network: a shared trunk, a value stream V and an advantage stream A with
    Q = V + (A - mean A), so mean over actions of Q equals V exactly."""

    def __init__(self, in_dim, hidden, n_actions):
        super().__init__()
        layers, d = [], in_dim
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU()]
            d = h
        self.trunk = nn.Sequential(*layers)  # identity when hidden is empty (fabricated tests)
        self.value = nn.Linear(d, 1)
        self.advantage = nn.Linear(d, n_actions)

    def forward(self, x):
        f = self.trunk(x)
        v = self.value(f)
        a = self.advantage(f)
        return v + (a - a.mean(dim=-1, keepdim=True))

    def value_of(self, x):
        return self.value(self.trunk(x))


def double_dqn_target(online, target, obs, rets, next_obs, term, gamma_n):
    """The Dueling Double DQN target: the ONLINE net picks argmax a' at the n-step bootstrap state,
    the TARGET net gives its value; a terminal window gets no bootstrap."""
    with torch.no_grad():
        a_star = online(next_obs).argmax(dim=-1)
        q_next = target(next_obs)[torch.arange(len(next_obs)), a_star]
        return rets + (1.0 - term.float()) * gamma_n * q_next


class F1Agent:
    """Dueling Double DQN with prioritized replay and n-step returns on the F1 refinement MDP
    (horizon 13, Amendment A3; rewards R1 terminal-sparse)."""

    def __init__(self, cfg, env):
        torch.manual_seed(cfg.seed)  # deterministic construction per seed
        self.gen = torch.Generator(device="cpu").manual_seed(cfg.seed)
        self.np_rng = np.random.default_rng(cfg.seed)  # epsilon and replay sampling, never global
        self.cfg = cfg
        f1 = cfg.extra["f1"]
        self.n = int(f1["n"])
        self.gamma = float(f1["gamma"])
        self.epsilon = float(f1["epsilon"])
        self.batch_size = int(f1["batch_size"])
        self.replay_size = int(f1["replay_size"])
        self.alpha = float(f1["alpha"])
        self.beta_anneal_steps = int(f1["beta_anneal_steps"])
        self.target_sync = int(f1["target_sync"])
        hidden = [int(h) for h in cfg.network["hidden"]]
        self.online = DuelingNet(OBS_DIM, hidden, len(F1_ACTIONS))
        self.target = DuelingNet(OBS_DIM, hidden, len(F1_ACTIONS))
        self.target.load_state_dict(self.online.state_dict())
        self.optimizer = torch.optim.Adam(self.online.parameters(), lr=float(cfg.network["lr"]))
        self.replay = PrioritizedReplay(self.replay_size, self.alpha, self.np_rng)
        self.builder = NStepBuilder(self.n, self.gamma)
        self.last_obs = None  # the observation act() acted on (observe() gets the post-step one)
        self.steps = 0        # gradient steps taken (beta anneal and target sync)

    def _q(self, obs):
        return self.online(torch.as_tensor(np.asarray(obs, dtype=np.float32)))

    def act(self, env):
        """Epsilon-greedy (constant epsilon): a uniform random action with probability epsilon,
        else the argmax-Q action (lowest index on ties)."""
        obs = np.asarray(env.obs(), dtype=np.float32)
        if obs[-1] == 0.0 and self.last_obs is not None:
            # a new episode (steps/13 == 0): the previous one was truncated by the budget stop -
            # its partial n-step windows are discarded, never learned from
            self.builder.discard()
        self.last_obs = obs
        if self.np_rng.random() < self.epsilon:
            a = int(self.np_rng.integers(len(F1_ACTIONS)))
        else:
            with torch.no_grad():
                a = int(torch.argmax(self._q(obs)))
        return F1_ACTIONS[a]

    def greedy_act(self, env):
        """Argmax Q, lowest index on ties (used only for checkpoint evaluation)."""
        with torch.no_grad():
            return F1_ACTIONS[int(torch.argmax(self._q(env.obs())))]

    def observe(self, obs, action, reward, done, info):
        """Build the (s, a, r, s', done) transition from the remembered pre-step observation;
        push it through the n-step builder; completed windows enter the replay with max priority."""
        s = self.last_obs
        self.last_obs = None
        if s is None:  # defensive: no remembered state (nothing to learn from)
            return
        s_next = np.asarray(obs, dtype=np.float32)
        if not (np.isfinite(s).all() and np.isfinite(s_next).all()):
            raise RuntimeError("non-finite observation in the F1 DQN transition")
        for w in self.builder.push((s, F1_A2I[action], float(reward), s_next, bool(done))):
            self.replay.add(w, self.replay.max_priority())  # new transitions get max priority

    def update(self):
        """One Dueling Double DQN gradient step when the replay holds at least batch_size n-step
        transitions, else None. Huber loss with importance weights, gradient-norm clipping, PER
        priority update from the new TD errors, a hard target sync every target_sync steps."""
        if len(self.replay) < self.batch_size:
            return None
        beta = min(1.0, self.steps / float(self.beta_anneal_steps))
        slots, (obs, act, ret, next_obs, term), weights = self.replay.sample(self.batch_size, beta)
        obs_t = torch.as_tensor(obs)
        act_t = torch.as_tensor(act, dtype=torch.long)
        ret_t = torch.as_tensor(ret)
        next_t = torch.as_tensor(next_obs)
        term_t = torch.as_tensor(term)
        w_t = torch.as_tensor(weights)
        q = self.online(obs_t)[torch.arange(len(act_t)), act_t]
        if not torch.isfinite(q).all():
            raise RuntimeError("non-finite Q values in the F1 DQN update")
        target = double_dqn_target(self.online, self.target, obs_t, ret_t, next_t, term_t,
                                   self.gamma ** self.n)
        td = target - q
        if not torch.isfinite(td).all():
            raise RuntimeError("non-finite TD error in the F1 DQN update")
        loss = (w_t * F.smooth_l1_loss(q, target, reduction="none", beta=HUBER_BETA)).mean()
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite loss in the F1 DQN update")
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.online.parameters(), GRAD_CLIP)
        self.optimizer.step()
        self.replay.update_priorities(slots, td.detach().numpy())
        self.steps += 1
        if self.steps % self.target_sync == 0:
            self.target.load_state_dict(self.online.state_dict())
        return {"loss": float(loss), "td_mean": float(td.abs().mean()), "beta": beta}

    def checkpoint_state(self):
        """Everything needed to resume: networks, optimizer, torch and numpy RNG states, the FULL
        replay (incl. sum-tree priorities), the n-step window, the counters."""
        return {"online": self.online.state_dict(), "target": self.target.state_dict(),
                "optimizer": self.optimizer.state_dict(), "torch_rng": self.gen.get_state(),
                "np_rng": self.np_rng.bit_generator.state,
                "replay": self.replay.state(), "builder": self.builder.state(),
                "steps": self.steps,
                "last_obs": None if self.last_obs is None else self.last_obs.copy()}

    def load_state(self, state):
        self.online.load_state_dict(state["online"])
        self.target.load_state_dict(state["target"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.gen.set_state(state["torch_rng"])
        self.np_rng.bit_generator.state = state["np_rng"]
        self.replay.load_state(state["replay"])
        self.builder.load_state(state["builder"])
        self.steps = int(state["steps"])
        self.last_obs = None if state["last_obs"] is None else state["last_obs"].copy()


def make_f1_agent(cfg, env):
    """The registered factory: harness main() calls it as AGENTS[entry](cfg, env)."""
    return F1Agent(cfg, env)


# ------------------------------------------------------------------ F2: conditional GFlowNet
class F2Net(nn.Module):
    """The conditional GFlowNet policy: a shared trunk over the 9-dim context, a series head
    (logits over the series), one variant head (logits over all 91 sections, masked to the chosen
    series' variants) and a learned logZ(context) head for the trajectory-balance loss."""

    def __init__(self, in_dim, hidden, n_series, n_sections):
        super().__init__()
        layers, d = [], in_dim
        for h in hidden:
            layers += [nn.Linear(d, h), nn.ReLU()]
            d = h
        self.trunk = nn.Sequential(*layers)  # identity when hidden is empty (fabricated tests)
        self.series_head = nn.Linear(d, n_series)
        self.variant_head = nn.Linear(d, n_sections)
        self.logz_head = nn.Linear(d, 1)

    def forward(self, x):
        f = self.trunk(x)
        return self.series_head(f), self.variant_head(f), self.logz_head(f).squeeze(-1)


class F2Agent:
    """Conditional GFlowNet, trajectory balance, hierarchical series-then-variant policy (the tree
    makes the backward policy trivial), R3 log-rewards, on-policy with no replay."""

    def __init__(self, cfg, env):
        torch.manual_seed(cfg.seed)  # deterministic construction per seed
        self.gen = torch.Generator(device="cpu").manual_seed(cfg.seed)
        self.cfg = cfg
        f2 = cfg.extra["f2"]
        self.batch_size = int(f2["batch_size"])
        self.logz_lr = float(f2["logz_lr"])
        self.series = list(env.series)
        self.variants = {s: [int(i) for i in v] for s, v in env.variants.items()}
        self.n_sections = env.n
        hidden = [int(h) for h in cfg.network["hidden"]]
        self.net = F2Net(OBS_DIM_F0, hidden, len(self.series), self.n_sections)
        self.optimizer = torch.optim.Adam(
            list(self.net.trunk.parameters()) + list(self.net.series_head.parameters())
            + list(self.net.variant_head.parameters()), lr=float(cfg.network["lr"]))
        self.logz_optimizer = torch.optim.Adam(self.net.logz_head.parameters(), lr=self.logz_lr)
        self.batch = []  # (obs float32, k, j, log R); an incomplete final batch is discarded

    def _variant_logp(self, v_logits, k):
        """log P(variant | series k): the softmax over the series' own sub-vector of the one
        variant head (the head is masked to the series' variants from F2Env.variants)."""
        idx = self.variants[self.series[int(k)]]
        sub = v_logits.index_select(0, torch.as_tensor(idx, dtype=torch.long))
        return torch.log_softmax(sub, dim=-1), idx

    def act(self, env):
        """Sample the trajectory: series ~ softmax(series head), then variant ~ the masked
        softmax of the chosen series; both draws use self.gen, never the global RNG."""
        obs = torch.as_tensor(np.asarray(env.obs(), dtype=np.float32))
        with torch.no_grad():
            s_logits, v_logits, _ = self.net(obs)
            p_s = torch.softmax(s_logits, dim=-1)
            k = int(torch.multinomial(p_s, 1, generator=self.gen).item())
            logp_v, idx = self._variant_logp(v_logits, k)
            j = int(torch.multinomial(torch.exp(logp_v), 1, generator=self.gen).item())
        return (k, j)

    def greedy_act(self, env):
        """The (k, j) of the section with the largest joint probability P(series) P(variant |
        series), computed exactly over C by F2Env.greedy (exact ties to the lowest mass index)."""
        joint = self.joint_probs(env.obs())
        p_v = [joint[self.variants[s]] for s in self.series]
        i = env.greedy(np.ones(len(self.series)), p_v)
        for k, s in enumerate(self.series):
            if i in self.variants[s]:
                return (k, self.variants[s].index(i))
        raise RuntimeError("greedy section not found in the series/variant mapping")

    def joint_probs(self, obs):
        """The 91-vector of joint probabilities P(series) P(variant | series) in mass-order
        section index; sums to 1 (the masked variant head puts no mass outside the tree)."""
        with torch.no_grad():
            s_logits, v_logits, _ = self.net(torch.as_tensor(np.asarray(obs, dtype=np.float32)))
            log_p_s = torch.log_softmax(s_logits, dim=-1)
            log_joint = torch.full((self.n_sections,), float("-inf"))
            for k, s in enumerate(self.series):
                idx = self.variants[s]
                logp_v, _ = self._variant_logp(v_logits, k)
                log_joint[torch.as_tensor(idx, dtype=torch.long)] = log_p_s[k] + logp_v
            return torch.exp(log_joint).numpy()

    def observe(self, obs, action, reward, done, info):
        """Accumulate one on-policy trajectory: (context obs, k, j, log R). The reward passed by
        the harness is the R3 log-reward, i.e. log R. No learning happens here."""
        self.batch.append((torch.as_tensor(np.asarray(obs, dtype=np.float32)),
                           int(action[0]), int(action[1]), float(reward)))

    def update(self):
        """One trajectory-balance gradient step when the batch holds batch_size trajectories,
        else None: loss = mean((logZ(c) + log P(series|c) + log P(variant|c, series) - log R)^2).
        Adam, with the separate f2.logz_lr rate for the logZ head; gradient-norm clip at the fixed
        provisional TB_GRAD_CLIP."""
        if len(self.batch) < self.batch_size:
            return None
        obs = torch.stack([b[0] for b in self.batch])
        ks = torch.tensor([b[1] for b in self.batch], dtype=torch.long)
        js = torch.tensor([b[2] for b in self.batch], dtype=torch.long)
        log_rs = torch.tensor([b[3] for b in self.batch], dtype=torch.float32)
        self.batch = []  # cleared before the step: an incomplete final batch is discarded
        s_logits, v_logits, logz = self.net(obs)
        if not (torch.isfinite(s_logits).all() and torch.isfinite(v_logits).all()
                and torch.isfinite(logz).all()):
            raise RuntimeError("non-finite logits or logZ in the F2 GFlowNet update")
        log_p_s_taken = torch.log_softmax(s_logits, dim=-1)[torch.arange(len(ks)), ks]
        log_p_v = torch.empty(len(ks))
        for i in range(len(ks)):
            logp_v, _ = self._variant_logp(v_logits[i], ks[i])
            log_p_v[i] = logp_v[js[i]]
        loss = torch.mean((logz + log_p_s_taken + log_p_v - log_rs) ** 2)
        if not torch.isfinite(loss):
            raise RuntimeError("non-finite loss in the F2 GFlowNet update")
        self.optimizer.zero_grad()
        self.logz_optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.net.parameters(), TB_GRAD_CLIP)
        self.optimizer.step()
        self.logz_optimizer.step()
        return {"loss": float(loss)}

    def checkpoint_state(self):
        """Everything needed to resume: the network, both optimizers, the sampling RNG and the
        batch buffer."""
        return {"net": self.net.state_dict(), "optimizer": self.optimizer.state_dict(),
                "logz_optimizer": self.logz_optimizer.state_dict(),
                "rng": self.gen.get_state(),
                "batch": [(o.clone(), k, j, r) for o, k, j, r in self.batch]}

    def load_state(self, state):
        self.net.load_state_dict(state["net"])
        self.optimizer.load_state_dict(state["optimizer"])
        self.logz_optimizer.load_state_dict(state["logz_optimizer"])
        self.gen.set_state(state["rng"])
        self.batch = [(o.clone(), k, j, r) for o, k, j, r in state["batch"]]


def make_f2_agent(cfg, env):
    """The registered factory: harness main() calls it as AGENTS[entry](cfg, env)."""
    return F2Agent(cfg, env)


harness.register_agent("f0_r1", make_f0_agent)
harness.register_agent("f1_r1", make_f1_agent)
harness.register_agent("f2_r3", make_f2_agent)
