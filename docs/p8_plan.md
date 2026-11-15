# P8 plan: trimmed Stage 1 baselines II — categorical-native GA and supervised MLP (i)

Status: plan only, no code, 2026-11-15, branch `review`. Uncommitted until the plan is reviewed. P8 runs exactly what Amendment A5 kept: one GA and one supervised MLP. No RL. No change to the checker, physics, objective or splits.

Sources: spec §9 and Amendment A5 (READ: `docs/spec.md`); P8 acceptance line (READ: `docs/patch_plan.md`); the trim (READ: `docs/scope_trim_proposal.md` §4); P7 building blocks (READ: `src/ub_rl/baselines.py`, `src/ub_rl/runstore.py`, `scripts/run_baselines1.py`).

## 1. What P8 runs

- **GA (categorical-native)**: budgets 20 and |C| = 91, mass order only, seeds 0-9, on T1–T5 and the reference — 9,341 contexts (VERIFIED: T1–T5 9,337 + reference 4; READ: `docs/scope_trim_proposal.md` §4). Tuning per A5: 12 configurations on V, budgets 20 and |C|, seeds 0-2, with the calls added to the GA's cost (READ: `docs/spec.md` Amendment A5).
- **MLP variant (i)**: 2,197 labels = floor(200,000/91) (VERIFIED arithmetic; READ: `docs/spec.md` §9), enumeration labels at matched calls, trained on `train`, evaluated on T1–T5.
- Dropped by A5, so not run: DE, the other GA orderings and budgets, MLP variants (ii)/(iii) (READ: `docs/spec.md` Amendment A5).

## 2. The GA (definition decided here; the variant itself is fixed by A5)

Uniform crossover + random-section mutation (A5). Everything else is decided and recorded so the implementation has no free choices:

