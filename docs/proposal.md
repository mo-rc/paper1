# Reinforcement Learning for Safe, Automated Design of Steel Beams

**Eurocode 3 (UK NA) verified design, from standard UK Universal Beams to custom welded I-sections**

**Repository:** https://github.com/mo-rc/paper1  (Eurocode checker, catalogue parser, tests)
**Output:** one journal paper, aimed at a top-tier journal (title to be finalized after the results)
**Date:** 19 October 2026

---

## 1. Aim

Design the lightest steel I-beam that passes every Eurocode 3 check, automatically, for any new span, load and restraint condition, using a trained reinforcement learning (RL) policy instead of repeating a search for each problem.

Every design the policy proposes is checked by an independent Eurocode solver. An unsafe design is never counted as a success.

We claim RL is better only where tests show it is. Where simpler methods already do the job, we say so.

## 2. Why this matters

Beam design is a loop: choose a section, run the code checks, adjust. Genetic algorithms and gradient-based solvers automate the loop, but they start from scratch for every new problem. A trained policy pays its cost once and then answers new problems in one or two checks. Whether this really pays off against strong conventional methods, and under which conditions, has not been tested rigorously for code-compliant steel design.

## 3. Contributions of the paper

1. **A verified, open Eurocode 3 environment** for beam design (LTB, web bearing, shear buckling, interaction), with tests, independent re-implementation and Blue Book comparison.
2. **A pre-registered benchmark** of RL against enumeration, heuristic iteration, GA, DE, supervised learning and, for custom sections, SLSQP and CMA-ES, with cost counted in checker calls including training.
3. **A map of when learned design wins**: safety, generalization, quality and break-even cost, in cheap-check and expensive-check regimes.
4. **Amortized generative design of welded I-sections**, with hybrid RL + optimizer results.

The catalogue study (Stage 1) is the controlled testbed with a known exact optimum. The custom-section study (Stage 2) carries the main result. Both are reported in the one paper.

## 4. Research questions

1. **Safety:** does the policy produce designs that pass every code check?
2. **Generalization:** does it work on spans, loads and restraint conditions it has never seen?
3. **Quality:** how close is its section to the lightest feasible one?
4. **Efficiency:** what does it cost per design, and after how many designs does training pay for itself?
5. **Diversity:** can it return several distinct, near-optimal, safe designs?

## 5. Design problem

| Item | Definition |
|---|---|
| Member | Simply supported I-beam, S355, UDL |
| Code | EN 1993-1-1 and EN 1993-1-5 with UK National Annexes; EN 1990 (factors 1.35 dead, 1.5 live) |
| Checks | Classification, bending, shear, bending-shear interaction, shear buckling, web bearing, lateral-torsional buckling (LTB), deflection |
| Catalogue (Stage 1) | 91 UK Universal Beams in BS EN 10365 (Blue Book table, 107 rows; the 16 "+" rows as a sensitivity test) |
| Custom sections (Stage 2) | Welded symmetric I-sections, S355, plates in fabrication increments |
| Reference case | 9 m span, 6 m tributary width, 3.675 kN/m² dead, 3.0 kN/m² live, factored 56.77 kN/m; expected lightest UB 457×191×74 |
| Objective | Minimum mass among sections that pass every check |

**Seven context parameters** (the policy must generalize across them): span, tributary width, dead load, live load, lateral restraint spacing (Lcr/L), deflection rule, depth limit.

## 6. Method

**Verification engine.** A tested, vectorized Eurocode 3 checker (in the repository), extended with LTB, the seven-parameter contexts, and a welded-section version for Stage 2. It is verified by a separate implementation, hand calculations, and the Blue Book resistance tables before any RL training.

**Stage 1: catalogue selection.** Discrete choice among 91 sections. Formulations: direct choice, and step-by-step refinement of a trial section using the utilisation of each check. Algorithms are compared in a tournament under equal tuning effort: DQN, Double DQN, Dueling Double DQN, discrete PPO, discrete SAC, policy gradient.

**Stage 2: custom welded sections.** Continuous or increment-based design of h, b, tw, tf. Algorithms: SAC, TD3, DDPG, PPO, branching dueling Q-networks, and hybrids where the policy warm-starts an optimizer.

**Rewards.** Four families are compared on validation data: reference-relative, potential-based shaping, constrained (Lagrangian), and call-penalized. In all of them a safe design always scores higher than an unsafe one.

**Baselines (same checker, same cost accounting).** Exhaustive enumeration (exact optimum), heuristic iteration (conventional manual design), random search, genetic algorithm, differential evolution, a supervised classifier, and for Stage 2 also SLSQP and CMA-ES.

**Fair comparison.** Separate training, validation and test contexts fixed before training; held-out interior block, unseen restraint values and extrapolation sets; ten random seeds; Holm-corrected exact tests with practical margins, and non-inferiority tests for custom sections; cost counted in checker calls, training and tuning included. All results in the paper come from saved runs.

## 7. What counts as success

RL is claimed to win only if it meets one of these, fixed in advance:

- **Custom sections (non-inferiority):** mass no more than 2 percentage points above the best per-problem optimizer, tested with a non-inferiority test; safe in at least 99 % of tests; and at least 10× cheaper per design.
- **Learning from feedback:** beats a supervised classifier given the same total checker-call budget.
- **Expensive verification (finite-element-type checks):** needs fewer checks per design than heuristic iteration.
- **Hybrid:** warm-starting an optimizer reaches the same design with at least 30 % fewer evaluations.

If none is met, the paper's contribution is the verified environment and the benchmark that maps when learned design is and is not worth it.

## 8. Tasks and timeline (about 28 weeks)

| Work package | Weeks | Output |
|---|---|---|
| **1. Foundations** | 1–3 | Literature search, confirmed assumptions |
| **2. Verification engine** | 3–8 | Checker with LTB and seven-parameter contexts; verification report |
| **3. Baselines and audit** | 8–10 | Exact optima, conventional methods, feasibility audit, frozen test sets |
| **4. Stage 1 RL** | 10–16 | Tournament results, generalization and cost analysis |
| **5. Stage 2 welded sections** | 12–24 | Welded-section checker, RL vs optimizers, hybrid results |
| **6. Application and verification** | 20–26 | Web app (inputs → verified designs → report); Abaqus check of about 10 designs |
| **7. Paper** | 22–28 | One journal manuscript, code and data released |

**Rule:** no RL training until the checker passes verification.

## 9. Deliverables

1. Open, verified Eurocode 3 beam-checking code with tests.
2. RL environments, trained policies, benchmark data and analysis code.
3. Prototype design application that shows several verified designs and a report.
4. One journal paper.

## 10. Scope and assumptions

**In scope:** single simply supported beams, S355, UDL (other load patterns as extensions), catalogue and welded I-sections.

**Out of scope:** connections, composite action, fire, vibration, frames, topology optimization, cost and life-cycle analysis.

**Assumptions to confirm:** 1.35/1.5 load factors; self-weight included in the checks; deflection limits L/360 (variable load, primary) with L/200 and L/250 as variants; bearing length 100 mm; LTB with load at the shear centre (top-flange loading as a variant); Class 4 sections treated as unsafe in Stage 1; fy reduced by plate thickness (355, 345, 335, 325 N/mm²).
