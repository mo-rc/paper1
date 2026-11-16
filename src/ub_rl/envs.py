"""P10: Stage 1 RL environments and rewards (spec section 9 as amended by A3 and A5). No
algorithms, no training, no result files.

  F0  direct choice (contextual bandit): one sampled section per context, one checker call per
      sample, scored with R1 as an accepted section (no step cost); greedy output = arg max
      probability (the policy side, not built here).
  F1  refinement MDP: starts at the trial section (baselines.trial_index, which costs no checker
      call); reset costs 1 checker call (the trial section's utilisation is the first observation);
      every move - including a no-op past a catalogue end - is a step costing STEP_COST_R1; an
      explicit accept is not a step and costs nothing; after the N_MAX-th (13th) move the current
      section is accepted automatically. Visits are cached within the episode, like
      baselines.heuristic: a revisit costs a step but no call, so calls = 1 + the number of newly
      visited sections.
  F2  constructive (GFlowNet tree): two choices, series then variant within the series; one checker
      call for the sampled section; R3 log-reward; greedy(p_series, p_variant) = exact arg max of
      the joint probability P(series) P(variant | series) over C.

Rewards are float64 log-space, exactly the spec formulas, with N_MAX, STEP_COST_R1 and R3_BETAS
imported from ub_rl.reward_checks (no copies); tests/test_envs.py asserts equality with the
reward_checks formulas to 1e-12 and the strict feasible > infeasible ordering (including episode
returns with the worst-case step cost).

Calls are measured by the CountingChecker (the cost unit of spec section 10), never the
environment's arithmetic. `env.calls` is a per-episode counter (baselined at reset(), re-baselined
by reset_calls()); the cumulative budget across episodes and phases is `kc.sections`, the checker's
own counter - never reset. The observation scales the context with fixed constants from the A2
registered ranges and the section geometry with the catalogue maxima - never data statistics.
`info` reports steps, calls and each step's max utilisation (the hook R-C would need; no R-C code
here).
"""
import math

import numpy as np

from .baselines import trial_index
from .context import DEFLECTION_RULES
from .reward_checks import N_MAX, R3_BETAS, STEP_COST_R1

# Fixed scaling constants: the A2 registered training boxes (READ: docs/spec.md Amendment A2
# Table 1 - span [9, 15] m, width [4, 8] m, dead [2.5, 5.0] kN/m2, live [2.0, 5.0] kN/m2; the
# depth caps none/700/800/900 mm). Never data statistics.
A2_SPAN_M = 15.0
A2_WIDTH_M = 8.0
A2_DEAD_KNM2 = 5.0
A2_LIVE_KNM2 = 5.0
A2_DEPTH_CAP_MM = 900.0
RULE_ORDER = tuple(sorted(DEFLECTION_RULES))  # fixed one-hot order ("tot250", "var200", "var360")


def r1_log_return(mass_kg_m, m_trial, m_max, feasible, steps):
    """R1 terminal-sparse return for an accepted section (spec section 9): -ln(m/m_trial) when
    feasible, -ln(m_max/m_trial) - 1 when infeasible, minus STEP_COST_R1 per step taken (float64
    log-space; the spec's 13-step worst case totals 0.013, below the margin of 1)."""
    lnm = math.log(float(mass_kg_m))
    ln_trial = math.log(float(m_trial))
    if feasible:
        term = -(lnm - ln_trial)
    else:
        term = -(math.log(float(m_max)) - ln_trial) - 1.0
    return term - STEP_COST_R1 * float(steps)


def r3_log_return(mass_kg_m, m_trial, m_max, feasible, beta):
    """R3 reward-proportional return (spec section 9): -beta ln(m/m_trial) when feasible,
    -beta ln(m_max/m_trial) - 10 when infeasible, no step cost (float64 log-space)."""
    lnm = math.log(float(mass_kg_m))
    ln_trial = math.log(float(m_trial))
    if feasible:
        return -float(beta) * (lnm - ln_trial)
    return -float(beta) * (math.log(float(m_max)) - ln_trial) - 10.0


def _series_maps(kc):
    """next-deeper / previous-shallower series targets per series, as f1_distances of
    src/ub_rl/landscape.py defines them: series ordered by (depth, first mass-order index); the
    move lands on the lightest (first mass-order index) section of the next strictly deeper /
    strictly shallower series; None past the ends (the move is then a no-op)."""
    series, h = kc.cat.series, kc.h
    first_of = {}
    for i, s in enumerate(series):
        first_of.setdefault(s, i)
    order = sorted(first_of, key=lambda s: (float(h[first_of[s]]), first_of[s]))
    deeper, shallower = {}, {}
    for k, s in enumerate(order):
        ds = [s2 for s2 in order[k + 1:] if h[first_of[s2]] > h[first_of[s]]]
        ss = [s2 for s2 in order[:k] if h[first_of[s2]] < h[first_of[s]]]
        deeper[s] = first_of[ds[0]] if ds else None
        shallower[s] = first_of[ss[-1]] if ss else None
    return deeper, shallower


