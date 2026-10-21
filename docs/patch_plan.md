# Patch plan

Every step of the project is one patch: one commit, its own tests, its own acceptance criteria. A patch is applied only after the one before it is accepted. No patch changes a pre-registered assumption without a dated amendment in `docs/spec.md`, and every patch updates `docs/verification_record.md` where its evidence belongs. No RL training happens before Gate 3 is accepted. Dependencies are the order of the list.

## Done (in the repository)

| Patch | Content | Evidence |
|---|---|---|
| D1 | Specification, catalogue parser, vectorised Eurocode 3 checker (bending, shear, shear buckling, bending-shear interaction, web bearing, deflection) | 45 tests; reference beam 457x191x74 at 99.8 % bending utilisation |
| D2 | Amendment A1: lateral-torsional buckling (LTB), seven-parameter `Context`, research proposal | LTB tests; second scalar LTB implementation |
| D3 | Review fixes: restraint ratios limited to 0, (0, 0.5] and 1; one not-found convention (-1); sensitivity script | 101 tests |
| D4 | Gate 2 evidence: second implementation of the non-LTB checks, public SCI benchmarks, generated verification cases, Blue Book comparison script and module, corrections found (LTB curve d for h/b > 3.1; shear modulus) | 120 tests, 7 skipped without the licensed Blue Book workbooks; all 107 sections agree with the Blue Book tables within rounding |
| D5 | This plan and the engineering review request (`docs/review_request.md`) | none needed (documents) |

## Planned patches

### Gate 2 close-out

**P5 Gate 2 sign-off.** Record the engineer's check of the 8 required cases in `docs/gate2_cases.md` (G2-01, 02, 06, 07, 08, 09, 10, 11), the answers on each assumption, and the review notes (`docs/gate2_signoff.md`); fix whatever is found, with a dated amendment if an assumption changes. *Accepted when:* every required case is signed, every assumption has an answer, no open difference above rounding. *Needs a person:* the filled form from `docs/review_request.md`; this is the only step in the plan that no program can do.

### Gate 3: Stage 1 preparation

**P6 Context box and splits.** Dated spec amendment A2 fixing the seven-parameter sampling ranges and the splits (the spec defines T1 interpolation, T2 held-out block, T3 extrapolation E1 to E3 for two parameters; A2 extends them to seven parameters, including a held-out restraint value, and adds T4 for unseen combinations); feasibility audit over the context box; generate the training, validation and test sets with their SHA-256; list the abstention contexts (none removed). *Accepted when:* A2, the split files with hashes and the audit tables are committed and the audit is reproducible by one script.

**P7 Stage 1 baselines I.** Exhaustive enumeration, ordered scan, heuristic iteration, random search; checker-call accounting; stored designs for every test context. *Accepted when:* enumeration equals ordered scan on every context; call counts are logged per method.

**P8 Stage 1 baselines II.** Genetic algorithm and differential evolution (several section orderings and a categorical-native GA), and the supervised MLP in its three variants trained on enumeration labels at equal total call budget (kNN was removed in spec v1.1). Equal tuning effort (12 configurations per method), selection on validation only. *Accepted when:* every baseline reports feasibility, gap and calls on T1 to T4.

**P9 Landscape and saturation diagnostics, Gate 3 acceptance.** Landscape diagnostics (distinct optima, governing checks, alternatives, section-order monotonicity); the saturation rule (heuristic iteration or the classifier at exact match >= 0.99 and feasibility 1.0 on the validation set); the Gate 3 record. Freezing is not done here: the spec freezes test files, budgets and the primary family at Gate 4 (P12). *Accepted when:* diagnostics are reproducible by one script and the Gate 3 record states the saturation outcome per context set.

### Gate 4: Stage 1 learning

**P10 Environments and rewards.** Direct choice (F0), refinement (F1) and constructive (F2) environments; reward families R-A to R-D; the assertion that every feasible return exceeds every infeasible return, checked on every validation context. *Accepted when:* the ordering assertion passes for every family and every context.

