# Scope trim (draft of Amendment A5): what Stage 1 keeps and what it cuts

Status: draft, 2026-11-14, branch `review`. No code, no spec edits. This draft supersedes the earlier revisions of this file (2026-11-12) and the unapplied second-revision patch.

**What this document is.** The research proposal is `docs/proposal.md` (unchanged — it says what the paper is about). The frozen pre-registration is `docs/spec.md`. The work plan is `docs/patch_plan.md`. This document is none of those: it is the trim plan — what we propose to cut from the pre-registered Stage 1 plan, why, what it costs, and the order of the remaining work. It becomes Amendment A5 to `docs/spec.md` only after it is applied. It does not change the checker, the physics, the objective, the splits or the success criteria.

## 1. Why trim

1. **Saturation.** The conventional method (heuristic iteration — the way an engineer sizes a beam by hand) already finds the lightest valid section on every validation context: exact match 1.0000, feasibility 1.0 (READ: `docs/gate3_record.md`). A learned policy therefore has no quality headroom on V; RL still earns its place on speed, diversity and cost, and the spec's saturation rule already says exactly this (READ: `docs/spec.md` §12). The tournament was sized to find quality differences that cannot exist.
2. **Focus.** The paper's five questions are safety, generalization, quality, efficiency and diversity (READ: `docs/proposal.md` §4). Three RL entries with three formulations answer all five. The other tournament entries only add breadth, not claims.
3. **Cost.** Pre-registered Stage 1 work: about 181.4 M checker calls. Trimmed: about 20.8 M (section 4). About 9 times less (VERIFIED arithmetic: 181.4 / 20.8 = 8.7).

Material grade: S355 in both stages, as frozen (READ: `docs/spec.md`, Amendment A1). No grade change.

## 2. Stage 1: keep, drop or optional

Registered in (READ: `docs/spec.md` §9 and Amendment A1, changes 4–5). "Optional" means not run unless a further dated amendment brings it back — there is no silent optionality.

| Method (as pre-registered) | Verdict | Why (one line) | Claim it supports |
|---|---|---|---|
| P7 baselines: enumeration, ordered scan, heuristic iteration, random search | keep (done) | Exact reference, plus the conventional and random floors every method is compared against | gap, N*, P1, diversity floor |
| GA, four section orderings, budgets 10/20/50/\|C\| | optional | Order-sensitivity exploration; redundant once one GA is kept | none primary |
| GA, categorical-native variant | keep, trimmed to budgets 20 and \|C\|, mass order, seeds 0-9 | The one GA kept; becomes the P3 comparator after A5 | P3, diversity baseline |
| DE, four orderings, budgets 10/20/50/\|C\| | drop | A second evolutionary search; about 64 M test-set calls for no claim the GA cannot carry | none after trim |
| Supervised MLP variant (i): enumeration labels at matched calls | keep | P2 comparator — RL vs supervised learning on the same budget | P2 |
| MLP variants (ii), (iii) | optional | Cheaper-label and favourable-reference ablations | exploratory |
| F0-R1: REINFORCE with learned baseline | keep | One checker call per design; the direct-choice agent | S1, P1, N* |
| F0-R1: discrete PPO | optional | Second direct-choice learner | none primary |
| F1-R1: DQN, Double DQN, discrete PPO, discrete SAC | optional | Ablations of the one kept F1 agent | exploratory |
| F1-R1: Dueling Double DQN (prioritised replay, n-step) | keep | The one F1 agent: refinement MDP with step cost; sampled output for P4 | S1, S2, P4 |
| F1-R2: potential-based shaping | optional | R1's reward ordering already holds with zero violations (READ: `docs/gate3_record.md`) | robustness |
| F2-R3: conditional GFlowNet | keep | The generative core: diversity (RQ5) and P4; also one call per design | RQ5, P4, P1, N* |
| R-C Lagrangian on the best F1 | contingent | Safety variant; runs only on the trigger written in A5 (section 4) | S1 if the trigger fires |
| R-D call-penalised | drop | Call cost is already reported in calls and in seconds per call; duplicates P1 | none |