class _EnvBase:
    """Shared: the CountingChecker (measured calls), the resettable call counter, fixed log-mass
    cache, the scaled context observation and the scaled section observation."""

    def __init__(self, kc):
        self.kc = kc
        self.n = len(kc)
        self._m_max = float(kc.mass[-1])
        self._ln_max = float(np.log(np.asarray(kc.mass, dtype=np.float64))[-1])
        self._h_max = float(kc.h.max())
        self._b_max = float(kc.cat["b"].max())
        self._tw_max = float(kc.cat["tw"].max())
        self._tf_max = float(kc.cat["tf"].max())
        self.ctx = None
        self.m_trial = 0.0
        self.ln_trial = 0.0
        self.done = False
        self._s0 = 0

    @property
    def calls(self):
        """Checker calls since the last reset (measured by the CountingChecker)."""
        return self.kc.sections - self._s0

    def reset_calls(self):
        """Re-baseline the counter: training, V-verification and evaluation calls stay separate."""
        self._s0 = self.kc.sections

    def _set_trial(self, ctx):
        t = trial_index(self.kc, ctx)  # no checker call
        self.m_trial = float(self.kc.mass[t])
        self.ln_trial = math.log(self.m_trial)
        return t

    def _context_obs(self, ctx):
        """The scaled context: span/15, width/8, dead/5, live/5, restraint_ratio (already in [0,1]),
        depth cap /900 (0 when no cap), one-hot deflection rule (fixed order). A2 constants only."""
        cap = 0.0 if ctx.depth_cap is None else ctx.depth_cap / A2_DEPTH_CAP_MM
        rule = [0.0] * len(RULE_ORDER)
        rule[RULE_ORDER.index(ctx.deflection_rule)] = 1.0
        return [ctx.span / A2_SPAN_M, ctx.width / A2_WIDTH_M, ctx.dead / A2_DEAD_KNM2,
                ctx.live / A2_LIVE_KNM2, ctx.restraint_ratio, cap, *rule]

    def _section_obs(self, i):
        """The current section's geometry and mass, scaled by the catalogue maxima (fixed
        constants, never data statistics)."""
        return [self.kc.mass[i] / self._m_max, self.kc.h[i] / self._h_max,
                self.kc.cat["b"][i] / self._b_max, self.kc.cat["tw"][i] / self._tw_max,
                self.kc.cat["tf"][i] / self._tf_max]


class F1Env(_EnvBase):
    """F1 refinement MDP (horizon N_MAX = 13, Amendment A3). reset() returns the observation; step()
    returns (observation, reward, done, info). Actions: "up", "down" (mass steps; up = heavier, as
    baselines.heuristic's "up in mass order until feasible"), "deeper", "shallower" (series moves),
    "accept". Every move, including a no-op, is a step costing STEP_COST_R1; an explicit accept is
    not a step; after the 13th move the current section is accepted automatically. The episode
    cache makes a revisit cost a step but no call."""

    def __init__(self, kc):
        super().__init__(kc)
        self._deeper, self._shallower = _series_maps(kc)
        self.i = 0
        self.steps = 0
        self.visited = {}  # index -> (feasible, utilisation row), cached within the episode
        self.max_u = []    # each move's max utilisation (the R-C hook; no R-C code here)

    def reset(self, ctx):
        self.ctx = ctx
        self._s0 = self.kc.sections
        self.i = self._set_trial(ctx)
        self.steps = 0
        self.done = False
        self.visited = {}
        self.max_u = []
        self._land(self.i)  # the 1 reset call: the trial section's utilisation is the first observation
        return self.obs()

    def obs(self):
        feasible, u = self.visited[self.i]
        return np.concatenate([self._context_obs(self.ctx), self._section_obs(self.i), u])

    def _land(self, i):
        if i not in self.visited:  # a revisit costs a step but no call
            e = self.kc.evaluate_context(self.ctx, [i])  # one counted checker call
            self.visited[i] = (bool(e["feasible"][0]), e["U"][0])
        return self.visited[i]

    def _move(self, action):
        i, s = self.i, self.kc.cat.series[self.i]
        if action == "up":  # one mass step heavier (index +1), as baselines.heuristic's "up"
            return min(self.n - 1, i + 1)
        if action == "down":  # one mass step lighter (index -1)
            return max(0, i - 1)
        if action == "deeper":
            return i if self._deeper[s] is None else self._deeper[s]
        if action == "shallower":
            return i if self._shallower[s] is None else self._shallower[s]
        raise ValueError(f"unknown action {action!r}")

    def step(self, action):
        if self.done:
            raise RuntimeError("episode already done")
        if action == "accept":
            self.done = True  # explicit accept: not a step, costs nothing
            feasible, _ = self.visited[self.i]
            r = r1_log_return(self.kc.mass[self.i], self.m_trial, self._m_max, feasible, self.steps)
            return self.obs(), r, self.done, self.info()
        self.i = self._move(action)
        self.steps += 1  # every move, including a no-op, is a step
        feasible, u = self._land(self.i)
        self.max_u.append(float(u.max()))
        if self.steps >= N_MAX:  # after the 13th move: accepted automatically
            self.done = True
            r = r1_log_return(self.kc.mass[self.i], self.m_trial, self._m_max, feasible, self.steps)
        else:
            r = 0.0
        return self.obs(), r, self.done, self.info()

    def info(self):
        return {"steps": self.steps, "calls": self.calls, "max_utilisation": list(self.max_u)}


