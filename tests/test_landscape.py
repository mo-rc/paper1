"""P9: landscape diagnostics — monotonicity counters, the F1 horizon check, alternatives and the
governing check at the optimum (spec sections 9 and 12; patch plan P9). Synthetic masks and graphs
test the counting and the action graph exactly; sampled split contexts test against the verified
checker. Skips without the workbook (conftest).
"""
from pathlib import Path

import numpy as np
import pytest

from ub_rl import splits as S
from ub_rl.checker import CHECKS, Checker
from ub_rl.landscape import diagnose, f1_distances, monotonicity

ROOT = Path(__file__).resolve().parent.parent
FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]


@pytest.fixture(scope="module")
def K(C):
    return Checker(C)


@pytest.fixture(scope="module")
def sample_contexts():
    out = []
    for name in FILES:
        _, ctxs = S.load_split(name, root=ROOT / "data" / "splits")
        out.extend(ctxs[:10])
    return out


@pytest.fixture(scope="module")
def f1_d(K):
    return f1_distances(K.cat.series, K.h)


# ---------------------------------------------------------------- the monotonicity counter
def test_clean_feasible_block_has_zero_counters():
    ok = np.array([False, False, True, True, True, True, True, True, True, True])
    r = monotonicity(ok, opt=2, t=6)
    assert r["c1"] == r["c1_edges"] == r["c2"] == r["c2_block"] == 0
    assert r["walk_start"] == 6  # the trial itself is feasible


def test_dip_above_the_trial_counts_c1_but_not_c2():
    ok = np.array([False, True, True, True, True, True, True, True, False, True])
    r = monotonicity(ok, opt=1, t=6)
    assert r["c1"] == 1 and r["c1_edges"] == 1  # section 8 infeasible below feasible ones
    assert r["c2"] == 0 and r["c2_block"] == 0  # nothing between the optimum and the walk start


def test_infeasible_section_between_optimum_and_trial_counts_c2():
    ok = np.array([False, False, False, True, False, True, True, True, True, True])
    r = monotonicity(ok, opt=3, t=8)
    assert r["c2"] == 1 and r["c2_block"] == 1  # section 4 blocks the downward walk
    assert r["c1"] == 1 and r["c1_edges"] == 1


def test_infeasible_trial_extends_the_walk_region_to_the_first_feasible_section():
    ok = np.array([False, False, False, True, True, False, True, True, True, True])
    r = monotonicity(ok, opt=3, t=5)  # the trial (5) is infeasible; the walk starts at 6
    assert r["walk_start"] == 6
    assert r["c2"] == 0  # section 4 (between the optimum and the trial) is feasible, so no dip
    assert r["c2_block"] == 1  # but the infeasible trial itself blocks the walk down from 6:
    # the walk stops at 6 and cannot reach the optimum 3 — the plan phrasing (c2) stops at the
    # trial and misses this case, which is why both counts are reported


def test_trial_lighter_than_optimum_has_empty_between_regions():
    ok = np.array([False, False, True, True, True, True, True, True, True, True])
    r = monotonicity(ok, opt=2, t=0)  # the trial is lighter than the optimum (fallback never used)
    assert r["c2"] == 0 and r["c2_block"] == 0 and r["walk_start"] == 2


# ---------------------------------------------------------------- the F1 action graph
def test_f1_distances_on_a_synthetic_catalogue():
    series = ["A1", "A1", "A2", "A2", "B1", "B1"]
    h = np.array([100.0, 100.0, 100.0, 100.0, 200.0, 200.0])
    d = f1_distances(series, h)
    assert d.shape == (6, 6) and d.dtype == int
    assert (np.diag(d) == 0).all()
    assert d[0, 1] == 1 and d[0, 4] == 1  # mass step and series jump to the next deeper series
    assert d[0, 5] == 2 and d[0, 2] == 2  # A2 is not a direct deeper-series target of A1
    assert d[0, 3] == 2  # 0 -> 4 (deeper series) -> 3 (one mass step down)
    assert d[4, 2] == 1  # jump to the lightest shallower series (A2, depth 100 < 200)
    assert d[5, 0] == 3


def test_f1_distances_on_the_catalogue_are_shortest_paths(K, f1_d):
    n = K.n
    assert f1_d.shape == (n, n)
    assert (np.diag(f1_d) == 0).all() and (f1_d >= 0).all()
    assert (f1_d < n).all()  # the mass edges connect every section in both directions
    for i in range(n):
        for j in range(n):
            assert f1_d[i, j] <= abs(i - j)  # the mass walk is always available
            assert (f1_d[i, j] == 0) == (i == j)
    # triangle inequality of shortest paths (the series jumps are directed, symmetry is not required)
    rng = np.random.default_rng(7)
    for _ in range(50):
        i, j, k = rng.integers(0, n, 3)
        assert f1_d[i, j] <= f1_d[i, k] + f1_d[k, j]


def test_series_jump_reaches_any_section_in_its_series(K, f1_d):
    first = {}
    for i, s in enumerate(K.cat.series):
        first.setdefault(s, i)
    for s, i0 in first.items():
        assert f1_d[i0, i0] == 0
        assert all(f1_d[i0, j] == 1 for j in range(i0 + 1, K.n)
                   if K.cat.series[j] == s and j == i0 + 1)  # only the adjacent member is 1 step away


# ---------------------------------------------------------------- per-context diagnostics
def test_diagnose_agrees_with_the_checker_and_the_enumeration(K, sample_contexts, f1_d):
    n_feasible = 0
    for ctx in sample_contexts:
        e = K.evaluate_context(ctx)
        ok = e["feasible"]
        opt = int(np.argmax(ok)) if ok.any() else -1
        out = diagnose(K, ctx, f1_d, e=e)
        assert out["opt"] == opt and out["n_feasible"] == int(ok.sum())
        if opt < 0:
            assert "trial" not in out
            continue
        n_feasible += 1
        # the governing check and utilisation come from Checker.check with the context's config:
        # they must agree with the U matrix of the enumeration pass
        assert out["governing"] in CHECKS
        assert out["u_opt"] == pytest.approx(float(e["U"][opt].max()), abs=1e-9)
        assert 0 <= out["f1_distance"] <= abs(out["trial"] - opt)
        assert out["f1_distance"] == 0 if out["trial"] == opt else out["f1_distance"] > 0
        assert out["n_within5"] >= 1 and 0 <= out["n_depth50"] <= out["n_within5"]
        assert out["c1"] in (0, 1) and out["c2_block"] in (0, 1)
    assert n_feasible >= 1


def test_diagnose_reuses_the_enumeration_pass(K, sample_contexts, f1_d):
    for ctx in sample_contexts[:5]:
        e = K.evaluate_context(ctx)
        assert diagnose(K, ctx, f1_d, e=e) == diagnose(K, ctx, f1_d)  # e=None reruns, same result