**P11 Agents and training harness.** DQN, Double DQN, Dueling Double DQN with prioritized replay and n-step returns, discrete PPO, discrete SAC, policy gradient, GFlowNet (diversity); configuration-driven runs, seeds, checker-call counters, checkpoints, logs. *Accepted when:* each agent trains on a toy context set and reproduces its result for the same seed.

**P12 Pilots and pre-registration freeze.** Pilots on validation data only; hyperparameter search protocol (12 configurations per algorithm); budgets; success criteria; freeze and tag. *Accepted when:* the tag exists and the spec amendment records the frozen choices.

**P13 Stage 1 runs and analysis.** Ten seeds per configuration; exact tests with Holm correction, context-level bootstrap intervals, practical margins; the pre-registered comparisons (including RL against the supervised classifier at matched checker calls); safety, generalisation (T1 to T3, by restraint value), quality, cost and diversity (RQ5, GFlowNet); figures and tables generated from saved results only. *Accepted when:* every claim in the results maps to a pre-registered comparison, and a claim is made only if its criteria are met.

### Stage 2: custom welded sections

**P14 Stage 2 amendment, welded-section model and checker.** Dated spec amendment A3 for Stage 2 (plate ranges, fabrication increments, context ranges, splits, success criteria) before any Stage 2 result. Section properties from plate geometry; classification; bending; shear; shear buckling; web bearing; deflection; LTB for welded sections (UK NA NA.2.17 as reproduced in software documentation, not yet read from the NA text: lambda_LT,0 = 0.2 and beta = 1.0; curve c for h/b <= 2 and curve d for 2 < h/b <= 3.1; not specified above 3.1, so the general case 6.3.2.2 or an h/b limit, to be decided and recorded); fabrication increments and bounds. *Accepted when:* unit tests pass and the model reproduces rolled-UB resistances to a stated tolerance when given UB plate dimensions.

**P15 Stage 2 verification.** Second implementation, generated cases with hand-check sheets, an independent calculation by an engineer, and an entry in the verification record. *Accepted when:* signed as in P5.

**P16 Stage 2 baselines and audit.** SLSQP, differential evolution, genetic algorithm, CMA-ES, supervised policy trained on optimizer labels; saturation diagnostics; frozen test sets and budgets. *Accepted when:* as P9.

**P17 Stage 2 environments, agents and freeze.** Sequential design environment; SAC, TD3, DDPG, PPO, branching dueling Q-network, and RL-then-optimizer hybrids; pilots on validation data; freeze and tag. *Accepted when:* as P12.

**P18 Stage 2 runs and analysis.** Ten seeds; non-inferiority tests on mass (margin 2 percentage points), cost comparison, hybrid warm-start comparison. *Accepted when:* as P13.

### Delivery

**P19 Efficiency and break-even analysis.** Cost per design and break-even number of designs in calls and wall-clock, for cheap checks and for checks of 1 ms and 1 s; sensitivity of the efficiency conclusions to N_ref (the pre-registered threshold N_ref = 10,000 is not changed). *Accepted when:* every efficiency claim has its break-even and its assumption stated.

**P20 Abaqus verification.** Input generation and result comparison for about 10 final designs (linear buckling for Mcr, static deflection). *Accepted when:* differences from the checker are tabulated and explained. *Needs:* Abaqus access; if it is not available the step is recorded as not done and the paper states that finite-element confirmation was not performed.

**P21 Application.** Web application: inputs, several distinct verified designs, utilisation table, governing check, report; every shown design is re-verified when it is displayed. *Accepted when:* the application's output equals the checker's for the reference cases.

**P22 Manuscript (Gate 5).** The journal paper written from `results/` and `paper/tables/` only; every number traceable to a saved result; claims limited to the pre-registered criteria that were met. *Accepted when:* a script lists every number in the text with its source file and none is missing.

**P23 Artefacts and release.** Final figures and tables from saved results, locked environment, README with exact commands, data and code release (the Blue Book workbooks stay out of the release; instructions to obtain them), final verification record. *Accepted when:* a clean clone reproduces every number in the paper.
