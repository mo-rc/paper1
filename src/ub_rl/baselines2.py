"""Stage 1 baselines II (patch P8): the categorical-native genetic algorithm (spec section 9 as trimmed by
Amendment A5). No RL.

GA definition (plan docs/p8_plan.md section 2, every choice recorded there):
  chromosome   k genes, each a section index into the mass-ordered catalogue C; the design of a chromosome is
               its lightest feasible gene
  initial      p full chromosomes, each gene drawn uniformly from the unseen sections
  crossover    uniform: per gene position the child's allele is parent A's or parent B's with probability 1/2
  mutation     per gene with probability m the allele becomes a uniformly drawn unseen section
  selection    tournament of size t on fitness; elitism e carries the best individual at cost 0
  fitness      feasible sections by mass (lightest best, ties by smaller index); infeasible sections below
               every feasible one by utilisation overrun max(0, U_max - 1), least first, then mass (the run
               summary records that the GA's fitness uses utilisation overrun for infeasible sections)
  budget       a run makes exactly `budget` distinct section evaluations: a section already evaluated in this
               run costs 0 - it is never re-evaluated - and its slot is redrawn from the unseen sections; the
               final partial batch evaluates only the remaining budget genes. Budget |C| = 91 therefore
               evaluates every section and equals the enumeration optimum by construction - a cost data point,
               not a GA-quality result (recorded in the run summary)
  output       the lightest feasible section among all evaluated, -1 (abstain) if none is feasible
  determinism  one random.Random(f"{seed}|{config.id}|{context_id}") per run drives every draw - the same
               NumPy-version-independent device P7 used for random orders (src/ub_rl/baselines.py)

Call accounting as in P7: the vectorised population evaluations are the counted checker calls (measured by
the CountingChecker, never the GA's own arithmetic); the run's verification call (spec section 9 end-to-end)
is reported separately by the run script.

Tuning selection (Amendment A5, recorded in the meta by the run): the first drawn configuration is the
default; a later configuration replaces the current best only if the V mean gap improves by at least 0.5
percentage points with feasibility not lower, applied in draw order. `select_config` implements the rule for
both the GA and the MLP; gap = infinity when a configuration outputs no design on V.
"""
import random
from dataclasses import dataclass

import numpy as np

from ub_rl.baselines import MethodResult, _Calls

GA_BUDGETS = (20, 91)        # spec section 9, trimmed by A5: budgets 20 and |C|
GA_SEEDS = tuple(range(10))  # spec section 9: seeds 0-9
GA_TUNE_SEEDS = (0, 1, 2)    # A5: tuning runs seeds 0-2
TUNING_GAP_MARGIN_PP = 0.5   # A5: a replacement needs >= 0.5 percentage points of V mean-gap improvement
TUNING_RULE = ("the first drawn configuration is the default; a later configuration replaces the current "
               "best only if the V mean gap improves by at least 0.5 percentage points with feasibility not "
               "lower, applied in draw order")


@dataclass(frozen=True)
class GAConfig:
    id: int   # position in the draw order (the first drawn, id 0, is the tuning default)
    p: int    # population size
    k: int    # genes per chromosome
    t: int    # tournament size
    m: float  # mutation probability per gene
    c: float  # crossover probability
    e: int    # elitism: 1 carries the best individual into the next generation at cost 0


def ga_config_grid():
    """The fixed parameter grid (plan section 2) in the fixed product order the draw samples from."""
    return [(p, k, t, m, c, e)
            for p in (2, 4, 5, 10, 20) for k in (1, 2, 4, 8) for t in (2, 3, 4)
            for m in (0.05, 0.1, 0.2, 0.5) for c in (0.5, 1.0) for e in (0, 1)]


def draw_ga_configs():
    """The 12 tuning configurations, drawn by a fixed seed from the fixed grid (spec section 9: "drawn by a
    fixed seed"). Deterministic and asserted by a test."""
    rng = random.Random("ga-configs-2026-11-15")
    return [GAConfig(i, *cfg) for i, cfg in enumerate(rng.sample(ga_config_grid(), 12))]


