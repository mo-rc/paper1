"""P9: reward families and the float64 log-space ordering assertion (spec sections 9 and 12).

The assertion says: per validation context and per family (R1, R2, R3, R-C, R-D), the smallest
return of any feasible candidate exceeds the largest return of any infeasible candidate. Synthetic
masks test the analytic margins exactly; sampled val contexts test the assertion against the
verified checker. Skips without the workbook (conftest).
"""
from pathlib import Path

import numpy as np
import pytest

from ub_rl import reward_checks as RC
from ub_rl import splits as S
from ub_rl.checker import Checker

ROOT = Path(__file__).resolve().parent.parent

N = 10  # sections in the synthetic catalogue: masses 1..10 kg/m
LNM = np.log(np.arange(1.0, N + 1.0, dtype=np.float64))
LN_MAX = float(LNM[-1])


@pytest.fixture(scope="module")
def K(C):
    return Checker(C)


@pytest.fixture(scope="module")
def val_contexts():
    _, ctxs = S.load_split("val", root=ROOT / "data" / "splits")
    return ctxs[:20]


# ---------------------------------------------------------------- synthetic masks (no checker)
def test_heaviest_feasible_margin_is_exactly_the_bound():
    ok = np.array([False, False, True] + [True] * 7)  # heaviest section feasible -> ln(m_max/m_hf) = 0
    r = RC.context_ordering(LNM, ok, 0.5, float(LNM[2]), LN_MAX)
    bound_r1 = 1.0 - RC.STEP_COST_R1 * RC.N_MAX
    for key in ("R1", "R2", "R-C"):
        assert r[key][2] == pytest.approx(bound_r1, abs=1e-12)
    assert r["R-D"][2] == pytest.approx(1.0 - RC.KAPPA_RD * RC.N_MAX, abs=1e-12)
    for beta in RC.R3_BETAS:
        assert r[f"R3-b{beta}"][2] == pytest.approx(10.0, abs=1e-12)


def test_margin_adds_the_log_mass_ratio_of_the_heaviest_infeasible_to_the_heaviest_feasible():
    ok = np.array([False, False, True, True, True, True, True, True, False, False])  # m_hf = 8, m_max = 10
    r = RC.context_ordering(LNM, ok, 0.5, float(LNM[1]), LN_MAX)
    gap = float(np.log(10.0 / 8.0))
    assert r["R1"][2] == pytest.approx(1.0 + gap - RC.STEP_COST_R1 * RC.N_MAX, abs=1e-12)
    assert r["R3-b25"][2] == pytest.approx(10.0 + 25.0 * gap, abs=1e-12)
    assert r["R3-b100"][2] == pytest.approx(10.0 + 100.0 * gap, abs=1e-12)


def test_r2_shift_is_context_constant_and_preserves_the_ordering():
    ok = np.array([False, False, True, True, True, True, True, True, False, False])
    r = RC.context_ordering(LNM, ok, 1.5, float(LNM[1]), LN_MAX)  # infeasible trial: Phi(s0) = -1.0
    assert r["R2"][0] == pytest.approx(r["R1"][0] + 1.0, abs=1e-12)  # return shifted by -Phi(s0)
    assert r["R2"][2] == pytest.approx(r["R1"][2], abs=1e-12)


def test_vacuous_when_no_feasible_or_no_infeasible_candidate():
    assert RC.context_ordering(LNM, np.ones(N, bool), 0.5, float(LNM[2]), LN_MAX) is None
    assert RC.context_ordering(LNM, np.zeros(N, bool), 0.5, float(LNM[2]), LN_MAX) is None


def test_all_values_finite_float64_log_space():
    ok = np.array([False, False, True, True, True, True, True, True, False, False])
    r = RC.context_ordering(LNM, ok, 1.5, float(LNM[1]), LN_MAX)
    for key, (min_f, max_i, margin) in r.items():
        for v in (min_f, max_i, margin):
            assert isinstance(v, float) and np.isfinite(v)
        assert margin > 0.0


# ---------------------------------------------------------------- the assertion on val contexts
def test_ordering_holds_on_sample_val_contexts(K, val_contexts):
    report = RC.assert_ordering(K, val_contexts)
    assert report["n_contexts"] == len(val_contexts)
    for row in report["rows"]:
        assert row["n"] == len(val_contexts)
        assert row["n_nonvacuous"] + row["n_vacuous"] == len(val_contexts)
        assert row["n_nonvacuous"] >= 1  # val has feasible contexts with infeasible sections
        assert row["violations"] == 0 and row["pass"] == 1
        assert row["min_margin"] >= row["margin_bound"] - 1e-9
        assert row["max_margin"] >= row["min_margin"]


def test_trial_mass_never_exceeds_the_heaviest_section(K, val_contexts):
    from ub_rl.baselines import trial_index
    for ctx in val_contexts:
        t = trial_index(K, ctx)
        assert 0 <= t < K.n
        assert K.mass[t] <= K.mass[-1]


def test_assert_ordering_raises_on_a_violation(K, val_contexts, monkeypatch):
    def fake(lnm, ok, u_trial, ln_trial, ln_max):
        return {key: (0.0, 0.0, -1.0 if key == "R1" else 1.0) for key in RC._keys()}

    monkeypatch.setattr(RC, "context_ordering", fake)
    with pytest.raises(AssertionError, match="reward ordering violated"):
        RC.assert_ordering(K, val_contexts)


def test_assert_ordering_raises_when_the_margin_is_below_the_bound(K, val_contexts, monkeypatch):
    def fake(lnm, ok, u_trial, ln_trial, ln_max):
        return {key: (0.0, 0.0, 0.5) for key in RC._keys()}  # positive but below every bound

    monkeypatch.setattr(RC, "context_ordering", fake)
    with pytest.raises(AssertionError, match="reward ordering violated"):
        RC.assert_ordering(K, val_contexts)