- **Chromosome**: k genes, each a section index; the design of a chromosome is its lightest feasible gene, -1 if none.
- **Population and budget**: population size p; generations run while evaluations remain, so a run makes **exactly `budget` distinct section evaluations** (asserted). A carried elite is not re-evaluated and costs 0. **Duplicate rule: a section already evaluated in this run costs 0 — it is never re-evaluated — and the slot is redrawn from the unseen sections (deterministic), so each run ends at exactly `budget` distinct evaluations** — the same distinctness convention P7 used for random search (READ: `src/ub_rl/baselines.py` line 20). The final partial batch evaluates only the remaining budget genes.
- **Fitness**: feasible sections ranked by mass (lightest best, ties by smaller index); infeasible sections ranked below every feasible one by their largest utilisation overrun, max(0, U_max − 1), least-infeasible first, then mass. The GA may walk through infeasible sections, which matters at budget 20. **The run summary records that the GA's fitness uses utilisation overrun for infeasible sections.**
- **Uniform crossover**: per gene position, the child's allele is parent A's or parent B's with probability 1/2 per gene. **Random-section mutation**: with probability m per gene, the allele becomes a uniformly drawn section.
- **Selection**: tournament of size t on fitness; elitism e ∈ {0, 1} carries the best-seen individual into the next generation.
- **Configurations**: grid = p ∈ {2, 4, 5, 10, 20}, k ∈ {1, 2, 4, 8}, t ∈ {2, 3, 4}, m ∈ {0.05, 0.1, 0.2, 0.5}, c ∈ {0.5, 1.0}, e ∈ {0, 1} (960 combinations). The 12 tuning configurations are `random.Random("ga-configs-2026-11-15").sample(grid, 12)` over the product in this fixed order — deterministic, asserted by a test (spec §9: "12 configurations … drawn by a fixed seed").
- **Determinism**: the per-run RNG is `random.Random(f"{seed}|{config}|{context_id}")` — the same NumPy-version-independent device P7 used for random orders (READ: `src/ub_rl/baselines.py` lines 126–135). The same (seed, context, config) reproduces the same run and the same call count (tested).
- **Tuning selection (A5)**: each of the 12 configurations runs on all 1,000 V contexts at both budgets with seeds 0-2; score = V mean gap with feasibility not lower (the §9 selection rule); the best configuration is recorded with its tuning calls — 12 × 1,000 × 111 × 3 = 3.996 M evaluations (VERIFIED arithmetic, matches the trim's 4.0 M row). **The first drawn configuration is the default; a later configuration replaces the current best only if the V mean gap improves by at least 0.5 percentage points with feasibility not lower, applied in draw order. The rule is recorded in the meta.** Gap is the mean over rows where the configuration outputs a design; feasibility is the share of (budget, seed, context) rows with a feasible output. The selected configuration is then run on T1–T5 and the reference with seeds 0-9. **Budget |C| equals the enumeration optimum by construction (all 91 sections are evaluated) and is asserted per context; the summary records the budget-91 result as a cost data point, not a GA-quality result.**

## 3. The MLP variant (i)

- **Labels**: the first 2,197 rows of `train.csv` in file order that have a feasible enumeration optimum (rows whose context has no feasible section are skipped in file order — decided, recorded in the meta). Label = the enumeration optimum section of the context, one-hot over the 91 sections. Costed both ways per §9 and both recorded in the meta: full enumeration, 2,197 × 91 = 199,927 calls; and the ordered-scan-with-certificate cost, sum of (optimum rank + 1) per label.
- **Features**: 12 inputs — span, tributary width, dead, live, restraint ratio, one-hot deflection rule (3), one-hot depth cap (4, including "none") — z-scored with train-set statistics (recorded).
- **Model**: 91-way softmax MLP, cross-entropy, Adam, PyTorch 2.5.1+cpu (VERIFIED available in `rl_env`), `torch.set_num_threads(1)`, fixed data order, no shuffle. Training costs 0 checker calls — the labels are already costed.
- **Configurations**: grid = hidden ∈ {1×64, 1×128, 2×64, 2×128}, lr ∈ {1e-3, 3e-4, 1e-4}, epochs ∈ {20, 40, 80}, batch ∈ {32, 64}; the 12 tuning configurations are `random.Random("mlp-configs-2026-11-15").sample(grid, 12)` in this fixed order (same §9 rule). Each configuration trains once on the 2,197 labels and is scored on V; the V evaluation calls (1 verification per context plus repair steps) are counted and added to the classifier's cost (spec §9: tuning calls are added to the training cost; for the classifier the "training cost" is the label cost, decided and recorded). **The same selection rule as the GA applies: the first drawn configuration is the default and is replaced only on a ≥ 0.5 percentage-point V mean-gap improvement with feasibility not lower, in draw order; recorded in the meta.**
- **Seeds 0-9**: `torch.manual_seed(seed)` before init and training; identical rerun outputs asserted by a test (spec §11 treats the classifier as a stochastic comparator trained with seeds 0-9, so it needs ten seeds).
- **End-to-end evaluation** (spec §9 procedure, reused): argmax output → verify (1 call) → if infeasible, step up in mass order until feasible (each step 1 counted call) → abstain at the end of C. Gap is reported against the enumeration optimum (P7's reference, recomputed by the run itself).

## 4. Call counting, storage, determinism

- **Counting**: reuse `baselines.CountingChecker` (READ: `src/ub_rl/baselines.py` lines 43–61). A GA population is one vectorised `evaluate_context(ctx, idx)` and counts `len(idx)` evaluations; the counter is the only source of call numbers (P7 convention: a method's own arithmetic is never trusted). Verification and repair calls are stored separately in the `verification_calls` column, exactly as P7 did (READ: `scripts/run_baselines1.py` line 52).
- **Storage**: reuse `runstore.write_results` / `load_results` with the P7 meta shape — `status: "complete"`, commit, environment-file SHA-256, catalogue and split SHA-256, checker config, hardware, thread limits, elapsed seconds, `n_section_evaluations` (READ: `src/ub_rl/runstore.py`; `scripts/run_baselines1.py` lines 101–124). Results go under `results/p8/` (git-ignored, never committed). Every written file is reloaded through the store before the run exits (P7 self-check).
- **Clean-tree rule**: the committed P9 record was regenerated from a clean tree, and the meta records `working_tree_dirty` (READ: `scripts/run_baselines1.py` lines 56–62). The full P8 run therefore happens only after the P8 code is committed and the tree is clean; the run asserts `data/splits/SHA256SUMS` before any evaluation (READ: `scripts/run_baselines1.py` lines 65–70).
- **Permutation order**: the later exact seed-level tests (P3, P12b/P13) enumerate the 10-vs-10 arrangements with `itertools.permutations` in lexicographic index order — a fixed, recorded order, so P8's seed-0-9 outputs are already its inputs. Decided and recorded here; nothing in P8 consumes it yet.

## 5. Files written by the run (under `results/baselines2/`, ignored)

- `ref_<file>.csv` + metas (the enumeration reference per context, for the gap denominators and the summary).
- `ga_tune.csv` + meta (12 configs × 3 seeds × 2 budgets on V), `ga_tuning_selection.json` + meta (chosen configuration, V gap, calls, the selection rule).
- `ga_<file>.csv` for `test_t1` … `test_t5`, `reference` (2 budgets × 10 seeds per context) + metas.
- `mlp_tune.csv` + meta (12 configs on V), `mlp_tuning_selection.json` + meta.
- `mlp_<file>.csv` for T1–T5 (10 seeds) + metas; `mlp_labels.json` + meta (the 2,197 contexts, labels and both costings).
- `run_summary.json` + meta (P7 shape; per-file feasibility, gap, calls; totals; both label costings; tuning totals; the GA fitness note and the budget-91 note).
- **Committed snapshot `paper/tables/baselines2_run_output.txt`**: the printed summary, the SHA-256 of the result files and the run commit, as P7's `baselines1_run_output.txt` (READ: `paper/tables/baselines1_run_output.txt`). Written by the run unless `--out` is given. Until the full run, the committed snapshot records the `--limit 100` sample run (stated in its header); the full run replaces it.

## 6. Tests (tests/test_baselines2.py), mapped to the P8 acceptance line

Acceptance line (READ: `docs/patch_plan.md` P8): *every baseline reports feasibility, gap and calls on T1 to T5* — the run summary asserts exactly that, and the tests enforce the properties below.

1. GA determinism: same (seed, context, config) → identical run and identical call count on a rerun.
2. GA budget: exactly `budget` distinct evaluations per (context, seed, config), read from `CountingChecker` (both budgets); a recording checker shows no section is evaluated twice in one run (the duplicate rule: already-seen costs 0 and the slot is redrawn from unseen).
3. GA outputs: every returned design is feasible on recheck; abstain only when no feasible section was evaluated; gap ≥ 0 always (the optimum is the lightest feasible section).
4. **GA budget |C| equals the enumeration optimum on every seed and context run** (asserted by the runner too; the summary records it as a cost data point, not a GA-quality result).
5. GA config draw: the 12 configurations are stable across runs (fixed seed, fixed grid) and all 12 are distinct.
6. Tuning rule: the first drawn configuration is the default; a replacement needs ≥ 0.5 percentage points of V mean-gap improvement with feasibility not lower, in draw order (unit test on synthetic scores; the rule is recorded in the meta).
7. MLP labels: 2,197 rows, each equal to the enumeration optimum on that context; both costings computed as §9 states (199,927 full-enumeration calls VERIFIED).
8. MLP determinism: same seed → identical model weights and identical V/T1 predictions on a rerun.
9. MLP end-to-end: repaired outputs are feasible; abstention at the end of C; verification calls counted as 1 per output, 0 per abstain.
10. Store: every written file reloads through `load_results`; a file without its meta (or a stale meta) is rejected (P7 tests reused).
11. Splits: the run refuses to start if a split file differs from `data/splits/SHA256SUMS` (P7 test reused).
12. P7 snapshot: enumeration equals ordered scan on every evaluated context, and the per-file feasible counts reproduce the P7 snapshot (the P9 assertion pattern; READ: `docs/gate3_record.md` line 3).

## 7. Compute: measure a sample first, then tell before the full run

- **Sample**: `python scripts/run_baselines2.py --limit 100` (100 contexts per file, incl. V for tuning) measures the wall time and writes nothing committed; the per-context rate is extrapolated to the full run and reported to the project lead before it starts (the project rule: tell before any heavy run).
- **Volume** (VERIFIED arithmetic, matches the trim's compute table): GA test sets 9,341 × 10 seeds × 111 = 10.37 M evaluations; GA tuning 3.996 M; MLP labels 199,927 plus V/test verification and repair calls (measured, small). Total about 14.6 M evaluations plus verification.
- **What to expect** (READ: `docs/verification_record.md`): P7's full run over 34,841 contexts took about 50 minutes on this machine (i3-3110M, single-threaded); P9's full diagnostics were measured at about 2 minutes in 2026-11, but the 2026-11-15 regeneration of the Gate 3 record was much slower (it exceeded 10 minutes), so the old rates are not trusted — **the 100-context sample is the authority**, and the full run starts only after the measured extrapolation is reported.

## 8. Assumptions (decided, recorded)

1. "On T1–T5 and the reference" (GA) and "evaluated on T1–T5" (MLP) are read literally: the MLP is not evaluated on the 4 reference contexts.
2. The 12 GA/MLP configurations are drawn from the fixed grids above with the fixed seeds above; "drawn by a fixed seed" (spec §9) is implemented as `random.Random` over the grid in the listed product order.
3. GA budget = exactly `budget` distinct section evaluations; carried elites cost 0; the last generation is truncated to the remainder.
4. MLP training uses the first 2,197 rows of `train.csv`; training itself costs 0 checker calls; MLP tuning calls are added to the classifier's label cost.
5. The MLP's matched-call position for P2 is reported with both label costings; which costing the P2 match uses is fixed at the freeze (P12b), not here.
6. Tuning V rows and test rows are stored separately; the selected configuration is the only one run on the test files.
7. The permutation order for the exact seed-level tests is `itertools.permutations` in lexicographic index order, fixed and recorded.
8. The tuning score pools both budgets (a configuration is selected once and used at both); gap is the mean over rows with a feasible output, feasibility is the share of (budget, seed, context) rows with a feasible output; a configuration with no feasible output has gap = infinity and never replaces the default unless the default also has none.
9. The committed snapshot is written by the run unless `--out` is given (tests use `--out`, so they never touch the committed file).
10. Train rows whose context has no feasible section cannot carry a 91-way label; they are skipped in file order and the count is recorded in the labels meta.

## 9. What P8 does not do

No RL training, no environments, no agent code; no checker, physics, objective or split changes; DE, MLP (ii)/(iii), R2/R-D are not run (A5); results are not committed and no claims are computed — P13 does the analysis. `docs/verification_record.md` gains the P8 entry when the patch is delivered (patch-plan rule).