The reward-ordering checks for every reward family stay in the P9 tests (they pass; READ: `docs/gate3_record.md`), so making R2 optional and dropping R-D removes no safety guard.

F1 and N*: the spec counts F1's per-task cost as its step count (READ: `docs/spec.md` §10). Whether F1 can carry the N* claim depends on its measured steps, so A5 states the rule (section 4). The N* arithmetic in section 5 covers F0 and F2, whose per-task cost is 1 call.

## 3. The minimal Stage 1 set

- P7 baselines (done, unchanged): enumeration, ordered scan, heuristic iteration, random search.
- One GA: categorical-native, budgets 20 and \|C\| = 91, mass order, seeds 0-9.
- Supervised MLP variant (i) at matched calls (2,197 labels).
- Three RL entries, 10 seeds each (30 runs of 200,000 calls): F0-R1 REINFORCE; F1-R1 Dueling Double DQN; F2-R3 conditional GFlowNet. Sample-efficiency curves at 10,000, 50,000 and 200,000 calls; 12 tuning configurations per entry, selected on V only; pilots (3 seeds, 10,000 calls, V only).
- Unchanged: S1/S2, the primary family P1, P2, P4 (P3 amended below), N_ref = 10,000, the ten-seed exact tests with Holm correction, the diversity metric, budgets, splits, checker, physics, objective.

By research question: RQ1 safety = S1 on the best configuration; RQ2 generalization = T1–T5; RQ3 efficiency = P1 (heuristic), P2 (MLP), P3 (GA) and N*; RQ4 quality = S2 with saturation stated; RQ5 diversity = F2 and P4. Every question keeps its claim.

## 4. Amendment A5 (draft text)

**Amendment A5 (2026-11-12, finalised 2026-11-14, before any run): Stage 1 scope trim.** A4 stays reserved for Stage 2 (patch P14). Original text stays visible; the amendment governs the runs it names. A5 does not change Stage 2.

*Superseded (kept visible)*: A1 change 4, "Algorithms (Stage 1 tournament matrix): … About 110 runs in total (8 algorithm-formulation entries and 3 reward variants, 10 seeds each)."

*Replaced by*: Stage 1 runs three algorithm-formulation entries with 10 seeds each: F0-R1 REINFORCE with a learned baseline; F1-R1 Dueling Double DQN with prioritised replay and n-step returns; F2-R3 conditional GFlowNet. 200,000 checker calls per run; sample-efficiency curves at 10,000, 50,000 and 200,000 calls; 12 configurations per entry selected on V; pilots as registered. The other tournament entries (discrete PPO on F0; DQN, Double DQN, discrete PPO and discrete SAC on F1; R2 and R-D on the best F1) are not run unless reinstated by a further dated amendment.

*N\* rule if the V-selected best configuration is F1 (new, because the spec gives F1 a per-task cost of its step count)*: N* is computed per spec §10 for whichever entry is selected on V. If the selected entry is F1, its per-task cost is its measured mean step count plus repair calls, and section 5's arithmetic does not apply — the efficiency claim then stands or falls on F1's measured calls.

*Safety trigger for R-C (new, fixed before any pilot)*: if, in the pilots on V, no F0, F1 or F2 entry reaches raw top-1 verified feasibility of at least 0.99 in every pilot seed, R-C is run on the best F1 entry; R-C's constants are frozen at Gate 4. If the trigger does not fire, R-C is not run. The trigger is a pilot-based early warning only: if S1 later fails on T1/T2 at P13, the paper reports RL as not meeting the criteria (no rescue run), per §11.

*Tuning budget for the RL entries (new, fixed here because the spec does not fix it)*: 12 configurations per entry, one seed each, **3,000 checker calls per configuration, counting every call it makes, including the verification of the 1,000 V contexts** (so about 2,000 calls of learning). A pilot run counts its 10,000 training calls plus 1,000 V verification calls. The selection rule of §9 (a change counts only if the V mean gap improves by at least 0.5 percentage points with feasibility not lower) is unchanged. Why 3,000: section 5.

