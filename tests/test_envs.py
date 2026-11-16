"""P10: the Stage 1 RL environments (F0 direct choice, F1 refinement with horizon 13, F2 constructive
tree) and the R1/R3 rewards, exactly as registered (spec section 9, Amendments A3 and A5). The envs
reuse baselines.trial_index, the CountingChecker and the reward_checks
constants; the tests assert the step/call semantics, the episode cache, the 13-move auto-accept on a
real 13-move T3 context, and that the env reward functions equal the reward_checks formulas to 1e-12
with the strict feasible > infeasible ordering (worst-case step cost included). Fast tests sample the
first N contexts per file; the full-V ordering check (1,000 contexts) is a slow test the project lead
runs himself (P10_FULL_V_ORDERING=1). No algorithms, no training, no result files."""
import math
import os
from pathlib import Path

import numpy as np
import pytest

from ub_rl import baselines, envs, landscape, reward_checks
from ub_rl import splits as S
from ub_rl.checker import Checker

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ROOT / "data" / "splits"
N_SAMPLE = 10


@pytest.fixture(scope="module")
def kc(C):
    return baselines.CountingChecker(Checker(C))


def _val_ctxs():
    return S.load_split("val", root=SPLITS)[1]


def _shortest_walk(env, D, start, target):
    """Rebuild one shortest walk start -> target over the env's move graph: at every node a
    decreasing edge of the exact landscape distance matrix D exists (no-op self-edges skipped)."""
    path, cur = [], start
    while cur != target:
        s = env.kc.cat.series[cur]
        for act, nxt in (("down", cur - 1 if cur > 0 else cur),
                         ("up", cur + 1 if cur < env.n - 1 else cur),
                         ("deeper", env._deeper[s]), ("shallower", env._shallower[s])):
            nxt = cur if nxt is None else nxt
            if nxt != cur and D[nxt, target] == D[cur, target] - 1:
                path.append(act)
                cur = nxt
                break
        else:
            raise AssertionError("no decreasing edge on a shortest walk")
    return path


# ------------------------------------------------------------------ step semantics
def test_f1_step_semantics(kc):
    """Mass steps land on the neighbour; series moves land on the lightest section of the next
    strictly deeper/shallower series; an explicit accept is not a step and terminates with the R1
    return of the current section."""
    ctx = _val_ctxs()[0]
    env = envs.F1Env(kc)
    env.reset(ctx)
    assert env.calls == 1  # the trial section's utilisation is the first observation
    t, steps0 = env.i, env.steps

    env.step("up")
    assert env.i == min(t + 1, env.n - 1) and env.steps == steps0 + 1
    env.step("down")
    assert env.i == t and env.steps == steps0 + 2

    old_series = kc.cat.series[env.i]
    env.step("deeper")
    new_series = kc.cat.series[env.i]
    first_of_new = next(i for i, s in enumerate(kc.cat.series) if s == new_series)
    assert env.i == first_of_new  # the lightest section of the new series
    assert (new_series == old_series and env.i == t) or kc.h[env.i] > kc.h[t]  # no-op, or strictly deeper

    env.step("shallower")
    s2 = kc.cat.series[env.i]
    first_of_s2 = next(i for i, s in enumerate(kc.cat.series) if s == s2)
    assert env.i == first_of_s2
    assert kc.h[env.i] <= kc.h[t] + 1e-9  # back to the previous (or the same) series

    steps_before = env.steps
    obs, r, done, info = env.step("accept")
    assert done and env.steps == steps_before  # accept is not a step
    assert info["steps"] == steps_before and info["calls"] == env.calls
    feasible = kc.evaluate_context(ctx, [env.i])["feasible"][0]
    assert r == envs.r1_log_return(kc.mass[env.i], env.m_trial, kc.mass[-1], bool(feasible), steps_before)


def test_f1_horizon_13_on_a_t3_e3_13_move_context(kc):
    """One of the 17 T3 contexts whose optimum is exactly 13 moves from the trial section
    (paper/tables/p9_horizon.csv: 4+1+12 across t3-E1/E2/E3; scan t3-E3 only). Stepping the exact
    13-move shortest walk must land on the optimum on the 13th move and accept it automatically."""
    rows, ctxs = S.load_split("test_t3", root=SPLITS)
    D = landscape.f1_distances(kc.cat.series, kc.h)
    found = None
    for r, ctx in zip(rows, ctxs):
        if r["set"] != "t3-E3":
            continue
        e = kc.evaluate_context(ctx)
        if not e["feasible"].any():
            continue
        opt = int(np.argmax(e["feasible"]))  # the lightest feasible section in mass order
        t = baselines.trial_index(kc, ctx)
        if D[t, opt] == 13:
            found = (ctx, t, opt)
            break
    assert found is not None, "no t3-E3 context with the optimum exactly 13 moves from the trial"

    ctx, t, opt = found
    env = envs.F1Env(kc)
    env.reset(ctx)
    assert env.i == t and env.calls == 1 and env.steps == 0
    path = _shortest_walk(env, D, t, opt)
    assert len(path) == 13
    done = False
    for k, act in enumerate(path, 1):
        _, r, done, info = env.step(act)
        if k < 13:
            assert not done
    assert done and env.i == opt  # the 13th move: landed on the optimum, accepted automatically
    assert info["steps"] == 13 and info["calls"] == env.calls
    assert r == envs.r1_log_return(kc.mass[opt], env.m_trial, kc.mass[-1], True, 13)


