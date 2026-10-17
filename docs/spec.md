# Specification (pre-registration), Paper 1

Version 1.1. Repository: https://github.com/mo-rc/paper1. Frozen before any run. Changes are dated amendments at the end of this file, made before the affected run.

## 1. Scope

One simply supported steel I-beam of a three-storey building. Standard UK Universal Beams (UB) only, S355 only, no welded or built-up sections. Beam is fully restrained laterally. Primary output: a catalogue section that passes every check, verified by an independent checker.

Research questions:
- RQ1 Safety: does the policy output sections that pass every check?
- RQ2 Generalisation: does it hold on unseen span/load without retraining?
- RQ3 Automation efficiency: per-design and total cost versus enumeration, GA and DE, training included.
- RQ4 Quality: gap to the lightest feasible catalogue section.
- RQ5 Diversity: does a generative policy return several distinct feasible near-optimal sections?

No method is assumed to win. Claims follow section 11.

## 2. Design basis

First-generation Eurocodes with UK National Annexes:
- BS EN 1993-1-1:2005+A1:2014 with NA+A1:2014
- BS EN 1993-1-5:2006 with its NA
- BS EN 1990 with its UK NA (load combinations)
- BS EN 10025-2 (steel), BS EN 10365:2017 (sections)

gamma_M0 = gamma_M1 = 1.0. E = 210,000 N/mm2. Clause numbers and limits in section 6 are checked against publicly available sources (SCI Blue Book and resistance-table notes, Steel for Life, published design guides) at Gate 2; anything not confirmed there is listed in the verification record.

## 3. Loads and context

Reference case (supervisor paper): span 9.0 m, tributary width 6.0 m, dead 3.675 kN/m2, live 3.0 kN/m2, factors 1.35 and 1.5.
- G_k,sup = 22.05 kN/m, Q_k = 18.0 kN/m, w_ref = 1.35*22.05 + 1.5*18.0 = 56.7675 kN/m (quoted 56.77).
- The line load excludes the beam's own weight.

Context (L, w): span L in [9, 15] m, factored superimposed UDL w in [56, 100] kN/m.
- Variable share fixed at the reference value: phi = 27.0 / 56.7675. Q_k = phi*w/1.5.
- Self-weight g = m * 9.80665/1000 kN/m (m = tabulated kg/m), factored by 1.35.
- ULS: w_Ed = w + 1.35 g. M_Ed = w_Ed L^2/8. V_Ed = w_Ed L/2. Support reaction = V_Ed.

## 4. Catalogue

Source: Steel for Life Blue Book, UB section properties and dimensions (Eurocode 3, UK NA, BS EN 10365:2017), downloaded 16/10/2026.
File: `UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx`
SHA-256: `190e17b694bdb27adac2a762738421590394871662236c5df2fb073231740aa8`

- 107 rows; 16 are marked "+" (additional to BS EN 10365).
- Primary candidate set C: the 91 rows without "+". Sensitivity set C+: all 107.
- Parsed values are used as tabulated; none are typed or corrected by hand. Parser reports row count, excluded rows and units.
- Mass objective: tabulated mass per metre times span.
- Raw file is not committed (copyright); its checksum is.

## 5. Material

S355. fy by the maximum element thickness t = max(tf, tw), per EN 10025-2 as specified by the UK NA:
- t <= 16 mm: 355; <= 40: 345; <= 63: 335; <= 80: 325 N/mm2.

epsilon = sqrt(235/fy).

## 6. Required checks

Every check yields a utilisation (demand/resistance). A design is feasible iff all are <= 1.0 (numerical tolerance 1e-9).

