"""Stage 1 baselines I (patch P7): enumeration, ordered scan, heuristic iteration, random search.

All methods share the verified checker over the mass-ordered catalogue C, the same contexts and the same
objective (spec section 7: minimum mass, ties by smaller depth, then catalogue order). All return a section
index into C or -1 (abstain).

Cost accounting (spec section 10): one checker call is one section evaluation. A vectorised evaluation of k
sections therefore counts as k calls; the CountingChecker wrapper measures the calls actually made, and every
method reports that measured number (its own arithmetic is never trusted). Per spec section 9, the end-to-end
procedure adds one verification call when a design is output and none when the method abstains; that call is
reported separately and is not part of the search calls.

Method definitions (spec section 9):
  enumeration     every section of C evaluated; the lightest feasible section is the exact reference optimum
  ordered scan    sections evaluated in mass order; the first feasible section is the optimum (exact)
  heuristic       trial section = first section in mass order with Wpl >= M_Ed / 355 (w = superimposed
                  factored UDL, fy = 355), step up in mass order until feasible, then down while the
                  next-lighter section stays feasible (conventional manual design)
  random search   a fixed number (budget) of distinct sections, the first ones of a random order that is fixed per
                  (seed, context) and does not depend on the NumPy version; the
                  lightest feasible among them is output. Budget |C| draws the whole catalogue, so it equals
                  enumeration; seeds then do not matter (recorded, not assumed silently).
Feasibility is not monotone in mass order, so the heuristic and random search can return a feasible section
heavier than the enumeration optimum; the gap is a result, not an assumption.
"""
import random
from dataclasses import dataclass

import numpy as np

RANDOM_BUDGETS = (10, 20, 50, 91)  # spec section 9: evaluation budgets 10, 20, 50, |C|
RANDOM_SEEDS = tuple(range(10))  # spec section 9: seeds 0-9
TRIAL_FY = 355.0  # N/mm2, spec section 9: the F1 trial section uses w and fy = 355


@dataclass(frozen=True)
class MethodResult:
    status: str  # "feasible" or "abstain"
    index: int  # position in the mass-ordered catalogue C, -1 if abstain
    calls: int  # checker calls (section evaluations) made by the search


class CountingChecker:
    """Wraps a Checker and counts checker calls (section evaluations) per context evaluation. Attribute
    lookups delegate to the wrapped checker."""

    def __init__(self, checker):
        self._checker = checker
        self.invocations = 0  # evaluate_context calls
        self.sections = 0  # section evaluations (the cost unit of spec section 10)

    def evaluate_context(self, ctx, idx=None):
        self.invocations += 1
        self.sections += len(self) if idx is None else len(np.atleast_1d(np.asarray(idx, dtype=int)))
        return self._checker.evaluate_context(ctx, idx)

    def __len__(self):
        return self._checker.n

    def __getattr__(self, name):
        return getattr(self._checker, name)


class _Calls:
    """Reads the calls made since construction from a CountingChecker (the counter is the source of truth)."""

    def __init__(self, kc):
        self.kc = kc
        self.start = kc.sections

    def calls(self):
        return self.kc.sections - self.start


def enumerate(kc, ctx):
    """Exact reference: lightest feasible section of C, -1 if none (spec section 7 optimum)."""
    c = _Calls(kc)
    e = kc.evaluate_context(ctx)
    opt = int(np.argmax(e["feasible"])) if e["feasible"].any() else -1
    return MethodResult("feasible" if opt >= 0 else "abstain", opt, c.calls())


def ordered_scan(kc, ctx):
    """Sections in mass order, one evaluation each, stop at the first feasible section (exact: the first
    feasible section is the lightest). Abstains after the whole catalogue."""
    c = _Calls(kc)
    for i in range(len(kc)):
        if kc.evaluate_context(ctx, [i])["feasible"][0]:
            return MethodResult("feasible", i, c.calls())
    return MethodResult("abstain", -1, c.calls())


def trial_index(kc, ctx):
    """First section in mass order with Wpl >= M_Ed / fy, using the superimposed factored UDL w and fy = 355
    (spec section 9, F1 trial section). The heaviest section is the fallback when nothing is strong enough."""
    w, _ = ctx.factored_udl()  # kN/m, self-weight excluded
    need = (w * ctx.span ** 2 / 8.0) * 1e6 / TRIAL_FY  # N mm / (N/mm2) = mm3
    W = kc.Wpl  # mm3, in mass order
    i = int(np.argmax(W >= need))
    return i if W[i] >= need else len(kc) - 1


def heuristic(kc, ctx):
    """Conventional manual design: trial section from the required modulus, up in mass order until feasible,
    then down while the next-lighter section stays feasible (spec section 9). A section already evaluated in this
    context is remembered, not evaluated (and not counted) again."""
    c = _Calls(kc)
    n = len(kc)
    seen = {}

    def ok(i):
        if i not in seen:
            seen[i] = bool(kc.evaluate_context(ctx, [i])["feasible"][0])
        return seen[i]

    j = trial_index(kc, ctx)
    while not ok(j) and j < n - 1:
        j += 1
    if ok(j):
        while j > 0 and ok(j - 1):
            j -= 1
        return MethodResult("feasible", j, c.calls())
    return MethodResult("abstain", -1, c.calls())


def random_order(n, seed, context_id):
    """Fixed random order of the n sections for one (seed, context): Fisher-Yates driven by random.Random(...).random(),
    so it does not depend on the NumPy version (the splits use the same device). Every context has its own order;
    prefixes are nested (the sections of budget 10 are the first 10 of budget 20)."""
    rng = random.Random(f"{seed}|{context_id}")
    order = list(range(n))
    for k in range(n - 1, 0, -1):
        j = int(rng.random() * (k + 1))
        order[k], order[j] = order[j], order[k]
    return order


def random_search(kc, ctx, budget, seed, context_id):
    """The first `budget` sections of the (seed, context) random order are evaluated; the lightest feasible one is
    output, -1 if none. Budget |C| evaluates every section (equals enumeration for every seed)."""
    c = _Calls(kc)
    n = len(kc)
    idx = np.array(random_order(n, seed, context_id)[:min(budget, n)], dtype=int)
    ok = idx[kc.evaluate_context(ctx, idx)["feasible"]]
    if len(ok):
        opt = int(ok.min())  # smallest mass-order position = lightest feasible section found
        return MethodResult("feasible", opt, c.calls())
    return MethodResult("abstain", -1, c.calls())
