"""P9 landscape diagnostics over the mass-ordered catalogue C (spec sections 9 and 12; patch plan P9).

One line each:
  feasibility mask  per section, True where every check passes and the depth cap holds (checker)
  optimum           the lightest feasible section in mass order; -1 = abstain (spec section 7)
  monotonicity counter  two counts over the mask: c1 counts contexts where a lighter section is
                        feasible while a heavier one below it is not; c2 counts contexts with an
                        infeasible section between the optimum and the heuristic's trial section,
                        and c2_block the same between the optimum and the first feasible section at
                        or above the trial (the stretch the heuristic's downward walk must pass)
  F1 horizon check  fewest F1 actions from the trial section to the optimum (mass step up/down,
                    lightest section of the next deeper/shallower series; accept terminates and is
                    not counted; no-ops past the ends cost a step but never shorten a path, so they
                    are not edges), spec section 9, "Gate 3 verifies ... within 13 steps" (A3, amended from 12)
  governing check   which utilisation limit acts at the optimum, from the checker's own
                    Checker.check with the context's config applied (not a reimplementation)
  alternatives      feasible sections within 5 % of the optimal mass, and of those the ones
                    differing in depth by at least 50 mm (spec section 9 diversity counts)

The module reads the verified Checker and the unchanged baselines (baselines.trial_index); nothing
here trains, changes the checker, or changes the physics, objective or assumptions.
"""
import numpy as np

from .baselines import trial_index
from .context import DEFLECTION_RULES

HORIZON_F1 = 13  # F1 horizon in steps (spec section 9, amended 12 -> 13 by A3, 2026-11-11); the check is a result, never changed here


def f1_distances(series, h):
    """All-pairs fewest-F1-action counts over the catalogue: d[i, j] is the smallest number of
    actions (mass step up/down, move to the lightest section of the next strictly deeper or
    strictly shallower series) that take the section pointer from i to j. `series` are the
    catalogue's series designations ("457x191"), `h` the section depths in mm; series are ordered
    by (depth, first mass-order index). Returns an int array (n, n) with d[i, i] = 0."""
    n = len(series)
    first_of = {}
    for i, s in enumerate(series):
        first_of.setdefault(s, i)
    order = sorted(first_of, key=lambda s: (h[first_of[s]], first_of[s]))
    depth = {s: h[first_of[s]] for s in order}
    next_deeper, prev_shallower = {}, {}
    for k, s in enumerate(order):
        deeper = [s2 for s2 in order[k + 1:] if depth[s2] > depth[s]]
        shallower = [s2 for s2 in order[:k] if depth[s2] < depth[s]]
        next_deeper[s] = first_of[deeper[0]] if deeper else None
        prev_shallower[s] = first_of[shallower[-1]] if shallower else None
    adj = [[] for _ in range(n)]
    for i, s in enumerate(series):
        if i > 0:
            adj[i].append(i - 1)
        if i < n - 1:
            adj[i].append(i + 1)
        for j in (next_deeper[s], prev_shallower[s]):
            if j is not None:
                adj[i].append(j)
    D = np.full((n, n), n, dtype=int)  # larger than any real distance (the graph is connected)
    for start in range(n):
        dist = np.full(n, n, dtype=int)
        dist[start] = 0
        frontier = [start]
        while frontier:
            next_frontier = []
            for u in frontier:
                for v in adj[u]:
                    if dist[v] > dist[u] + 1:
                        dist[v] = dist[u] + 1
                        next_frontier.append(v)
            frontier = next_frontier
        D[start] = dist
    return D


def monotonicity(ok, opt, t):
    """The P9 monotonicity counter for one feasible context (opt >= 0): c1 = a lighter section is
    feasible while a heavier one below it is not (any pair, plus the adjacent-edge count c1_edges);
    c2 = an infeasible section lies strictly between the optimum and the trial section (the patch
    plan's phrasing); c2_block = the same between the optimum and the first feasible section at or
    above the trial, which is exactly the stretch the heuristic's downward walk must pass (c2_block
    = 0 means the feasible block from the optimum up to the walk start is contiguous, so the walk
    reaches the optimum structurally)."""
    j0 = int(np.argmax(ok[t:])) + t if ok[t:].any() else len(ok)
    return {
        "c1": int(np.triu(ok[:, None] & ~ok[None, :], 1).any()),
        "c1_edges": int((ok[:-1] & ~ok[1:]).sum()),
        "c2": int((~ok[opt + 1:t]).any()),
        "c2_block": int((~ok[opt + 1:j0]).any()),
        "walk_start": j0,
    }


def diagnose(checker, ctx, f1_d, e=None):
    """One context's P9 diagnostics: feasibility mask, optimum, trial index, F1 distance from the
    trial to the optimum, the monotonicity counter, alternatives, and the governing check of the
    optimum from the checker's own Checker.check with the context's config applied. `f1_d` is
    f1_distances(checker.cat.series, checker.h); `e` is an optional earlier evaluate_context result
    (the enumeration pass) so the context is not evaluated twice. Abstain contexts (no optimum)
    report opt = -1 and skip the optimum-dependent fields."""
    if e is None:
        e = checker.evaluate_context(ctx)
    ok = e["feasible"]
    opt = int(np.argmax(ok)) if ok.any() else -1
    out = {"opt": opt, "n_feasible": int(ok.sum())}
    if opt < 0:
        return out
    t = trial_index(checker, ctx)
    out.update({"trial": t, "f1_distance": int(f1_d[t, opt])})
    out.update(monotonicity(ok, opt, t))
    m_opt = checker.mass[opt]
    within5 = ok & (checker.mass <= 1.05 * m_opt)
    out["n_within5"] = int(within5.sum())
    out["n_depth50"] = int((within5 & (np.abs(checker.h - checker.h[opt]) >= 50.0)).sum())
    w, phi = ctx.factored_udl(checker.cfg.gamma_G, checker.cfg.gamma_Q)
    mode, ratio = DEFLECTION_RULES[ctx.deflection_rule]
    Kc = checker.with_config(variable_share=phi, restraint_ratio=ctx.restraint_ratio,
                             deflection_load=mode, deflection_ratio=ratio)
    cr = Kc.check(ctx.span, w, opt)
    out["governing"] = cr.governing
    out["u_opt"] = cr.max_utilisation
    return out
