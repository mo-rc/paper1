# Specification (pre-registration)

Version 1.2 with Amendments A1 and A2 (end of file). Repository: https://github.com/mo-rc/paper1. Frozen before any run. Changes are dated amendments at the end of this file, made before the affected run.

## 1. Scope

One simply supported steel I-beam of a three-storey building. Standard UK Universal Beams (UB) only, S355 only, no welded or built-up sections. Beam is fully restrained laterally. Primary output: a catalogue section that passes every check, verified by an independent checker.

Research questions:
- RQ1 Safety: does the policy output sections that pass every check?
- RQ2 Generalisation: does it hold on unseen span/load without retraining?
- RQ3 Automation efficiency: per-design and total cost versus enumeration, ordered scan, heuristic iteration, GA and DE, with training, tuning and label cost included.
- RQ4 Quality: gap to the lightest feasible catalogue section.
- RQ5 Diversity: does a generative policy return several distinct feasible near-optimal sections?

No method is assumed to win. The question is whether a learned policy is a useful, reliable and computationally competitive mapping from context to feasible near-optimal sections across many tasks, not whether RL beats enumeration. Enumeration is exact within C and the implemented checks, so no claim of better solution quality than enumeration is made. If conventional heuristics already saturate solution quality (section 12), the paper is a benchmark of when learned design is and is not needed, and a negative result for RL on quality is an accepted outcome. Claims follow section 11.

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
- Raw file is not committed (licence terms not checked); its checksum is.

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

Deflection limits (span/360 brittle finishes, span/200 other beams, on variable load) follow UK practice and the UK NA suggested values as given in public sources. Bearing length ss is a stated assumption.

Checker rules (clarifications, no change of assumptions):
- Bending resistance by class: class 1-2 use Wpl; class 3 uses Wel; class 4 is infeasible (conservative; effective-section design is out of scope; an unverified preliminary check finds no class 3 or 4 section in C, so this choice matters only if the verified checker finds any). Class limits use epsilon from the same fy as the resistance.
- fy uses the maximum element thickness (convention of the SCI Blue Book resistance tables; verified from the SCI explanatory notes, which state the UK NA specifies the product-standard values).
- Bending-shear interaction (6.2.8) is evaluated at stations along the span (101 stations), not by pairing maximum moment with maximum shear.
- Shear area Av per 6.2.6(3) with eta from the UK NA to EN 1993-1-5 (value to be confirmed in the verification record).
- Gate 2 benchmarks include the public SCI Blue Book bending, web bearing and buckling resistance tables for the same sections.
- Not modelled: construction-stage stability, torsional restraint at supports (fork supports assumed), connection details. If the feasible set is empty for any context, the range is revised before experiments through a documented feasibility audit.

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

Catalogue order: sections are indexed in mass-ascending order (ties: smaller h, then catalogue order). Series = nominal serial size (for example 457x191), ordered by depth.

RL formulations (state includes normalised context):
- F0 Direct choice (contextual bandit): the policy outputs a categorical distribution over C; one sampled section is checked per context (bandit feedback, one checker call per sample) and scored with R1 as an accepted section (no step cost). Greedy output = arg max probability.
- F1 Refinement MDP: start from the trial section (first section in mass order with Wpl >= M_Ed/fy, using w and fy = 355). Observation: context, current section geometry and mass, utilisation of every check. Actions: one mass step up or down, move to the lightest section of the next deeper or shallower series, accept. A move past either end of the catalogue is a no-op that still costs a step. Horizon 12 steps; at step 12 the current section is accepted automatically. Gate 3 verifies on every split that the optimum lies within 12 steps of the trial section; otherwise the horizon is amended before training.
- F2 Constructive MDP (GFlowNet): two choices, series then variant within the series. The choice graph is a tree, so F2 is equivalent to matching a hierarchical categorical distribution to R, and the paper says so. Greedy output = the section with the largest joint probability P(series)P(variant | series), computed exactly over C. One checker call per sampled section.

Algorithms (PPO, SAC, TD3 and DDPG are not used):
- F0: softmax policy gradient (REINFORCE) with a learned baseline.
- F1: Dueling Double DQN with prioritised replay.
- F2: conditional GFlowNet, trajectory balance, with a learned log Z(context).

