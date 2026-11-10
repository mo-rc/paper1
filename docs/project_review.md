# Project review (independent, end to end)

**Reviewer role:** senior research engineer joining mid-way. **Date of review:** 2026-11-10. **Branch:** `review` (local, off `main` at 5df1869).
**Environment used:** project conda env `rl_env` (Python 3.12.12, pytest 9.1.1, numpy 2.3.5, scipy 1.17.1) — the same versions quoted in `docs/verification_record.md`.
**Assumption (unverified):** local `main` equals origin/main head. `git status` showed `## main...origin/main` with no ahead/behind marker; a `git fetch` was declined, so this is stated, not checked.
**Marks:** VERIFIED = I ran it or read the file it names; READ = I read the claim in a repo file but did not reproduce it.

**Revision note (2026-11-10, documentation-only):** corrections applied directly in the working tree on the `review` branch: (1) the P7/P8 context count is stated exactly (section 6) — 34,841 is the total of all split files, not of train/val/T1–T4 (26,500); (2) `docs/proposal.md` §5 now carries the A2 depth caps with a dated note preserving the original values; (3) `docs/patch_plan.md` P6 now records the formal acceptance by the supervising engineer Dr Mudasir Hussain (2026-11-10), P7 states the exact context scope, and P8's acceptance line is corrected from "T1 to T4" to "T1 to T5" to match Amendment A2; (4) stale Gate 2 wording in `tests/test_ltb.py` fixed; (5) README now references A2; (6) the untracked duplicate `Final_Research_Proposal (1).md` (byte-identical to `docs/proposal.md`) was removed. An optional record of these edits is `patches/0001-review-clarifications.patch`; `patches/` is a record directory only (see `patches/README.md`), not part of the build, the tests or the registered methodology. **Same-day update:** the supervisor's approval of Amendment A2 — the depth caps none/700/800/900 mm and the T5 lattice as a test set, with the seven-parameter ranges and frozen splits — was recorded in `docs/spec.md` A2 (2026-11-10); the proposal, README and patch plan now carry the approved values, and finding H2 is closed. The formal acceptance of P6 by the supervising engineer, Dr Mudasir Hussain (2026-11-10), is recorded in `docs/patch_plan.md`; finding M1 is closed. No engineering or experimental code, data, hash, split, reward, environment or protocol was changed.

Glossary (one line each, for the AI engineer):
- **Beam**: horizontal member carrying load between two supports; here a simply supported steel I-beam.
- **UB (Universal Beam)**: a standard rolled I-section size family from the SCI Blue Book catalogue.
- **UDL**: uniformly distributed load (kN/m along the beam).
- **Utilisation**: demand / resistance; a check passes if ≤ 1.0, so 0.998 means 99.8 % of capacity used.
- **LTB (lateral-torsional buckling)**: sideways twisting failure mode of a beam under bending, worse with fewer lateral restraints.
- **Restraint ratio**: distance between lateral restraints divided by span; 0 = fully restrained, 1 = restrained at supports only.
- **Web bearing**: local crushing of the web (the vertical plate) where the load sits at a support.
- **Shear buckling**: web plate buckling under shear; only 2 of the 107 sections are slender enough to need it here.
- **Deflection**: how far the beam sags; a serviceability limit (span/360 etc.), not a collapse check.
- **Depth cap**: a floor-to-floor depth limit on the section; a design requirement, not a code check.
- **Abstention context**: a load situation where no catalogue section passes; the method must say "no design" instead of guessing.
- **Saturation**: a baseline already reaches the exact optimum almost always, leaving no quality headroom for learning.
- **Checker call**: one evaluation of a context against a catalogue; the unit of cost for every method.
- **Break-even N\***: training cost divided by per-design savings; the number of designs after which the learned method is cheaper.
- **Gate**: a frozen checkpoint (0–5) in the pre-registered plan; RL training is forbidden until Gate 3 is accepted.

---

## 1. The project in 10 lines