*Superseded (kept visible)*: §9 baselines, "GA and DE over C at evaluation budgets 10, 20, 50, |C|; seeds 0-9. Section order sensitivity: mass order and three random permutations; plus a categorical-native variant (uniform crossover, random-section mutation)."

*Replaced by*: one GA, the categorical-native variant, at budgets 20 and \|C\|, mass order only, seeds 0-9. DE and the remaining orderings and budgets are not run unless reinstated by a further dated amendment. **GA tuning (new, fixed here because the spec does not fix it)**: 12 configurations on V, budgets 20 and \|C\|, seeds 0-2; these calls are added to the GA's cost as §9 requires.

*Superseded (kept visible)*: §9, "Supervised MLP, three variants: (i) … (ii) … (iii) 20,000 enumeration labels …" *Replaced by*: variant (i) only (matched calls, 2,197 labels); (ii) and (iii) are not run unless reinstated by a further dated amendment.

*Superseded (kept visible)*: §11 primary family, "P3 best RL configuration vs DE at budget 20, gap on T1." *Replaced by*: P3 best RL configuration vs the categorical-native GA at budget 20, gap on T1. The comparator is still stochastic, so the permutation test stands; Holm correction over the four comparisons is unchanged; P1, P2 and P4 are unchanged.

*Unchanged by A5*: checker, physics, objective, splits and their hashes, the ten-seed statistics, the definition of N* and N_ref = 10,000, S1/S2 (Stage 1), S3–S6 (Stage 2), the gate ordering. `docs/proposal.md` keeps its words; it gets one dated note in §6, in the same pattern as the A2 note in §5, saying Stage 1 runs the three A5 entries.

**Effect on compute** (assumptions as stated; checker calls; VERIFIED arithmetic). Assumptions: GA and DE run on the 9,341 test contexts (VERIFIED count: T1–T5 9,337 plus reference 4); budgets run separately; 10 seeds; GA and DE tuning on the 1,000 validation contexts with 3 seeds and one pass per configuration. RL tuning after the trim: 12 configurations × 3,000 calls per entry; pilots 3 seeds × (10,000 + 1,000) calls per entry. The pre-registered column keeps the reading of 12 × 10,000 tuning calls and 3 × 10,000 pilot calls per entry, because the spec fixed no budget; the reduction shown is therefore an upper figure.

| Item | Pre-registered | After the trim |
|---|---|---|
| RL full runs (200 k calls each) | 110 runs = 22.0 M | 30 runs = 6.0 M |
| RL tuning and pilots | 1.2 M (8 entries) | 0.21 M (3 entries: 0.108 M tuning, 0.099 M pilots) |
| GA and DE on test sets | 143.8 M (5 GA variants and 4 DE orderings; 171 evaluations × 10 seeds × 9,341 contexts per variant) | 10.4 M (one GA; 111 evaluations × 10 seeds × 9,341) |
| GA and DE tuning | 12.3 M (2 algorithms × 12 configurations × 1,000 × 171 × 3 seeds) | 4.0 M (12 × 1,000 × 111 × 3 seeds) |
| MLP labels | 2.05 M (variants (i) 0.20 M, (ii) about 0.03 M, (iii) 1.82 M) | 0.2 M (variant (i)) |
| **Total** | **about 181.4 M** | **about 20.8 M** |

About a 9× reduction (VERIFIED: 181.4 M / 20.8 M = 8.7). The estimate moves with the tuning assumptions.

Wall-clock: multiply the call counts by the per-call rate from `results/baselines1/run_summary.json` — elapsed_seconds divided by n_section_evaluations (READ: both fields are written by the P7 baselines script; the file is git-ignored). That rate is an upper bound on pure checker time because it includes rechecks and file writing.

## 5. Effect on N*