def test_f1_move_graph_matches_landscape(kc):
    """Every env move is either a no-op or a landscape edge (D == 1), and every landscape edge is
    produced by some action - the env's move graph is exactly f1_distances'."""
    D = landscape.f1_distances(kc.cat.series, kc.h)
    n = len(kc)
    env = envs.F1Env(kc)
    for i in range(n):
        env.i = i  # _move reads only the current index and its series
        produced = set()
        for act in ("up", "down", "deeper", "shallower"):
            j = env._move(act)
            assert 0 <= j < n
            if j != i:  # a move: must be a landscape edge
                assert D[i, j] == 1, f"action {act} from {i} lands at {j} but D[{i},{j}] = {D[i, j]}"
            produced.add(j)
        for j in np.flatnonzero(D[i] == 1):  # every edge is reachable by some action
            assert j in produced, f"landscape edge {i} -> {j} not produced by any action"


def test_f1_calls_equal_distinct_visited_with_revisit_and_noop(kc, C):
    """The episode cache: a revisit costs a step but no call, and a no-op past a catalogue end costs
    a step but no call — a walk that ends at the lightest end, revisits the end section and then
    no-ops past it has steps > calls, and calls equal the number of distinct sections visited
    (measured by the CountingChecker)."""
    seen = []

    class Rec(baselines.CountingChecker):
        def evaluate_context(self, ctx, idx=None):
            seen.append([int(i) for i in np.atleast_1d(idx)])
            return super().evaluate_context(ctx, idx)

    rec = Rec(Checker(C))
    rows, ctxs = S.load_split("val", root=SPLITS)
    D = landscape.f1_distances(rec.cat.series, rec.h)  # the same move graph as the env
    n = len(rec)
    chosen = None
    for r, ctx in zip(rows, ctxs):
        t = baselines.trial_index(rec, ctx)  # no checker call
        if D[t, 0] <= 10:  # leave 3 moves for the revisit and the no-op (horizon 13)
            chosen = (r, ctx, t)
            break
    assert chosen is not None, "no val context whose trial reaches index 0 in <= 10 F1 moves"
    r, ctx, t = chosen

    env = envs.F1Env(rec)
    path = _shortest_walk(env, D, t, 0)  # a shortest walk trial -> 0 over the env's move graph
    assert D[t, 0] + 3 <= reward_checks.N_MAX

    env.reset(ctx)
    assert env.i == t
    for act in path:  # the walk to index 0: each landing a distinct, newly visited section
        _, _, done, _ = env.step(act)
        assert not done
    assert env.i == 0 and env.calls == D[t, 0] + 1  # 1 reset call + one per path landing
    env.step("up")    # 0 -> 1 (visited or not): one step
    env.step("down")  # 1 -> 0: a revisit, a step but no call
    env.step("down")  # no-op past the lightest end: a step, no call

    visited = {i for part in seen for i in part}
    assert env.calls == len(visited)                  # calls = distinct sections visited
    assert env.info()["steps"] == D[t, 0] + 3         # the revisit and the no-op cost steps
    assert env.info()["steps"] > env.calls
    assert len(env.info()["max_utilisation"]) == D[t, 0] + 3  # one entry per move (the R-C hook)
    assert env.i == 0


# ------------------------------------------------------------------ F0 and F2
def test_f0_bandit_semantics(kc):
    ctx = _val_ctxs()[0]
    ref = baselines.enumerate(kc, ctx)  # before reset: the reference must not pollute the env counter
    env = envs.F0Env(kc)
    obs = env.reset(ctx)
    assert obs.shape == (9,)  # span, width, dead, live, restraint, cap, 3 rule one-hots
    assert ref.index >= 0
    _, r, done, info = env.step(ref.index)
    assert done and env.calls == 1 and info["steps"] == 0
    assert r == envs.r1_log_return(kc.mass[ref.index], env.m_trial, kc.mass[-1], True, 0)
    e_ref = kc.evaluate_context(ctx, [ref.index])
    assert info["max_utilisation"][0] == pytest.approx(float(e_ref["U"][0].max()), abs=1e-12)


def test_f2_tree_and_greedy(kc):
    ctx = _val_ctxs()[0]
    env = envs.F2Env(kc)
    env.reset(ctx)
    # the series/variant lists partition C exactly: every section index appears exactly once
    flat = sorted(i for vs in env.variants.values() for i in vs)
    assert flat == list(range(len(kc)))
    # the greedy output is the exact arg max of the joint probability vector over C
    for seed in (0, 1, 2):
        rng = np.random.default_rng(seed)
        p_s = rng.random(len(env.series))
        p_v = [rng.random(len(env.variants[s])) for s in env.series]
        joint = np.zeros(len(kc))
        for k, s in enumerate(env.series):
            joint[env.variants[s]] = p_s[k] * p_v[k]
        assert env.greedy(p_s, p_v) == int(np.argmax(joint))
    # one sampled section = one call, R3 reward, per beta
    for beta in reward_checks.R3_BETAS:
        env.reset(ctx)
        _, r, done, info = env.step(1, 0, beta)
        assert done and env.calls == 1 and info["steps"] == 0
        i = env.variants[env.series[1]][0]
        feasible = bool(kc.evaluate_context(ctx, [i])["feasible"][0])
        assert r == envs.r3_log_return(kc.mass[i], env.m_trial, kc.mass[-1], feasible, beta)