Rewards use log-mass so a difference equals a relative mass gap. m_trial is the mass of the F1 trial section for the context; m_max is the heaviest section of C.
- R1 Terminal-sparse: accepting a feasible section gives -ln(m/m_trial); accepting an infeasible section gives -ln(m_max/m_trial) - 1, strictly below every feasible value for that context; step cost 0.001. With at most 12 steps the total step cost is at most 0.012, below the margin of 1, so the ordering also holds for episode returns.
- R2 Potential-based shaping on R1: F = Phi(s') - Phi(s), Phi = -ln(m/m_trial) - 2*max(0, max utilisation - 1), Phi(terminal) = 0, discount 1.
- R3 Reward-proportional (F2): log R(x) = -beta*ln(m/m_trial) if feasible; log R(x) = -beta*ln(m_max/m_trial) - 10 if infeasible. Every feasible section has a strictly higher log-reward than every infeasible one by construction (feasible: at least -beta*ln(m_max/m_trial); infeasible: that minus 10). The total sampling weight of infeasible sections is at most |C|*e^-10 (about 0.4%) of the optimum's weight; verification handles the remainder. All reward arithmetic is in float64 log-space. beta in {25, 50, 100}, selected on V.
- A check asserts the strict feasible > infeasible ordering for every context in V and every candidate.

Configurations: F0-R1, F1-R1, F1-R2, F2-R3; seeds 0-9; 40 runs. Training budget: 200,000 checker calls per run; sample-efficiency curves at 10,000, 50,000 and 200,000 calls. Greedy output (arg max) is the policy output for S1 and S2; sampled output is reported separately. Pilot runs (3 seeds, 10,000 calls, validation set only) precede full runs.

Baselines:
- Enumeration (exact reference; also timed).
- Ordered scan: evaluate in mass order, stop at the first feasible section (exact).
- Heuristic iteration (conventional manual design): trial section from the required modulus, move up until feasible, then down while feasible. Checker calls counted.
- GA and DE over C at evaluation budgets 10, 20, 50, |C|; seeds 0-9. Section order sensitivity: mass order and three random permutations; plus a categorical-native variant (uniform crossover, random-section mutation).
- Random search at the same budgets.
- Supervised MLP, three variants: (i) enumeration labels at matched calls, floor(200,000/|C|) = 2,197 labels; (ii) heuristic-iteration labels at matched calls (label cost = calls used; optimality not certified, audited against enumeration on V); (iii) 20,000 enumeration labels, unmatched, as a favourable reference. Exact labels are costed two ways: |C| calls (full enumeration) and rank of the optimum (ordered scan with certificate). It tests whether RL is needed.

Tuning: 12 configurations per algorithm (F0, F1, F2, GA, DE, classifier), drawn by a fixed seed, selected on V. A configuration change counts only if validation mean gap improves by at least 0.5 percentage points with feasibility not lower. Tuning checker calls are added to the training cost.

Sensitivity rules (C107, span/200, total load with span/250) are evaluated with enumeration, ordered scan, heuristic iteration and the classifier; RL is not retrained for them unless the primary rule changes by amendment.

End-to-end procedure for every method: output a section, verify it (1 call), if infeasible step up in mass order until feasible (calls counted), abstain at the end of C. Final gap and calls per verified design are reported alike for all methods.

Output status: a returned design is always checker-verified. If no feasible section is found within the method's budget, the method abstains. Unverified raw output exists only for metrics. Raw top-1, best-of-k with checker, and fallback to enumeration are three distinct metrics; fallback is not RL success.

Diversity: K = 50 samples (or evaluations) per context for F2, F1 (softmax of Q, temperature selected on V), GA, DE and random search. Metric: number of distinct feasible sections within 5% of the optimal mass, and the number differing in depth by at least 50 mm. Reported only on contexts where the reference has at least that many.

## 10. Metrics and cost accounting

Feasibility rate (verified), gap, exact-match rate, utilisations (governing check), abstention precision and recall, diversity counts, wall-clock time per design (single CPU thread for search and inference; hardware recorded), seed-to-seed spread.

Cost unit: checker calls. Per-task cost c = calls for one verified design (learned methods: 1 verification call for F0 and F2, the step count for F1, plus repair calls). One-off cost T = training + tuning + pilot + label calls. Break-even against a conventional method: N* = T / (c_conv - c_learned), defined only if c_conv > c_learned, otherwise "no break-even". Computed against enumeration, ordered scan and heuristic iteration separately, and in wall-clock separately (network compute included). Break-even in calls does not depend on the cost per call; absolute savings do, so costs are also stated for 1 microsecond (measured), 1 ms and 1 s per call (finite-element verification). Training and inference are always separate; T1 and T2 (in range) and T3 (extrapolation) are separate; single-seed and ten-seed results are separate.

## 11. Claims and success criteria

RL is called safe and accurate in range only if, on T1 and T2:
- S1 raw top-1 verified feasibility >= 0.99 in every seed.
- S2 median gap <= 2% (T1) and <= 3% (T2) for the median seed.

Efficiency is claimed only if N* against heuristic iteration (the cheapest conventional method) is finite and below N_ref = 10,000 design tasks, at equal feasibility and gap, with seed spread shown. N_ref was fixed in v1.0.
Diversity (RQ5): F2 is called diverse if its median count is at least 3 on contexts where the reference has at least 3 such sections.
Extrapolation (T3) is reported descriptively without a threshold.

"Method A better than B on metric M" is a confirmatory claim only within the primary family, fixed before runs (at most four comparisons):
- P1 best RL configuration vs heuristic iteration, end-to-end checker calls per verified design.
- P2 best RL configuration vs supervised MLP variant (i) at matched checker calls, gap on T1.
- P3 best RL configuration vs DE at budget 20, gap on T1.
- P4 F2 vs F1 sampled output, diversity count.
"Best RL configuration" is fixed on V before testing: highest verified feasibility, then lowest gap, then fewest calls.
Inference: (a) context level: paired bootstrap (10,000 resamples) of the mean per-context difference, averaged over seeds, 95% interval; (b) seed level: against a deterministic comparator (heuristic iteration, ordered scan, enumeration), exact two-sided sign-flip test of the 10 seed-level differences to the comparator's value (smallest p = 0.002); against a stochastic comparator (DE, GA, random search, the classifier trained with seeds 0-9, F1 vs F2), exact two-sided permutation test on the seed-level means (184,756 arrangements). With 5 seeds the smallest attainable p is 0.0625, so 10 seeds are used. Holm correction over the four comparisons. A claim needs all three: Holm-adjusted seed-level p < 0.05; a context-level 95% interval excluding zero; and a mean difference of at least 1 percentage point of gap, 20% of checker calls, or 1 section for diversity. Effect sizes with intervals are always reported. All other comparisons are exploratory and labelled so. Otherwise: no difference claimed. If enumeration, ordered scan, heuristic iteration, GA, DE or the classifier is better, that is reported as such. If S1 or S2 fail, the paper reports RL as not meeting the criteria.

## 12. Verification and gates

- Gate 0: this specification.
- Gate 1: checker implemented separately from the environment; unit, boundary and regression tests pass.
- Gate 2: independent verification: a separately written Python implementation and hand calculation agree with the checker within 0.5% on each utilisation for the reference case and at least 10 further cases covering each check; the supervisor's section 457x191x74 for the reference case is an external benchmark (expected lightest feasible section; to be reproduced by the verified checker, not assumed).
- Gate 3: feasibility audit and diagnostics. Enumeration run on all splits; infeasible contexts recorded and kept as abstention cases (none removed after seeing model performance); landscape diagnostics (distinct optima, governing checks, alternatives, section-order monotonicity); baseline saturation (heuristic iteration, ordered scan, classifier); reward asserts and float64 log-space checks. Then baselines run; every design of every method and seed stored; every output rechecked.
- Gate 4: test files, budgets and the primary family frozen (SHA-256 of test files recorded after the feasibility audit); pilots on V only; no RL training before Gates 1-3 are accepted.
- Saturation rule: if heuristic iteration or the classifier reaches exact match >= 0.99 and feasibility 1.0 on V, the study reports that the learned policy has no quality headroom on that context set. RL still runs for sample efficiency, diversity and cost; no quality-superiority claim is possible there.
- Gate 5: manuscript numbers come only from `results/` and `paper/tables/`.

Every run has status "complete". Every result file has a `*_meta.json` with commit and the SHA-256 of the environment file. Generated results are not committed.

## 13. Limitations

One representative beam; S355 UB only; fully restrained; UDL only; fixed dead/live share; fixed bearing length. Results do not transfer to other sections, grades, welded sections or unrestrained beams. Enumeration is optimal only within C and the implemented checks. Outputs are recommendations requiring engineering verification. Abaqus verification and a Streamlit application follow the core study and are not part of the claims.

## 14. Time

No external deadline. Self-set target: about 1 month. Run budgets in section 9 (40 RL runs) are sized to fit; extending the target is allowed and needs no change to the claims.

## 15. Decisions awaiting supervisor confirmation

Defaults below are working assumptions, not approvals. Each item that changes the feasible set or the optimum is a decision; results are conditional on them until answered.

| Item | Working default | Effect if changed |
|---|---|---|
| Load combination | Exp. 6.10, 1.35 dead and 1.5 live (UK NA also allows 6.10a/6.10b) | Changes demand and the optimum |
| Deflection load and limit | Variable load, span/360 | Changes governing check; span/250 on total load changes the optimum in every context (unverified preliminary) |
| Support and bearing | Fork supports, ss = 100 mm, c = 0, unstiffened web | Changes web bearing feasibility |
| Variable-load share | Fixed at the reference value across contexts | Changes the context definition |
| Catalogue "+" rows | Excluded from the primary set C (91); C+ (107) as sensitivity | Changes the reference section set; availability of "+" rows unconfirmed |
| Class 4 treatment | Infeasible; none found in C in an unverified preliminary check | Matters only if the verified checker finds any |
| Self-weight | Added by the checker (the source paper omits it; delegated by the supervisor) | Reference case bending utilisation 0.998 with it (unverified preliminary) |
| Shear buckling eta | From the UK NA to EN 1993-1-5, to be read from the text | Decides whether any section needs the shear buckling check |
| Extra context parameters (for example depth cap h <= h_max) | Not in the frozen study | Needs a design requirement and an amendment |
| Construction-stage stability | Not checked | Out of scope, stated as a limitation |

## Amendments

- 2026-10-17, v1.1, before any run: RL formulations, algorithms and reward modes replaced; kNN removed; RQ5 and diversity metric added; repository link added.
- 2026-10-17, v1.2, before any run: reward definitions corrected (v1.1 R3 gave every feasible section a reward below the infeasible reward of 1e-6 for beta 20 and 40, since m/m_trial >= 1 gives exp(-beta) < 1e-6; for beta 10 any feasible section heavier than 1.38 m_trial); F0 direct-choice formulation, ordered-scan and heuristic baselines added; seeds raised to 10 and statistics redefined (exact tests over contexts removed; 5 seeds give p >= 0.0625); feasibility audit, abstention, saturation rule and cost accounting added; checker rules clarified; assumptions listed as decisions awaiting confirmation.

### Amendment A1 (2026-10-19, before any run): scope, LTB, contexts, one-paper design

Governing narrative: `docs/proposal.md` (one journal paper). Status: **proposed, awaiting supervisor acceptance**. Nothing in this repository has been run for the study; no RL training occurs before Gates 1 to 3 are accepted. Where this amendment and an earlier section disagree, the amendment governs for the stage named in the table below; the earlier text is kept unchanged as the record.

**Superseded statements**

| Earlier statement (spec line) | Status after A1 |
|---|---|
| UB only, S355 only, no welded sections; fully restrained (section 1) | Stage 1 keeps UB only and S355. Restraint is a context parameter; restraint_ratio = 0 is the full-restraint case of v1.2. Stage 2 adds welded symmetric I-sections (S355) |
| Design variable is categorical over C; continuous dimensions out of scope (section 9) | Holds for Stage 1. Stage 2 uses continuous or increment-based dimensions |
| "PPO, SAC, TD3 and DDPG are not used" (section 9) | Replaced: Stage 1 runs a tournament (DQN, Double DQN, Dueling Double DQN, discrete PPO, discrete SAC, policy gradient, GFlowNet for diversity); Stage 2 uses SAC, TD3, DDPG, PPO, branching dueling Q-networks and hybrids |
| Scope: fully restrained, UDL only, fixed dead/live share, fixed bearing length (section 13) | Fully restrained and fixed dead/live share no longer hold (contexts below). UDL only and fixed bearing length (100 mm) still hold |
| Context = (span, factored UDL), dead/live share fixed (sections 3 and 8) | Context = seven parameters, `ub_rl.context.Context`: span, tributary width, dead load, live load, restraint ratio, deflection rule, depth cap. Ranges and splits fixed at Gate 3 after the feasibility audit; the v1.2 box remains the full-restraint sub-study |
| LTB: continuous restraint, chi_LT = 1 (section 6) | LTB is checked per context through the restraint ratio (change 1); ratio 0 reproduces this row |
| Configurations F0-R1, F1-R1, F1-R2, F2-R3; algorithms REINFORCE, Dueling Double DQN, GFlowNet; 40 runs (section 9) | Replaced by the tournament matrix of change 4. These four configurations remain the first entries of that matrix |
| Sensitivity rules span/200 and total load span/250 evaluated without retraining RL (section 9) | The deflection rule is a context parameter, so RL is trained across `var360`, `var200` and `tot250` (change 3). The sensitivity paragraph still applies to C+ (107 rows) |
| Extra context parameters such as a depth cap are not in the frozen study (section 15) | The depth cap is a context parameter (floor-depth limit; values none, 500, 600, 700 mm, to be confirmed at Gate 3) |
| Self-set target of about one month (section 14) | About 28 weeks |

**Changes**

1. **LTB check** (`restraint_ratio` = Lcr / L in `CheckerConfig`). 0 means continuous restraint and reproduces v1.2 exactly. EN 1993-1-1 6.3.2.3, rolled I sections; Mcr per NCCI SN003; load at the shear centre by default, top-flange loading (zg = +h/2) as a sensitivity; curve b for h/b <= 2, curve c for 2 < h/b <= 3.1, curve d above 3.1 (alpha 0.34, 0.49, 0.76; UK NA, confirmed by the Blue Book comparison); lambda_LT,0 = 0.4, beta = 0.75; shear modulus G = E / (2 (1 + 0.3)) = 80,769 N/mm2 (matches the Blue Book Mb,Rd table). **Moment factors:** C1 = 1.127, C2 = 0.454, kc = 0.94 (UDL) only when restraints are at the supports (ratio 1). For 0 < ratio < 1 the conservative uniform-moment values C1 = 1, kc = 1 are used at the maximum design moment (C2 kept for top-flange loading); per-segment moment diagrams are a Gate 2 sensitivity, not part of the primary study. Loads on the top flange are not validated and are not used in any frozen result.
2. **Seven-parameter contexts** implemented as `Context` with `Checker.evaluate_context` and `lightest_feasible_context`. The depth cap is a design requirement, not a code check: contexts with no feasible section are abstention cases and are not removed (`lightest_feasible` and `lightest_feasible_context` both return -1). **Restraint ratios in contexts are limited to 0, values in (0, 0.5], and 1**; the LTB model is not monotone in (0.5, 1) (see verification record), so those values are rejected.
3. **Deflection rules** per context: `var360` (variable load, L/360, primary), `var200` (variable, L/200), `tot250` (total characteristic, L/250).
4. **Algorithms (Stage 1 tournament matrix):** each algorithm is run on the formulations it supports, under equal tuning effort (12 configurations each, selection on V only), seeds 0 to 9, 200,000 checker calls per run, as in section 9.
   - F0 (direct choice, R1): REINFORCE with a learned baseline; discrete PPO.
   - F1 (refinement, R1): DQN; Double DQN; Dueling Double DQN with prioritised replay and n-step returns; discrete PPO; discrete SAC.
   - F2 (constructive, R3): conditional GFlowNet (diversity).
   - Reward variants R2, R-C and R-D are run for the best F1 algorithm selected on V.
   - About 110 runs in total (8 algorithm-formulation entries and 3 reward variants, 10 seeds each). The primary comparisons P1 to P4 of section 11 use the best configuration selected on V.
5. **Reward families** (R1 to R3 as in section 9; R3 is for F2 only):
   - **R-A = R1**, reference-relative terminal reward. **R-B = R2**, potential-based shaping.
   - **R-C Lagrangian (new):** the environment reward is R1, unchanged. The training loss adds lambda * c with cost c = max(0, max utilisation - 1) of the accepted design and a multiplier updated by dual ascent (lambda <- max(0, lambda + eta * (mean c - 0))). The ordering rule holds for the environment reward; feasibility is judged on verified output, never on the penalised objective.
   - **R-D call-penalized (new):** R1 with step cost kappa per checker call, with kappa * N_max <= 0.5 (N_max = maximum calls per episode), so the margin of 1 between feasible and infeasible returns is preserved, as for the 0.001 step cost of R1. For the expensive-check regime the cost is reported in calls and in assumed seconds per call, not folded into reward values.
   - The ordering "every feasible return exceeds every infeasible return" is asserted per validation context for every family; constants are frozen at Gate 4.
6. **Stage 2** (welded symmetric I-sections) carries the main result; Stage 1 is the controlled testbed; both are reported in one paper. Success criteria for custom sections (proposal section 7), fixed here before any Stage 2 run:
   - S3 safety: raw top-1 verified feasibility >= 0.99 in every seed.
   - S4 quality (non-inferiority): the one-sided upper 95 % bound of the median mass gap to the best per-problem optimizer is at most 2 percentage points.
   - S5 cost: at least 10 times fewer checker calls per verified design than the best per-problem optimizer, training and tuning counted through N* as in section 10.
   - S6 hybrid: warm-starting an optimizer from the policy reaches the same final mass with at least 30 % fewer optimizer evaluations than a cold start.
   - Stage 2 confirmatory family (at most four, Holm correction within Stage 2): P5 best RL vs best optimizer, mass gap (non-inferiority); P6 best RL vs best optimizer, calls per verified design; P7 best RL vs supervised policy trained on optimizer labels at matched calls, mass gap; P8 hybrid vs cold-start optimizer, evaluations.
   - Proposal section 7 maps to the specification as follows: "learning from feedback" is P2 (Stage 1); "expensive verification" is P1 with N* reported at 1 ms and 1 s per call (section 10); "custom sections" is S3 to S5 and P5 to P7; "hybrid" is S6 and P8.
   - **Amendment A3 (patch P14) is required before any Stage 2 run** and must fix: the design variables and bounds, class and h/b limits, fabrication increments, the welded LTB parameters (UK NA: lambda_LT,0 = 0.2, beta = 1.0, curve c for h/b <= 2 and curve d for 2 < h/b <= 3.1, and how h/b > 3.1 is handled), the Stage 2 splits and baselines, and the budgets. A3 may add detail but may not weaken S3 to S6 or P5 to P8. Amendment A2 (patch P6) fixes the Stage 1 seven-parameter ranges and splits.

7. **Web bearing, two valid solutions:** `CheckerConfig.bearing_rule` = `higher` (default; SCI AD 378 and the Blue Book tables) or `sequential` (EN text order, lower resistance for 6 sections). The default is unchanged. `sequential` is a pre-registered sensitivity.
8. **Gate 2 artefacts added:** a second implementation of the non-LTB checks, public SCI benchmarks, generated verification cases, and a Blue Book comparison script (see the verification record). They do not change any assumption.

Unchanged: catalogue and parser, material rules, self-weight in the checker, call-count cost accounting, ten-seed exact tests with Holm correction, saturation rule, gates.

### Amendment A2 (2026-10-23, before any run): Stage 1 seven-parameter ranges and splits (patch P6)

Status: recorded before any RL run; Gate 3 acceptance covers it. Generator: `src/ub_rl/splits.py`; audit and files: `python scripts/context_audit.py` (`--check` regenerates and compares); results: `docs/context_audit.md` and `paper/tables/audit_*.csv`. No assumption of Gate 2 is changed. No physics, checker or objective is changed.

**Disclosure.** The ranges were chosen after a checker-only look at feasibility (no model of any kind had been run). The same comparison is committed (`paper/tables/audit_cap_alternatives.csv`, every 4th training-pool row): the proposal's depth caps of 500 and 600 mm leave 71 to 100 % of the contexts without any feasible section (restraint 0: 95.0 % and 70.7 % abstention with cap 500 and 600 mm; restraint 1: 100 %). The cap values are therefore changed (superseded table). The audit rules R1 and R2 below are sanity gates fixed after that look; they are not claims.

**Superseded statements**

| Earlier statement | Status after A2 |
|---|---|
| Depth cap values none, 500, 600, 700 mm "to be confirmed at Gate 3" (A1, proposal section 5) | Confirmed as none, 700, 800, 900 mm. Caps 650 and 750 give the same abstention rates (UB depths cluster); 500 and 600 are near-empty (`audit_cap_alternatives.csv`) |
| Contexts (L, w) with hole H, V = 500 (section 8) | Seven-parameter contexts, tables below. The hole is a block in (span, factored UDL w) with the other five parameters free. V = 1,000 (40 trained cells need more than 500) |
| Training "sampled uniformly" (section 8) | Fixed training pool of 20,000 contexts (covers the 20,000 labels of supervised variant (iii)); learners draw from the pool. Online sampling is not used in frozen runs |
| v1.2 box as the full-restraint sub-study (A1) | Kept as written in section 8: `v12_substudy.csv` holds V (500, seed 101), T1 (2,000, seed 202), T2 (500, seed 303) and E1 to E3 (500 each, seed 404) as contexts with width 6 m, dead and live scaled from the reference (variable share fixed), restraint 0, `var360`, no cap. Its training contexts are drawn online from the same box by the same generator. The seven-parameter files also carry the flag `slice_full_restraint` |

**Table 1: sampling ranges** (uniform, rounded to span and width 0.01 m, dead and live 0.001 kN/m2; factored UDL w = (1.35 dead + 1.5 live) x width, rounded to 4 decimals; all tests use rounded values)

| Parameter | Training box |
|---|---|
| span L | [9, 15] m |
| tributary width | [4, 8] m |
| dead load | [2.5, 5.0] kN/m2 |
| live load | [2.0, 5.0] kN/m2 |
| factored UDL w (rejection) | [56, 100] kN/m (the v1.2 range) |
| restraint ratio | 0, 0.25, 0.5, 1 (equal probability) |
| deflection rule | `var360`, `var200`, `tot250` (equal probability) |
| depth cap | none, 700, 800, 900 mm (equal probability) |
| hole H | L in [11.5, 12.5] m and w in [75, 85] kN/m (closed), excluded from training, V, T1, E-sets, T4 |

The reference case (9 m, 6 m, 3.675, 3.0, restraint 0, `var360`, no cap; w = 56.7675 kN/m) is inside the box. `reference.csv` holds it at each of the four trained restraint ratios.

**Table 2: splits.** Each test set differs from the training distribution in one stated way (E3 in two). Contexts are unique across all files. Within a file the sets share one random stream (`random.Random(seed)`, one `random()` per value, fixed order).

| File, set | n | Seed | Definition |
|---|---|---|---|
| `train.csv` | 20,000 | 100 | box minus H, trained cells |
| `val.csv` V | 1,000 | 101 | as training; checkpoint and hyperparameter selection only |
| `test_t1.csv` T1 interpolation | 2,000 | 202 | as training |
| `test_t2.csv` T2 held-out block | 500 | 303 | inside H, other five parameters as training |
| `test_t3.csv` E1 | 500 | 404 | L in (15, 18] m, rest as training |
| E2 | 500 | 404 | w in (100, 130] kN/m, drawn from the extended load box width [4, 10] m, dead [2.5, 6.5], live [2.0, 6.5] kN/m2; rest as training |
| E3 | 500 | 404 | E1 and E2 together |
| E4 | 500 | 404 | restraint ratio 1/3 (never trained; inside the allowed (0, 0.5]); span, load as training; rule and cap uniform over all 12 combinations |
| `test_t4.csv` T4 unseen combinations | 1,000 | 505 | training box, but (restraint, rule, cap) in one of 8 held-out cells; every single value and every pair of values is seen in training |
| `test_t5.csv` T5 lattice | 3,520 | none | every point of the lattice span {9, 10, ..., 15} m, width {4, 6, 8} m, dead {2.5, 3.75, 5.0}, live {2.0, 3.5, 5.0} kN/m2 with w in [56, 100] outside H, in each of the 40 trained cells. Ends and middle of each range (the supervisor's "lower, real, upper" idea as a deterministic test); no sampling |
| `v12_substudy.csv` | 4,500 | 101, 202, 303, 404 | the v1.2 two-parameter sets, see the superseded table |
| `reference.csv` | 4 | none | reference case, four restraint ratios |

Test sets T1, T2, T3, T4 and T5 are reported separately and never pooled.

Held-out cells (`data/splits/heldout_cells.csv`): 8 of the 48 cells, drawn with seed 506 (first draw accepted; conditions: the cell (0, `var360`, none) stays in training; every pair of values stays covered). They are listed in `docs/context_audit.md`.

**Supervisor's suggestion of lower, real and upper values (decision).** Replacing the continuous ranges by a small grid (for example span 8, 9, 10) was considered and not adopted for training: a grid makes interpolation tests trivial and the held-out block, restraint value and combinations could not be defined as cleanly. Its purpose is kept as test T5, an exhaustive lattice that includes the range ends and middles; the lattice is a test only, so the training distribution stays continuous. The reference case lies between lattice points (dead load 3.675, not 3.75) and is reported separately.

**Sensitivity catalogue.** The audit also enumerates every context on C+ (107 sections, spec section 4) and reports where C+ gives a lighter optimum or a feasible design where C abstains (`paper/tables/audit_cplus.csv`). The primary catalogue stays C (91 sections); the abstention list and the splits do not depend on C+.

**Abstention.** A context with no feasible section (code checks, or all code-feasible sections deeper than the cap) is an abstention context. All are listed in `data/splits/abstention_contexts.csv` with the reason (`abstain_code` or `abstain_depth`); none is removed from any split file, now or later. Extrapolation sets contain many by construction; they are reported, not filtered.

**Audit rules** (all must pass before the files are used; values in `paper/tables/audit_rules.csv`): R1 training-pool abstention share <= 0.25; R2 every one of the 40 trained cells has a feasible share >= 0.25; R3 the reference optima at restraint 0, 0.25, 0.5, 1 equal 457x191x74, 533x210x82, 610x229x101, 686x254x140 (`docs/verification_record.md`); R4 no duplicate context across files; R5 no context of train, V, T1, T2, E1 to E3 lies in a held-out cell. If a rule fails, the box is revised by a further dated amendment before any use.

**File hashes (SHA-256).** Committed and checked by `tests/test_splits.py`. Test files are frozen at Gate 4 (section 12) with these hashes; they are not touched during tuning.

| File | SHA-256 |
|---|---|
| `data/splits/train.csv` | `1c67b52a487912b17634d8ca0a4d1dffba9a453a05290c9e22ec56fb3e13db7d` |
| `data/splits/val.csv` | `164c2ffcbf3647b1a86874c0ec26f3d528eb869a0407f76500c0bd43f73ce4e5` |
| `data/splits/test_t1.csv` | `ad9e0bcd1064c914053239d22b373cbb95361c969b3791df84d78eabf84c2955` |
| `data/splits/test_t2.csv` | `e5b31436673e5a36cb5ba2ccfba5c41fffbec07801076c6ae9b7ab1943341767` |
| `data/splits/test_t3.csv` | `c718ee9517eca0901febaf8e1789bbd376b6f1ffd67c0cf1ed03235591319638` |
| `data/splits/test_t4.csv` | `d7a8fd7c3a558b5ef2043ed0d85d111f77a133500afa7c26d07c330f1a33f199` |
| `data/splits/test_t5.csv` | `7369f283a709e9681e95ed843aced01c9c91801dde4a51a2fea4181b018cef3c` |
| `data/splits/v12_substudy.csv` | `8ffda9a0de01c8a58634b9bee0057d7bddf080c264662e28fa6207f77a97bf01` |
| `data/splits/reference.csv` | `633e2f16202fd2b2b9aa0e2207e54cdbf5d1fe5033154237216494bc2ec4510c` |
| `data/splits/heldout_cells.csv` | `693ff64c65a4a8e043a46fef3e07650edc2dff21d5f17a4c06b639a39629c72e` |
| `data/splits/abstention_contexts.csv` | `3aae9b828dd6e98b47b583d7009d7322f01ff4c44a38032d1353beb12759df54` |

**Result files.** `results/audit/labels_<file>.csv` (not committed) hold the enumeration optimum per context; each has `labels_<file>_meta.json` with the commit, the SHA-256 of the environment file (`src/ub_rl/checker.py`; also context, config, splits and script), the catalogue SHA-256 and the split SHA-256. Until environments exist (P10) the checker is the environment file.

**Not done here** (later patches): the F1 horizon check (optimum within 12 steps of the trial section), landscape diagnostics and saturation (P9), baselines (P7, P8).