Definitions (READ: `docs/spec.md` §10): one-off cost T = training + tuning + pilot + label calls; N* = T / (c_conv − c_learned), defined only if c_conv > c_learned; efficiency is claimed only if N* against heuristic iteration is finite and below N_ref = 10,000 design tasks, at equal feasibility and gap, with seed spread shown. N* is the registered correction of the common mistake of comparing per-design cost while ignoring training cost.

Inputs: c_conv = 14.193, the heuristic's mean checker calls on V (READ: `docs/gate3_record.md`); c_learned = 1 for F0 and F2 (one verification call per design; F1 uses its step count per the A5 rule above).

**The bar: N* ≤ 10,000 means T ≤ 10,000 × (14.193 − 1) = 131,930 calls** (VERIFIED arithmetic).

Counting assumptions (ASSUMED here, fixed in A5; the spec does not say): (a) T of one deployed policy counts one training run up to the checkpoint, that entry's own 12-configuration tuning and its own pilot (3 seeds), and no label calls (F0 and F2 use none); (b) every checker call counts, including the 1,000 V verification calls used to evaluate a tuning configuration or a pilot run, so a pilot costs 3 × 11,000 = 33,000 calls; (c) checkpoints at 10,000, 50,000 and 200,000 training calls. If instead the training of all ten seeds were counted, the 10,000-call checkpoint alone would give T = 169,000 and N* = 12,810, so no checkpoint could pass (VERIFIED). The spec's wording supports the one-policy reading but does not state it; A5 records the choice.

T and N* (VERIFIED arithmetic; "pass" means N* below 10,000):

| Tuning calls per configuration | Tuning (12 ×) | T and N* at 10 k | T and N* at 50 k | T and N* at 200 k |
|---|---|---|---|---|
| 10,000 (earlier revision) | 120,000 | 163,000 → 12,355 (fail) | 203,000 → 15,387 (fail) | 353,000 → 26,757 (fail) |
| **3,000 (fixed in A5)** | 36,000 | 79,000 → 5,988 (pass) | 119,000 → 9,020 (pass) | 269,000 → 20,390 (fail) |

- The 200,000-call checkpoint fails for every tuning budget: even with no tuning, T = 200,000 + 33,000 = 233,000 and N* = 17,660. The efficiency claim can rest only on the 10,000- and 50,000-call points, which is why A5 keeps those curve points.
- The largest tuning budget that still passes at 50,000 calls is 4,077 calls per configuration ((131,930 − 50,000 − 33,000) / 12); A5 fixes 3,000, leaving 12,930 calls of margin.
- **Repair calls raise c_learned.** A design that fails verification is repaired by moving up in mass order, one call per step, so c_learned = 1 + mean repair calls (READ: `docs/spec.md` §10). At the 50,000-call checkpoint with 3,000-call tuning, N* stays below 10,000 only while c_learned ≤ 2.29 (at 2.29 it is 10,000 exactly; at 3.0 it is 10,632 and the claim fails) (VERIFIED).
- **3,000 calls (about 2,000 of learning) means noisier tuning.** The configuration ranking comes from very short single-seed runs, so it may favour fast-starting settings over the best final one (assumption; a property of short tuning, not measured here). The spec's rule (0.5 percentage points with feasibility not lower) means few settings will beat the default, and a weakly tuned agent biases against RL, not for it. The chosen configuration is frozen at Gate 4 before any test data is touched.
- **N* counts only where feasibility and gap match the heuristic's at that checkpoint** (READ: `docs/spec.md` §10, "at equal feasibility and gap"). The heuristic has feasibility 1.0, gap 0.000% and no false abstentions on every set (READ: `docs/gate3_record.md`; 29,161 of 29,161 feasible contexts). The table is arithmetic about T, not a claim: at a checkpoint where the learned policy's verified feasibility is lower or its gap is above 0, there is no efficiency claim, whatever N* is. The spec states no tolerance for "equal"; A5 records the reading: feasibility, gap and N* are reported together, and the claim is made only where both match the heuristic's.
- c_conv depends on the set (heuristic means: V 14.193; T3 19.23, READ: `docs/verification_record.md`). The set used for P1 is fixed at the freeze.
- N* is computed against enumeration, ordered scan and heuristic iteration separately (READ: `docs/spec.md` §10); only the heuristic — the cheapest conventional method — is used above. The P3 comparator change does not touch N*.

