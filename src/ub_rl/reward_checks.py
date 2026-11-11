"""P9 reward families and the per-context ordering assertion (spec sections 9 and 12, change 5).

One line per family (all rewards use log-mass, so a difference equals a relative mass gap; every
arithmetic step is float64 log-space and nothing is exponentiated):
  R1  terminal-sparse: accepting a feasible section gives -ln(m/m_trial), an infeasible one
      -ln(m_max/m_trial) - 1, plus a step cost 0.001 per step
  R2  potential-based shaping on R1: F = Phi(s') - Phi(s) with Phi = -ln(m/m_trial)
      - 2*max(0, max utilisation - 1), Phi(terminal) = 0, discount 1, so the shaped return is the
      R1 return minus the context-constant Phi(s0)
  R3  reward-proportional (F2): log R = -beta*ln(m/m_trial) if feasible, else
      -beta*ln(m_max/m_trial) - 10; beta in {25, 50, 100}, selected on V
  R-C Lagrangian: the environment reward is R1 unchanged (the penalty lambda*c enters the training
      loss, not the reward); feasibility is judged on verified output, never on the penalised objective
  R-D call-penalized: R1 with step cost kappa per checker call, kappa*N_max <= 0.5 with N_max the
      maximum calls per episode, so the margin of 1 is preserved

Ordering property asserted (spec section 9 "A check asserts ...", Gate 3 of section 12): for every
validation context and every family, the smallest return over all feasible candidates exceeds the
largest return over all infeasible candidates (strictly, in float64). A candidate is a
(section, calls used) pair with calls in [0, N_MAX] (the spec's own worst case: "with at most 12
steps the total step cost is at most 0.012", amended by A3 to at most 13 steps and 0.013); R3 candidates carry no step cost. A context with no
feasible candidate or no infeasible candidate makes the assertion vacuous and is counted, not
failed. This module needs enumeration feasibility only: no training, no RL. The constants (beta,
kappa, N_MAX) are frozen at Gate 4; here the family property is asserted over their admissible
ranges.
"""
import numpy as np

from .baselines import trial_index

REWARD_FAMILIES = ("R1", "R2", "R3", "R-C", "R-D")
N_MAX = 13                # F1 horizon in steps (spec section 9, amended 12 -> 13 by A3, 2026-11-11)
STEP_COST_R1 = 0.001      # R1 step cost per step (spec section 9)
KAPPA_RD = 0.5 / N_MAX    # R-D boundary of its admissible range kappa*N_max <= 0.5 (spec change 5); = 0.5 exactly at N_MAX
R3_BETAS = (25, 50, 100)  # R3 inverse temperatures, selected on V (spec section 9)


def margin_bound(family, beta=None):
    """Analytic lower bound of (min feasible return - max infeasible return) per family, from the
    definitions in spec section 9 and change 5 (the observed margin is the bound plus
    ln(m_max / m_heaviest_feasible) >= 0)."""
    if family == "R3":
        return 10.0
    if family == "R-D":
        return 1.0 - KAPPA_RD * N_MAX
    return 1.0 - STEP_COST_R1 * N_MAX  # R1, R2, R-C


def _keys():
    return [f for f in REWARD_FAMILIES if f != "R3"] + [f"R3-b{b}" for b in R3_BETAS]


def context_ordering(lnm, ok, u_trial, ln_trial, ln_max):
    """Per-family (min feasible return, max infeasible return, margin) for one context. lnm is
    np.log of the section masses in kg/m (float64), ok the feasibility mask, u_trial the trial
    section's maximum utilisation (for R2's Phi(s0)), ln_trial and ln_max the log masses of the
    F1 trial section and the heaviest section of C. Returns None when the assertion is vacuous
    (no feasible candidate or no infeasible candidate). The step-cost term uses the worst case:
    calls = N_MAX on the feasible side, calls = 0 on the infeasible side."""
    if not (ok.any() and (~ok).any()):
        return None
    ln_hf = float(lnm[ok].max())  # heaviest feasible section: the worst feasible terminal reward
    out = {}
    # R1 / R-C: -ln(m/m_trial) feasible, -ln(m_max/m_trial) - 1 infeasible, step cost 0.001 per step.
    for fam in ("R1", "R-C"):
        min_f = -(ln_hf - ln_trial) - STEP_COST_R1 * N_MAX
        max_i = -(ln_max - ln_trial) - 1.0 - STEP_COST_R1 * 0.0
        out[fam] = (min_f, max_i, min_f - max_i)
    # R2: shaped return = R1 return - Phi(s0) with Phi(s0) = -2*max(0, u_trial - 1); the shift is
    # context-constant, so the ordering carries over (computed numerically in float64).
    phi0 = -2.0 * max(0.0, u_trial - 1.0)
    min_f, max_i, _ = out["R1"]
    out["R2"] = (min_f - phi0, max_i - phi0, (min_f - phi0) - (max_i - phi0))
    # R3: log R = -beta ln(m/m_trial) feasible, -beta ln(m_max/m_trial) - 10 infeasible, no step cost.
    for beta in R3_BETAS:
        b = float(beta)
        min_f = -b * (ln_hf - ln_trial)
        max_i = -b * (ln_max - ln_trial) - 10.0
        out[f"R3-b{beta}"] = (min_f, max_i, min_f - max_i)
    # R-D: R1 with step cost kappa per checker call, kappa*N_max <= 0.5.
    min_f = -(ln_hf - ln_trial) - KAPPA_RD * N_MAX
    max_i = -(ln_max - ln_trial) - 1.0 - KAPPA_RD * 0.0
    out["R-D"] = (min_f, max_i, min_f - max_i)
    return out


def assert_ordering(checker, contexts):
    """Assert, for every given (validation) context and every family, that the smallest feasible
    candidate return exceeds the largest infeasible candidate return, in float64 log-space.
    Feasibility comes from one enumeration pass per context over the checker's catalogue. Returns
    a report dict with one row per family (R3 one row per beta); raises AssertionError on any
    violation of the strict ordering or of the analytic margin bound."""
    lnm = np.log(np.asarray(checker.mass, dtype=np.float64))
    ln_max = float(lnm[-1])
    rows = []
    for family in REWARD_FAMILIES:
        for beta in (R3_BETAS if family == "R3" else (None,)):
            rows.append({"family": family, "beta": "" if beta is None else str(beta),
                         "key": f"{family}-b{beta}" if beta is not None else family,
                         "n": 0, "n_nonvacuous": 0, "n_vacuous": 0,
                         "min_margin": float("inf"), "max_margin": float("-inf"),
                         "margin_bound": margin_bound(family, beta), "violations": 0})
    for ctx in contexts:
        e = checker.evaluate_context(ctx)
        t = trial_index(checker, ctx)
        r = context_ordering(lnm, e["feasible"], float(e["U"][t].max()), float(lnm[t]), ln_max)
        for row in rows:
            row["n"] += 1
            if r is None:
                row["n_vacuous"] += 1
                continue
            _, _, margin = r[row["key"]]
            row["n_nonvacuous"] += 1
            row["min_margin"] = min(row["min_margin"], margin)
            row["max_margin"] = max(row["max_margin"], margin)
            if not margin > 0.0:
                row["violations"] += 1
    bad = []
    for row in rows:
        holds = row["n_nonvacuous"] == 0 or row["min_margin"] >= row["margin_bound"] - 1e-9
        row["pass"] = int(row["violations"] == 0 and holds)
        if row["violations"] or not holds:
            bad.append(row)
    if bad:
        raise AssertionError(f"reward ordering violated: {bad}")
    return {"n_contexts": len(contexts), "rows": rows}