1. Question: can an RL policy select the lightest safe UK Universal Beam (S355, UDL, Eurocode 3 with UK National Annexes) faster or cheaper than enumeration, ordered scan, heuristic iteration, GA/DE and supervised learning? Tested, never assumed; a negative result is a valid, pre-registered outcome (`docs/spec.md`, section 11).
2. The checker (physics) is done and Gate-2 accepted: 7 checks (classification, bending, shear, shear buckling, interaction, web bearing, deflection) plus LTB, verified against a second implementation, 14 hand-checked cases, public SCI numbers and all 107 Blue Book resistance rows (`docs/verification_record.md`, `docs/gate2_signoff.md`).
3. Stage 1 is categorical: pick one of 91 UB sections (107 with "+" rows as sensitivity C+); the optimum is defined by exhaustive enumeration, which is exact by construction.
4. The context has 7 parameters (span, width, dead, live, restraint ratio, deflection rule, depth cap); splits T1–T5 plus the v1.2 two-parameter sub-study are frozen files with SHA-256 (`docs/spec.md`, Amendment A2).
5. Stage 2 (welded I-sections, the paper's intended main result) is planned but nothing exists yet; it needs its own amendment (A3) and Gate-2-style verification.
6. Method: tournament of RL formulations (F0 direct choice, F1 refinement MDP, F2 constructive/GFlowNet) and agents (DQN family, discrete PPO/SAC, policy gradient, GFlowNet), 10 seeds, 200k checker calls per run, tuning on validation only.
7. Fairness machinery is pre-registered: hashed frozen tests, exact permutation/sign-flip tests, Holm correction, cost in checker calls including training and tuning, break-even N*.
8. State: D1–D7 and P6 done; P7–P13 (baselines, environments, agents, pilots, runs) and P14–P23 (Stage 2, delivery) planned in `docs/patch_plan.md`; no RL code exists and no RL has been run (rule: no training before Gate 3).
9. The main pre-loaded risk: preliminary diagnostics (unverified checker) show heuristic iteration already finds the exact optimum at a mean 2.6 calls, which leaves no quality headroom and makes the efficiency claim hinge on the 10,000-call budget (`docs/preliminary_diagnostics.md`).
10. Delivery target: one journal paper, app prototype, optional Abaqus check, clean-clone reproducibility (`docs/proposal.md`, section 8).

## 2. Commit timeline by phase

VERIFIED from `git log` (18 commits, 2026-10-17 → 2026-10-25; author dates as below).

| Date | Commits | Phase |
|---|---|---|
| 2026-10-17 | a95bc71, 53a9052, a1f7e52, 19c6a58 | Spec v1.0 → v1.2 (RL formulations, rewards, baselines, statistics, gates); preliminary diagnostics |
| 2026-10-18 | 0159d49 | Patch 0004: catalogue parser + vectorised EC3 checker + tests |
| 2026-10-19 | 208dff3 | Amendment A1: LTB check, seven-parameter `Context`, one-paper proposal |
| 2026-10-20 | f0f4d5f | Gate 2 evidence (second implementations, SCI benchmarks, Blue Book comparison; found curve-d and G corrections) |
| 2026-10-21 | 7e317dc, 8269dfe | Patch plan, engineering review request, worked example; A1/proposal alignment |
| 2026-10-23 | 8caf275, c38da04, 1884281 | Hand check (Muhammad Shifa, 234 values); **Gate 2 accepted** (supervisor sign-off); engineering concepts doc |
| 2026-10-24 | 0b7e65e | P6: Amendment A2 (seven-parameter box, splits T1–T5, v1.2 sub-study), feasibility audit, hashes |
| 2026-10-25 | dc82a6a, 7c67101, 000bd23, 09a7ec0, 5df1869 | How-to-run doc; P6b review fixes; P6c plan corrections (P7/P9/P10/P12/P13); P6d paper readiness; P6e reproduction record |

## 3. Done and verified / assumed / pending

### Done and verified (I ran it, 2026-11-10)

- `python -m pytest -q` → **155 passed**, 0 skipped, 33.8 s (VERIFIED; matches the 155 in `docs/how_to_run.md`).
- `python scripts/context_audit.py --check` → **checked 22 files; differing or missing: none**, 125.8 s (VERIFIED; matches `docs/verification_record.md` P6 and the "22 files" expectation).
- `python scripts/reference_case.py` → **lightest feasible = 457x191x74** for both C and C+; bending utilisation 0.998 (VERIFIED; matches `docs/how_to_run.md` and the G2-01 case).
- Workbook SHA-256s in `data/raw/` match the recorded values: properties `190e17b6…` (`docs/spec.md` §4), bending `c2fedba5…` and bearing `fb34eee1…` (`src/ub_rl/bluebook.py`) (VERIFIED by `sha256sum`).
- Environment-file hashes quoted in `docs/context_audit.md` provenance match the working tree: `src/ub_rl/checker.py` `3b6ab914…`, `src/ub_rl/splits.py` `f3db23c9…` (VERIFIED).
- Split sizes match Amendment A2 and `tests/test_splits.py` (train 20,000; val 1,000; T1 2,000; T2 500; T3 1,500; T4 1,500; T5 3,837; v12 4,500; reference 4) and the abstention list counts match `paper/tables/audit_sets.csv` exactly (VERIFIED by `wc -l`).
- Doc numbers vs tables: `docs/context_audit.md` is regenerated byte-identically by `--check`, so every number in it matches `paper/tables/audit_*.csv`; spot checks of spec-A2 numbers (abstention 0.1638 / R2 0.4803 / E1 61.2 % / E3 77.8 % / 68+1 uncarriable / 1,335 C+ rescues / 19 % lighter in C+) all match the tables (VERIFIED).
- Break-even arithmetic in `docs/preliminary_diagnostics.md` recomputes: 200,000/(2.6−1)=125,000; /(53−1)=3,846; /(91−1)=2,222 (VERIFIED by arithmetic).
- No RL/learning code exists in `src/` or `scripts/` (only checker, context, splits, catalogue, Blue Book, audit) — the "no RL before Gate 3" rule is intact (VERIFIED by file listing).
- The Blue Book comparison tests ran (not skipped) and pass, i.e. class/Mc/Iy 107/107, Vc 107/107, FRd 1,323 values, Mb,Rd 12,733 values all within table rounding (VERIFIED via pytest with the workbooks present).

### Done, accepted, but not re-verified by me (READ)

- Gate 2 sign-off: 12 assumptions agreed, form signed by the supervising engineer (Dr. Mudasir Hussain, 23 October 2026); hand recomputation done by Muhammad Shifa (234 values, max 0.28 %), not by the supervisor (`docs/gate2_signoff.md`, `docs/review_request_signed.md`).
- The correctness of the physics formulas as readings of EN 1993-1-1/-1-5: several clause details were taken from public secondary sources and "not read from the standards" (`docs/verification_record.md`, "Not confirmed") — the Blue Book comparison is the anchor evidence.
- The `v1.2` spec text kept unchanged as a historical record after A1/A2 superseded parts of it (the spec's own convention; `docs/spec.md` amendments).

### Assumed

- Local `main` = origin/main head (fetch not run; stated above).
- `rl_env` is the project's own environment and its installed `ub-rl` points at this checkout (tests pass via `pyproject.toml` `pythonpath = ["src"]`, so they exercise the repo copy either way).
- The signed Gate 2 form is genuine as recorded.

### Pending (recorded in-repo, not done)

- Supervisor acceptance of A1/proposal (the other sign-offs are done: A2 supervisor-approved, recorded 2026-11-10 in `docs/spec.md` A2; P6 formally accepted by the supervising engineer Dr Mudasir Hussain on 2026-11-10, recorded in `docs/patch_plan.md` P6).
- Gate 3: baselines (P7, P8), landscape + saturation + reward-ordering asserts (P9), then acceptance.
- Gate 4: environments (P10), agents (P11), pilots + analysis pipeline + freeze (P12).
- Stage 1 runs (P13) and everything from P14 (Stage 2 amendment) to P23 (release).

## 4. Findings, ranked

### High

**H1 — The efficiency claim is pre-loaded to fail at the full 200k-call budget; the 10k-call curve is the make-or-break evidence.**
Evidence (READ): `docs/spec.md` §10 defines N\* = T/(c_conv − c_learned) and §11 allows the efficiency claim only if N\* vs heuristic iteration < 10,000; `docs/preliminary_diagnostics.md` (unverified checker, exploratory) measures heuristic iteration at mean 2.6 calls and computes N\* ≈ 125,000 at T = 200,000. With c_learned ≥ 1, N\* < 10,000 requires T < 16,000 calls, so the pre-registered claim can only survive if RL reaches the required quality at the 10,000-call budget. This is not a defect — the spec anticipates exactly this (sample-efficiency curves at 10k/50k/200k; saturation rule; negative result valid) — but it decides the paper's headline. Fix: treat P9's saturation outcome and the 10k-call curve as the primary efficiency evidence; prepare the negative-result narrative (already pre-registered) rather than expecting the 200k-call budget to win.

**H2 — The frozen Stage 1 splits rested on unconfirmed A2 values (RESOLVED 2026-11-10).**
Evidence (READ): `docs/spec.md` A2 changed depth caps from none/500/600/700 to none/700/800/900 after a checker-only feasibility look (`paper/tables/audit_cap_alternatives.csv`: caps 500/600 leave 70–100 % of contexts infeasible); Gate 2 sign-off predates this change and covers only the 12 assumptions of the checker. Since the caps change the feasible set and the optimum, all Stage 1 results were conditional until confirmed (the spec's own rule, §15). **Resolved 2026-11-10:** the supervisor's approval of A2 — the depth caps none/700/800/900 mm and the T5 lattice as a test set, with the seven-parameter ranges and frozen splits — is recorded in `docs/spec.md` A2; `docs/proposal.md` §5 and the README carry the approved values. The remaining condition on Stage 1 results is Gate 3 acceptance, not A2 confirmation.

### Medium

**M1 — P6 acceptance is now formally recorded (RESOLVED 2026-11-10).**
Evidence (READ): the P6 technical delivery is complete and reproducible (`docs/verification_record.md` records the reproduction, dated 2026-10-25). **Resolved 2026-11-10:** `docs/patch_plan.md` P6 records the formal acceptance — the supervising engineer, Dr Mudasir Hussain, accepted P6 on 2026-11-10.

**M2 — Stage 2 (the paper's intended main result) has a heavy verification backlog and its key parameter sources are not yet read.**
Evidence (READ): `docs/spec.md` A1 §6 requires Amendment A3 before any Stage 2 run and lists open items: welded LTB parameters (lambda_LT,0 = 0.2, beta = 1.0 "as reproduced in software documentation, not yet read from the NA text"), h/b > 3.1 handling, fabrication increments, Stage 2 splits and baselines; P15 needs an independent engineer's calculation and sign-off like Gate 2. Fix: schedule P14 early enough for the A3 decisions to be reviewed by the supervisor; start looking for the Stage 2 verifier (an engineer who did not write the code) now, not at P15.

**M3 — The hand check and second implementations were written by the project team; the only genuinely independent layer is the supervisor's assumptions review plus Blue Book tables.**
Evidence (READ): `docs/gate2_signoff.md` ("His sign-off rests on the assumptions and on the recorded hand check. The supervising engineer did not recompute each case independently"), `docs/verification_record.md` (second implementation "checks the arithmetic, not the understanding of the standard"). The Blue Book comparison is strong (VERIFIED passing), but clause-level errors that agree with the Blue Book would be invisible to it. Fix: acceptable as is for Gate 2; for Stage 2 (P15) press for at least a few genuinely independent recomputed cases, not just assumption sign-off.

### Low

**L1 — Stale docstring:** `tests/test_ltb.py` line 1 still says "Not Gate 2: Blue Book Mb,Rd comparison and a second implementation are still required"; both now exist (`tests/test_bluebook.py`, `tests/test_ltb_reference.py`) and pass (VERIFIED). **Fixed in patch 0001 (2026-11-10):** the module docstring now points at the Gate 2 evidence and the sign-off.

**L2 — Untracked duplicate proposal:** `Final_Research_Proposal (1).md` at the repo root is byte-identical to `docs/proposal.md` (VERIFIED by `diff`) and is untracked; it duplicates the stale cap values of H2. **Fixed in patch 0001 (2026-11-10):** verified untracked (`git ls-files --error-unmatch` fails) and byte-identical, then removed; `docs/proposal.md` is tracked, so nothing was lost.

**L3 — `docs/how_to_run.md` says pytest takes "about 15 seconds"; I measured 33.8 s** on this machine (VERIFIED). Harmless, machine-dependent. Fix: reword to "about half a minute" or leave as is.

**L4 — README's research-proposal paragraph mentions only A1**, not A2; a new reader may not notice the splits/spec changes. **Fixed in patch 0001 (2026-11-10):** the paragraph now points at Amendment A2 (caps, ranges, splits, SHA-256).

**L5 — No CI** (`.github/` absent; VERIFIED). The two reproducibility commands (pytest, `--check`) are cheap enough to run as CI. Fix: optional; add a workflow later if the team wants automatic guards.

**L6 — Cosmetic dead code:** `src/ub_rl/checker.py:167` computes `q = Qk + 0.0 * g` in the variable-deflection branch (self-weight is intentionally excluded there). Harmless; a comment would be clearer than `0.0 * g`.

## 5. Open questions for the supervisor (plain words, each with a default)

1. ~~Do you confirm the Amendment A2 choices (depth caps none/700/800/900 mm, and the T5 lattice as a test instead of training on lower/real/upper values)?~~ **Answered 2026-11-10:** the supervisor approved the A2 choices (depth caps none/700/800/900 mm; T5 lattice as a test); the approval is recorded in `docs/spec.md` A2.
2. **Do you accept the proposal (Amendment A1): seven context parameters, two-stage design (catalogue, then welded sections), about 28 weeks?** Default: accept; the spec already treats it as the working plan.
3. **Can you commit to the Stage 2 verification (P15): an independent engineer's calculation and sign-off of the welded-section checker?** Default: proceed to P14 (the A3 amendment) in parallel with finding the verifier; if none is available, the paper falls back to Stage-1-only claims, which is a pre-registered valid outcome.
4. **Is Abaqus available for the finite-element check of ~10 designs (P20)?** Default: if not, record "not done" and say so in the paper (already the plan's fallback).
5. **What journal is the target?** Default: decide after results; aim high, title finalised later (as the proposal says).

## 6. Complete plan from P7 to submission

Gates and budgets follow `docs/patch_plan.md` and `docs/spec.md` §9–12. Compute estimates are my extrapolations from measured numbers (audit check 126 s for ~31,000 contexts × 2 catalogues + tables; pytest 34 s); RL runtimes are order-of-magnitude guesses, marked "estimate" — measure on the first pilot run and rescale before committing to P13. Everything runs single-threaded; hardware must be recorded in `*_meta.json`.

| Patch | Purpose (one line) | Files | Acceptance test | What I run | Compute | Gate |
|---|---|---|---|---|---|---|
| **P7** | Baselines I: enumeration, ordered scan, heuristic iteration, random search; checker-call accounting; result store with `status: complete` + `*_meta.json` (commit, environment SHA-256); single-thread timing harness | new `src/ub_rl/baselines.py`, `src/ub_rl/runstore.py`, `scripts/run_baselines1.py`; `tests/test_baselines1.py` | enumeration == ordered scan optimum on every context; per-method call logs; a result file without its meta file is rejected | `pytest`; run baselines over all split files (34,841 contexts = train 20,000 + val 1,000 + T1–T5 9,337 + reference 4 + v1.2 4,500; train/val/T1–T4 alone is 26,500) | minutes on one CPU (vectorised checker; measured ~126 s for a similar sweep) | Gate 3 |
| **P8** | Baselines II: GA and DE (mass order + 3 random permutations + categorical-native), supervised MLP in 3 variants at matched call budgets; 12 configs each, selection on V only | new `src/ub_rl/baselines_evo.py`, `src/ub_rl/supervised.py`, `scripts/run_baselines2.py`; tests | every baseline reports feasibility, gap and calls on T1–T5 (A2) | `pytest`; run scripts | minutes for the MLP; GA/DE over 34,841 contexts ≈ tens of minutes to a few hours (estimate) | Gate 3 |
| **P9** | Landscape + saturation diagnostics; reward-ordering assertion for R1/R2/R3/R-C/R-D on every V context (float64 log-space); Gate 3 record stating the saturation outcome | new `scripts/landscape_diagnostics.py`, `src/ub_rl/reward_checks.py`; `docs/gate3_record.md`; tests | diagnostics reproducible by one script; record states saturation per context set | `pytest`; run the script | minutes | **Gate 3 acceptance** |
| **P10** | Environments F0/F1/F2 with rewards R1/R2/R3/R-C/R-D (unit semantics: horizon 12, no-op at catalogue ends, one checker call per sampled section) | new `src/ub_rl/envs.py`; `tests/test_envs.py` | unit tests pass; ordering assertion (from P9) still passes | `pytest` | seconds | Gate 4 prep |
| **P11** | Agents and training harness: DQN, Double/Dueling DQN (PER, n-step), discrete PPO, discrete SAC, REINFORCE+baseline, conditional GFlowNet (TB); config-driven, seed control, call counters, checkpoints | new `src/ub_rl/agents/*.py`, `scripts/train.py`, `configs/*.yaml`; tests | each agent trains on a toy context set and reproduces its result for the same seed | `pytest`; toy runs | minutes per toy run | Gate 4 prep |
| **P12** | Pilots on V only (3 seeds, 10k calls); hyperparameter protocol (12 configs, V selection); analysis pipeline (gap, feasibility, N*, bootstrap, sign-flip/permutation, Holm, tables/figures) tested on synthetic results; freeze and tag | new `src/ub_rl/analysis.py`, `scripts/make_tables.py`, `scripts/make_figures.py`; tests on synthetic data | tag exists; pipeline tests pass; spec amendment records frozen choices | `pytest`; pilot runs | minutes per pilot (10k calls) | **Gate 4 freeze** |
| **P13** | Stage 1 runs and analysis: 10 seeds × ~11 entries (8 algorithm-formulation + 3 reward variants) × 200k calls; break-even N*; P1–P4 confirmatory comparisons; T1–T5 generalisation; diversity (F2); figures/tables from saved results only | scripts for batch runs; analysis outputs to `results/` and `paper/tables/` | every claim maps to a pre-registered comparison; claim made only if its criteria are met | `pytest`; batch runs; analysis | **heavy**: ~110 runs × 200k calls; rough estimate 1–4 CPU-days on one machine (measure at pilot scale first, then rescale; tell the lead before launching the full batch) | Gate 4 |
| **P14** | Amendment A3 (Stage 2): welded-section model and checker; design variables/bounds, class and h/b limits, fabrication increments, welded LTB parameters, splits, baselines, budgets | spec amendment; new `src/ub_rl/welded.py`; tests | unit tests pass; reproduces rolled-UB resistances to a stated tolerance when given UB plate dimensions | `pytest` | seconds–minutes | before any Stage 2 run |
| **P15** | Stage 2 verification: second implementation, generated hand-check cases, independent engineer calculation, verification record entry | docs + `tests/` additions | signed as in P5 (Gate 2) | `pytest`; hand-check workbook route | minutes + engineer time | Stage 2 Gate |
| **P16** | Stage 2 baselines and audit: SLSQP, DE, GA, CMA-ES, supervised policy on optimizer labels; saturation; frozen Stage 2 test sets and budgets | new baseline modules; audit script | as P9 | `pytest`; audit run | minutes–hours (estimate) | Stage 2 Gate |
| **P17** | Stage 2 environments, agents, hybrids (RL warm-starts optimizer); pilots on V; freeze and tag | extensions of envs/agents; tests | as P12 | `pytest`; pilots | minutes per pilot | Stage 2 Gate |
| **P18** | Stage 2 runs and analysis: non-inferiority on mass (2 pp), cost, hybrid warm-start | batch scripts; analysis | as P13 | `pytest`; batch runs | **heavy**: similar scale to P13 (estimate) | Stage 2 |
| **P19** | Efficiency and break-even analysis in calls and wall-clock (cheap, 1 ms, 1 s per call); sensitivity to N_ref (threshold unchanged) | analysis scripts; tables | every efficiency claim has its break-even and assumption stated | scripts | minutes | after P13 |
| **P20** | Abaqus verification of ~10 designs (Mcr, deflection) | scripts to generate inputs and compare | differences tabulated and explained; or recorded "not done" if no Abaqus access | depends on access | external software | optional |
| **P21** | Web app: inputs → several distinct verified designs → utilisation table, governing check, report; re-verify on display | new `app/` | app output equals checker for reference cases | `pytest`; manual run | seconds | delivery |
| **P22** | Manuscript (Gate 5): numbers only from `results/` and `paper/tables/`; claims limited to met criteria | `paper/` | a script lists every number in the text with its source file, none missing | the audit script | seconds | **Gate 5** |
| **P23** | Release: final figures/tables from saved runs, locked environment, README with exact commands, data/code release without the licensed workbooks | repo hygiene | a clean clone reproduces every number in the paper | clean-clone run-through | hours (one-off) | delivery |

Suggested order and durations: P7+P8 first (parallel-able), then P9 immediately (it decides the headline), then P10–P12, P13. Start the A3 amendment (P14) and the P15 verifier search while P13 runs. Total to submission, roughly per the proposal's 28-week envelope (weeks 8–28; about 20 weeks from now, less if P13 compute is scheduled well).

## 7. What the paper can and cannot claim; what reviewers will ask

**Can claim (only if the pre-registered criteria in `docs/spec.md` §11 and A1 §6 are met):**
- A verified, open Eurocode 3 (UK NA) environment for UB design with the documented verification chain.
- Benchmark results: safety (verified feasibility), generalisation (T1–T5), quality (gap to the exact optimum), cost (checker calls, training and tuning included, break-even N*), diversity, for every method run.
- "RL better than X" only for the four pre-registered comparisons P1–P4 (Stage 1) and P5–P8 (Stage 2), each with all three of: Holm-corrected seed-level p < 0.05, a context-level 95 % interval excluding zero, and a practical margin; everything else labelled exploratory.
- A negative result as the headline if the criteria are not met: "learned design is not worth it here, and this is when" — explicitly a registered, valid outcome.

**Cannot claim:**
- Better solution quality than enumeration (exact within C by construction; `docs/spec.md` §7).
- Safety beyond the checker's scope: no frames, connections, fire, vibration, composite action, torsion, axial force; top-flange loading unvalidated; single span, UDL only, S355 UB only (§13, Gate 2 sign-off "does not cover" list).
- Transfer to other sections, grades, welded or unrestrained beams (until Stage 2 passes its own gate), or to any real building without engineering verification ("outputs are recommendations", §13).
- Any Stage 2 claim before A3 and P15 sign-off; any efficiency claim without a finite N* under the stated assumptions.
- Anything not traceable to a saved result file (Gate 5).

**What reviewers will ask (and where the answer lives):**
- "Why RL when a 2.6-call heuristic already finds the exact optimum?" → the saturation rule (§12) and P9's outcome; the honest answer is diversity, amortization, and the expensive-check regime — or a negative result.
- "Is the checker really verified?" → Blue Book comparison (12,733 Mb,Rd values), second implementation, 14 hand-checked cases, supervisor sign-off; but be ready to name what was not read from the standards text (`docs/verification_record.md`, "Not confirmed").
- "Why is top-flange loading excluded?" → not validated by the Blue Book tables; recorded, not used (§ A1 change 1).
- "Why are restraint ratios in (0.5, 1) rejected?" → a known model artefact near ratio 1 (factor jump); documented with the sensitivity numbers (§ A1 change 2, verification record).
- "Are the test sets really unseen?" → hashed frozen files, T2 hole, T4-A held-out cells, T4-B unseen restraint value, T3 extrapolation; freezing at Gate 4.
- "Is the cost accounting fair?" → training + tuning + label calls counted, break-even N*, single-thread wall-clock with recorded hardware (§10).
- "Multiple comparisons?" → Holm over 4 comparisons, 10 seeds for attainable p-values (§11).
- "Can readers reproduce it?" → P23 clean-clone test; workbooks excluded by licence with instructions to obtain them.
- "Is the catalogue choice realistic?" → "+" rows' availability unrecorded, kept out of C; C+ as sensitivity (§ A2).

## 8. Top three next actions

1. **Close the sign-off gap:** get the supervisor's acceptance of the proposal (A1) — the last open sign-off. Done already: A2 approval (recorded 2026-11-10 in `docs/spec.md` A2), P6 formal acceptance (Dr Mudasir Hussain, 2026-11-10, `docs/patch_plan.md`), and the documentation fixes (proposal note, README A2 pointer, duplicate proposal file removal). One day, no code.
2. **Deliver P7, then P8** (baselines and run infrastructure): unblocks everything and gives the first real numbers with the verified checker. Days of work, minutes–hours of compute.
3. **Run P9 (saturation + landscape diagnostics) immediately after P7** — it determines whether the paper's headline is a positive or negative RL result, so the manuscript framing can be decided early rather than at P13.