def test_reset_calls_rebaselines_the_counter(kc):
    """reset_calls() re-baselines the per-episode counter mid-way (training, V-verification and
    evaluation calls stay separate; the cumulative budget remains kc.sections)."""
    ctx = _val_ctxs()[0]
    env = envs.F1Env(kc)
    env.reset(ctx)
    assert env.calls == 1
    env.step("up")
    assert env.calls == 2
    before = kc.sections
    env.reset_calls()
    assert env.calls == 0
    env.step("up")
    assert env.calls == 1
    assert kc.sections == before + 1  # the cumulative counter never resets


# ------------------------------------------------------------------ rewards vs reward_checks
def _check_rewards_one_context(kc, ctx):
    """All 91 candidates: env reward functions equal the reward_checks formulas to 1e-12 and the
    strict feasible > infeasible ordering holds, worst-case step cost included. Returns the
    non-vacuous flag."""
    lnm = np.log(np.asarray(kc.mass, dtype=np.float64))
    ln_max = float(lnm[-1])
    e = kc.evaluate_context(ctx)
    ok = e["feasible"]
    if not (ok.any() and (~ok).any()):
        return False
    t = baselines.trial_index(kc, ctx)
    ln_trial = float(lnm[t])
    m_trial, m_max = float(kc.mass[t]), float(kc.mass[-1])
    r = reward_checks.context_ordering(lnm, ok, float(e["U"][t].max()), ln_trial, ln_max)

    for i in range(len(kc)):
        m, f = float(kc.mass[i]), bool(ok[i])
        lnm_i = math.log(m)
        for steps in (0, reward_checks.N_MAX):  # per-candidate equality, both step extremes
            ref = -(lnm_i - ln_trial) - reward_checks.STEP_COST_R1 * steps if f else \
                -(ln_max - ln_trial) - 1.0 - reward_checks.STEP_COST_R1 * steps
            assert envs.r1_log_return(m, m_trial, m_max, f, steps) == pytest.approx(ref, abs=1e-12)
        for beta in reward_checks.R3_BETAS:
            ref3 = -float(beta) * (lnm_i - ln_trial) if f else \
                -float(beta) * (ln_max - ln_trial) - 10.0
            assert envs.r3_log_return(m, m_trial, m_max, f, beta) == pytest.approx(ref3, abs=1e-12)

    # envelope equality with the reward_checks aggregates, and the strict ordering
    min_f = min(envs.r1_log_return(float(kc.mass[i]), m_trial, m_max, True, reward_checks.N_MAX)
                for i in np.flatnonzero(ok))
    max_i = max(envs.r1_log_return(float(kc.mass[i]), m_trial, m_max, False, 0)
                for i in np.flatnonzero(~ok))
    assert min_f == pytest.approx(r["R1"][0], abs=1e-12)
    assert max_i == pytest.approx(r["R1"][1], abs=1e-12)
    assert min_f > max_i
    for beta in reward_checks.R3_BETAS:
        key = f"R3-b{beta}"
        min_f3 = min(envs.r3_log_return(float(kc.mass[i]), m_trial, m_max, True, beta)
                     for i in np.flatnonzero(ok))
        max_i3 = max(envs.r3_log_return(float(kc.mass[i]), m_trial, m_max, False, beta)
                     for i in np.flatnonzero(~ok))
        assert min_f3 == pytest.approx(r[key][0], abs=1e-12)
        assert max_i3 == pytest.approx(r[key][1], abs=1e-12)
        assert min_f3 > max_i3
    return True


def test_rewards_match_reward_checks_and_order(kc):
    """Fast version: the first N V contexts (the full-V version is the slow test below)."""
    n = sum(1 for ctx in _val_ctxs()[:N_SAMPLE] if _check_rewards_one_context(kc, ctx))
    assert n > 0


@pytest.mark.slow
@pytest.mark.skipif(os.environ.get("P10_FULL_V_ORDERING") != "1",
                    reason="full-V ordering check (1,000 contexts): the project lead runs it himself - "
                           "P10_FULL_V_ORDERING=1 conda run -n rl_env python -m pytest tests/test_envs.py "
                           "-k full_v_ordering -q")
def test_full_v_ordering_check(kc):
    """The per-candidate ordering assertion over all 1,000 V contexts (plan section 3: a slow check,
    never run by the plan author)."""
    n = 0
    for ctx in _val_ctxs():
        n += int(_check_rewards_one_context(kc, ctx))
    assert n > 0