| Check | Reference |
|---|---|
| Classification (bending) | EN 1993-1-1 Table 5.2. Class 4 is infeasible and counted. |
| Bending resistance | EN 1993-1-1 6.2.5 |
| Shear resistance | EN 1993-1-1 6.2.6 |
| Bending-shear interaction | EN 1993-1-1 6.2.8 |
| Shear buckling | EN 1993-1-5 section 5 (applies if hw/tw exceeds the code limit) |
| Web bearing / patch loading at supports | EN 1993-1-5 section 6; stiff bearing length ss = 100 mm, load at the beam end, unstiffened web |
| LTB | EN 1993-1-1 6.3.2; continuous restraint, chi_LT = 1 (recorded, not assumed silently) |
| Deflection | EN 1993-1-1 7.2 with UK NA deflection limits |

Deflection (primary): variable load only, delta = 5 Q_k L^4 / (384 E I_y) <= L/360 (beams carrying brittle finishes).
Sensitivities: variable load with L/200; total characteristic load (G_k + g + Q_k) with L/250.

Deflection limits (span/360 brittle finishes, span/200 other beams, on variable load) follow UK practice and the UK NA suggested values as given in public sources. Bearing length ss is a stated assumption. If the feasible set is empty for any context, the range is revised before experiments through a documented feasibility audit.

## 7. Objective and reference

Feasible set F(L, w) = sections in C passing section 6. Optimum = minimum mass in F; ties broken by smaller depth h, then catalogue order.
Reference = exhaustive enumeration over C. It is exact for C and the verified checks only.
Gap = (mass - mass_ref)/mass_ref, in %. Reported only for feasible outputs, always next to feasibility.

## 8. Contexts and splits

Training: contexts sampled uniformly from the box excluding the hole H = {L in [11.5, 12.5], w in [75, 85]}.
Fixed files, generated once by script with these seeds, SHA-256 recorded:
- Validation V: 500 points, box minus H, seed 101. Used for checkpoint and hyperparameter selection only.
- T1 interpolation: 2,000 points, box minus H, seed 202.
- T2 hole: 500 points in H, seed 303.
- T3 extrapolation (reported separately): E1 L in (15, 18], w in [56, 100]; E2 L in [9, 15], w in (100, 130]; E3 both; 500 points each, seed 404.
- Reference case (9 m, 56.7675) reported separately.

Test files are not touched during tuning.

## 9. Methods

All methods use the same checker, catalogue C, objective and contexts.

Design variable type: each UB is a fixed rolled section (h, b, tw, tf, r are tabulated together), so the choice is categorical over C. Continuous dimensions would describe custom or welded sections, which are out of scope.

RL formulations (state includes normalised L and w):
- F1 Refinement MDP: a rule-based trial section (first section in mass order with Wpl above the required value) is revised step by step. Observation: context, current section geometry and mass, and the utilisation of every check. Actions: one mass step up or down, one depth series up or down, accept. Horizon at most 12 steps.
- F2 Constructive MDP: the section is built in two choices, depth series then variant within the series.

Algorithms (PPO, SAC, TD3 and DDPG are not used here):
- Dueling Double DQN with prioritised replay, on F1.
- Conditional GFlowNet (trajectory balance), on F2. It samples sections with probability proportional to reward, which gives diverse designs.

Reward modes (the Lagrangian, feasibility-gated and shaped modes of the earlier project are not reused):
- R1 Terminal-sparse with safety termination: accepting a feasible section gives -m/m_trial; an infeasible acceptance ends the episode with a fixed penalty larger in magnitude than any feasible value; step cost 0.01. No shaping.
- R2 Potential-based shaping: R1 plus F(s,s') = gamma*Phi(s') - Phi(s), with Phi = -m/m_trial - 2*max(0, max utilisation - 1). Shaping preserves the optimal policy.
- R3 Reward-proportional: R(x) = exp(-beta*m/m_trial) if feasible, 1e-6 otherwise; beta in {10, 20, 40}, selected on V.

Configurations: DDQN-R1, DDQN-R2, GFlowNet-R3; seeds 0-4; 15 runs. Training budget: 200,000 checker calls per run (every step counts). Greedy output (arg max) is the policy output for S1 and S2; sampled output is reported separately.