def select_config(scores):
    """Amendment A5 tuning rule, shared by the GA and the MLP. `scores` is the list of (mean_gap, feasibility)
    per configuration in draw order; mean_gap = float('inf') when the configuration outputs no design on V.
    Feasibility is the share of V rows with a feasible output."""
    current = 0
    for i in range(1, len(scores)):
        gap_i, feas_i = scores[i]
        gap_c, feas_c = scores[current]
        if gap_i + TUNING_GAP_MARGIN_PP <= gap_c + 1e-9 and feas_i >= feas_c:
            current = i
    return current


def ga(kc, ctx, budget, seed, context_id, config):
    """Categorical-native GA: uniform crossover, random-section mutation, exactly `budget` distinct section
    evaluations (a section already evaluated in this run costs 0 and the slot is redrawn from the unseen
    sections). Returns the lightest feasible section among the evaluated ones, -1 if none."""
    c = _Calls(kc)
    n = len(kc)
    rng = random.Random(f"{seed}|{config.id}|{context_id}")
    seen = {}    # section -> feasibility (memoised; a seen section is never re-evaluated)
    drawn = set()  # sections reserved by fresh() but not yet evaluated: keeps every evaluated gene distinct
    overun = {}  # section -> utilisation overrun max(0, U_max - 1), the infeasible ranking key

    def evaluate_pool(genes):
        idx = np.asarray(genes, dtype=int)
        e = kc.evaluate_context(ctx, idx)  # one vectorised call, counts len(genes)
        umax = e["U"].max(axis=1)
        for i, ok, ov in zip(idx.tolist(), e["feasible"].tolist(), umax.tolist()):
            seen[i] = bool(ok)
            overun[i] = max(0.0, float(ov) - 1.0)

    def fresh():
        while True:
            i = int(rng.random() * n)
            if i not in seen and i not in drawn:
                drawn.add(i)
                return i

    def gene_key(i):
        if seen[i]:
            return (0, -float(kc.mass[i]), -i)
        return (1, overun[i], -float(kc.mass[i]), -i)

    def ind_key(genes):
        return min(gene_key(g) for g in genes)

    def tournament(pop):
        best = pop[0]
        for _ in range(config.t - 1):
            cand = pop[int(rng.random() * len(pop))]
            if ind_key(cand) < ind_key(best):
                best = cand
        return best

    def breed(pop, n_children):
        children = []
        for _ in range(n_children):
            a = tournament(pop)
            if rng.random() < config.c:
                b = tournament(pop)
                child = [a[j] if rng.random() < 0.5 else b[j] for j in range(config.k)]
            else:
                child = list(a)
            for j in range(config.k):
                if rng.random() < config.m:
                    child[j] = fresh()
            children.append(tuple(g if g not in seen else fresh() for g in child))
        return children

    evaluated = 0
    pop = []
    best = None
    for _ in range(min(config.p, budget // config.k)):
        chrom = [fresh() for _ in range(config.k)]
        evaluate_pool(chrom)
        evaluated += config.k
        pop.append(tuple(chrom))
    if pop:
        best = min(pop, key=ind_key)
    while evaluated < budget:
        slots = budget - evaluated
        if slots < config.k:
            chrom = [fresh() for _ in range(slots)]  # the final partial batch: only the remaining budget genes
            evaluate_pool(chrom)
            evaluated += slots
            continue
        children = breed(pop, slots // config.k)
        for chrom in children:
            evaluate_pool(list(chrom))
            evaluated += config.k
        if config.e == 1 and best is not None:
            children.append(best)  # carried at cost 0
        pop = children
        best = min(pop, key=ind_key)
    out = [i for i in seen if seen[i]]
    if out:
        opt = min(out, key=lambda i: (float(kc.mass[i]), i))
        return MethodResult("feasible", opt, c.calls())
    return MethodResult("abstain", -1, c.calls())