## 6. Order of work

No RL training before Gates 1–3 are accepted and the relevant freeze exists (READ: `docs/spec.md` §12). Stage 2 needs its own gate: A4 (patch P14) and P15 verification before any Stage 2 run.

1. **Gate 3 acceptance.** The P9 criteria are met and the record is reproducible (READ: `docs/gate3_record.md`); the acceptance is recorded.
2. **A5 applied** — this trim, dated, before the affected runs.
3. **P8, trimmed**: categorical-native GA (budgets 20 and \|C\|) and MLP variant (i), run on T1–T5; every design of every seed stored and rechecked.
4. **P10 environments** (F0, F1, F2; R1 and R3; horizon 13 from A3). No RL training.
5. **P11 agent harness**, written so the agents and the call counter also serve Stage 2.
6. **P12a pilots** (right after P10 and P11): 3 seeds, 10,000 calls, V only, per entry, plus the 12-configuration tuning at 3,000 calls per configuration (V only). The pilots decide the R-C trigger and give the first look at S1 on V. They touch no test file, and their results change no success criterion.
7. **Stage 2 audit**: P14 (A4 and the welded checker, S355), P15 verification, P16 optimizer baselines and saturation diagnostics. Decision point: if the Stage 2 optimizers saturate quality and cost, the paper reports that — the success criteria are not changed to avoid it.
8. **P12b freeze**: the amended primary family, frozen configurations and R-C constants, test-file hashes, analysis pipeline tested on synthetic results, freeze tag.
9. **P13 Stage 1 runs** (the 30 trimmed runs plus the P8 baselines).
10. **P17 Stage 2 environments, agents and freeze**, then the Stage 2 runs.

Order note: `docs/patch_plan.md` lists P12 as one patch; this plan splits it (P12a before the Stage 2 audit, P12b after) and moves the freeze after the audit, following the parallel-work suggestion in `docs/project_review.md` §8. `docs/patch_plan.md` gets a matching dated edit when this order is applied.

**Stage 2 trim principle (for A4).** A4 will apply the same table method: at most two RL agents plus the hybrid, and the smallest optimizer set that still identifies the best per-problem optimizer. Kept: SLSQP, DE, CMA-ES, the supervised policy on optimizer labels, one continuous-control agent (SAC or TD3) and one increment-based agent (branching dueling Q), and the RL-then-optimizer hybrid. Optional: GA, PPO, and the second of SAC/TD3. Claims S3–S6 and P5–P8 are unchanged (A1 forbids weakening them).

## 7. Decisions recorded with A5

The project lead records all decisions. Where the spec asks for a supervisor confirmation (as A2 did, recorded 2026-11-10 in `docs/spec.md`), the lead records it in the supervisor's name.

1. Gate 3 acceptance.
2. A5 as a whole: the P3 comparator change DE → GA; dropping DE, MLP (ii)/(iii), R2 and R-D; the GA budget and ordering trim; the GA tuning protocol (12 configurations, V, seeds 0-2); the RL tuning budget of 3,000 calls per configuration (all calls counted); the R-C trigger; the F1 N* rule.
3. The T counting convention (one deployed policy: one training run, its own tuning and pilot). Under the alternative of counting all ten seeds, no checkpoint can meet the efficiency bar.
4. No tolerance for "equal feasibility and gap" in the spec: feasibility, gap and N* are reported together, and efficiency is claimed only where both match the heuristic's.
5. The Stage 2 trim principle of section 6, to be fixed in A4.
6. The order change: pilots right after P10/P11 (P12a), Stage 2 audit before the Stage 1 freeze (P12b) and runs (P13), with a decision point after P16.
7. The Gate 4 freeze as usual, with the amended primary family.

No RL training before items 1 and 2 are recorded. Checker, physics, objective, splits and success criteria are unchanged by this proposal.