class F0Env(_EnvBase):
    """F0 direct choice (contextual bandit): step(i) samples one section - one checker call - and
    scores it with R1 as an accepted section (no step cost). The observation is the scaled
    context; the categorical policy is not built here."""

    def reset(self, ctx):
        self.ctx = ctx
        self._s0 = self.kc.sections
        self._set_trial(ctx)
        self.done = False
        return np.asarray(self._context_obs(ctx), dtype=np.float64)

    def step(self, i):
        if self.done:
            raise RuntimeError("episode already done")
        e = self.kc.evaluate_context(self.ctx, [int(i)])  # one counted checker call per sample
        feasible, u = bool(e["feasible"][0]), e["U"][0]
        r = r1_log_return(self.kc.mass[int(i)], self.m_trial, self._m_max, feasible, 0)
        self.done = True
        return self.obs(), r, self.done, {"steps": 0, "calls": self.calls,
                                          "max_utilisation": [float(u.max())]}

    def obs(self):
        return np.asarray(self._context_obs(self.ctx), dtype=np.float64)


class F2Env(_EnvBase):
    """F2 constructive MDP (GFlowNet tree): choose a series, then a variant within the series; the
    sampled section costs one checker call and scores R3. greedy() is the exact arg max of the
    joint probability P(series) P(variant | series) over C (spec: the tree makes F2 a hierarchical
    categorical distribution)."""

    def __init__(self, kc):
        super().__init__(kc)
        series = kc.cat.series
        h = kc.h
        first_of = {}
        for i, s in enumerate(series):
            first_of.setdefault(s, i)
        self.series = sorted(first_of, key=lambda s: (float(h[first_of[s]]), first_of[s]))
        self.variants = {s: [i for i, x in enumerate(series) if x == s] for s in self.series}

    def reset(self, ctx):
        self.ctx = ctx
        self._s0 = self.kc.sections
        self._set_trial(ctx)
        self.done = False
        return np.asarray(self._context_obs(ctx), dtype=np.float64)

    def step(self, series_k, variant_j, beta):
        """Sample one section (series_k into self.series, variant_j into that series' variants):
        one checker call, R3 log-reward with the given beta (one of reward_checks.R3_BETAS)."""
        if self.done:
            raise RuntimeError("episode already done")
        i = self.variants[self.series[series_k]][variant_j]
        e = self.kc.evaluate_context(self.ctx, [i])  # one counted checker call per sample
        feasible, u = bool(e["feasible"][0]), e["U"][0]
        r = r3_log_return(self.kc.mass[i], self.m_trial, self._m_max, feasible, beta)
        self.done = True
        return self.obs(), r, self.done, {"steps": 0, "calls": self.calls,
                                          "max_utilisation": [float(u.max())]}

    def greedy(self, p_series, p_variant):
        """Exact arg max over C of P(series) P(variant | series)."""
        best_i, best_p = -1, float("-inf")
        for k, s in enumerate(self.series):
            for j, i in enumerate(self.variants[s]):
                p = p_series[k] * p_variant[k][j]
                if p > best_p:
                    best_i, best_p = i, p
        return best_i

    def obs(self):
        return np.asarray(self._context_obs(self.ctx), dtype=np.float64)