Baselines:
- Enumeration (reference; also timed).
- GA and DE on the integer index in mass-ascending order; evaluation budgets 10, 20, 50, |C| calls per context; seeds 0-4.
- Random search at the same budgets.
- Supervised classifier (MLP) trained on enumeration labels. Label count matched to the RL budget: floor(200,000/|C|) = 2,197 labels; sensitivity 20,000. Label cost counted as |C| checker calls each. It tests whether RL is needed at all.

Tuning: 12 configurations per algorithm (DDQN, GFlowNet, GA, DE, classifier), drawn by a fixed seed, selected on V. A configuration change counts only if validation mean gap improves by at least 0.5 percentage points with feasibility not lower.

Repair or post-processing (for example nearest-passing section, top-k with checker) is reported separately from raw policy output. Raw top-1, best-of-k with checker, and enumeration fallback are three distinct metrics; fallback is not RL success.

Diversity: K = 50 samples (or evaluations) per context for GFlowNet, DDQN (softmax of Q, temperature selected on V), GA, DE and random search. Metric: number of distinct feasible sections within 5% of the optimal mass.

## 10. Metrics

Feasibility rate (verified), gap, exact-match rate, utilisations (governing check), checker calls, wall-clock time per design (single CPU thread for search and inference; hardware recorded), diversity count, training cost, total cost for N design tasks = training + N * inference, crossover N*, seed-to-seed spread. Training and inference are always separate; in-distribution (T1, T2) and extrapolation (T3) are separate; single-seed and five-seed results are separate.

## 11. Claims and success criteria

RL is called safe and accurate in range only if, on T1 and T2:
- S1 raw top-1 verified feasibility >= 0.99 in every seed.
- S2 median gap <= 2% (T1) and <= 3% (T2) for the median seed.

Efficiency is claimed only if N* is finite and below N_ref = 10,000 design tasks, with seed spread shown.
Diversity (RQ5): the GFlowNet is called diverse if its median count is at least 3 on contexts where the reference has at least 3 such sections.
Extrapolation (T3) is reported descriptively without a threshold.

"Method A better than B on metric M" requires both: paired exact permutation test over contexts, Holm-adjusted p < 0.05 within the comparison family; and a mean difference of at least 1 percentage point of gap or 20% of time, or 1 section for diversity. Otherwise: no difference claimed. If enumeration, GA, DE or the classifier is better, that is reported as such. If S1 or S2 fail, the paper reports RL as not meeting the criteria.

## 12. Verification and gates

- Gate 0: this specification.
- Gate 1: checker implemented separately from the environment; unit, boundary and regression tests pass.
- Gate 2: independent verification: a separately written Python implementation and hand calculation agree with the checker within 0.5% on each utilisation for the reference case and at least 10 further cases covering each check; the supervisor's section 457x191x74 for the reference case is an external benchmark (expected lightest feasible section; to be reproduced by the verified checker, not assumed).
- Gate 3: enumeration, GA and DE protocols run; every design of every method and seed stored; every output rechecked.
- Gate 4: test files and budgets frozen; no RL training before Gates 1-2 are accepted.
- Gate 5: manuscript numbers come only from `results/` and `paper/tables/`.

Every run has status "complete". Every result file has a `*_meta.json` with commit and the SHA-256 of the environment file. Generated results are not committed.

## 13. Limitations

One representative beam; S355 UB only; fully restrained; UDL only; fixed dead/live share; fixed bearing length. Results do not transfer to other sections, grades, welded sections or unrestrained beams. Enumeration is optimal only within C and the implemented checks. Outputs are recommendations requiring engineering verification. Abaqus verification and a Streamlit application follow the core study and are not part of the claims.

## 14. Time

No external deadline. Self-set target: about 1 month. Run budgets in section 9 (15 RL runs) are sized to fit; extending the target is allowed and needs no change to the claims.

## Amendments

- 2026-10-17, v1.1, before any run: RL formulations, algorithms and reward modes replaced; kNN removed; RQ5 and diversity metric added; repository link added.
