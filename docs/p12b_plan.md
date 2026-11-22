# P12b pre-registration freeze — plan only

No analysis implementation, test run, test-set evaluation, or Stage 1 training is authorized by this plan. The approved spec governs. **READ** — `docs/spec.md:178`.

## Analysis pipeline

- Implement frozen metric calculations for verified feasibility, gap, exact match, utilisations, abstention precision/recall, diversity, calls, wall time, and seed spread. Keep training/inference and split reports separate. **READ** — `docs/spec.md:148-152`.
- Implement N* and report “no break-even” when the denominator is non-positive; compute against enumeration, ordered scan, and heuristic iteration separately. **READ** — `docs/spec.md:152`.
- Implement context-level paired bootstrap: 10,000 resamples of mean per-context differences averaged over seeds, with 95% intervals. Implement exact two-sided seed sign-flip tests for deterministic comparators and exact two-sided seed-mean permutation tests for stochastic comparators; apply Holm over the four primary comparisons. **READ** — `docs/spec.md:164-170`.
- Preserve the registered claim rule: Holm-adjusted p < .05, context interval excludes zero, and practical margin is met. Report effects and intervals; label other comparisons exploratory. **READ** — `docs/spec.md:170`.
- Write analysis and table/figure-generation scripts to consume saved result artifacts only. Test every statistical branch and generated table/figure path on synthetic fixtures only; no real Stage 1 result is read before freeze. **READ** — `docs/spec.md:170,178,180`; `docs/patch_plan.md:37,41`.
- Synthetic checks cover metric denominators/abstentions, N* eligibility and undefined denominator, bootstrap interval construction, exact test p-values, Holm adjustment, and deterministic table/figure generation. **Assumption** — these fixture cases operationalize the registered methods; no source outcome determines them. **READ** — `docs/spec.md:148-152,164-178`.

## R-C freeze

- R-C keeps environment reward R1 and adds `lambda * c`, where `c=max(0, max utilisation - 1)` for the accepted design; dual ascent is `lambda <- max(0, lambda + eta * (mean c - 0))`. Freeze exactly: initial multiplier `lambda_init`; learning rate `eta`; update schedule (cadence and observations included in `mean c`); seed set; checker-call budget and checkpoint schedule. **READ** — `docs/spec.md:246,128,367`.
- A5 says R-C runs on the best F1 entry only if its pilot trigger fires, and otherwise is not run. R2 and R-D are not run unless reinstated by a later dated amendment. **READ** — `docs/spec.md:367,385`.
- **Assumptions to resolve and record before P13:** A5 does not give numeric `lambda_init`, `eta`, or the dual-update cadence/statistic; set and freeze these in the P12b spec amendment, without inferring values from the equation. Use seeds 0–9 and 200,000 checker calls per run with the registered 10k/50k/200k checkpoints for a triggered full Stage 1 R-C entry. **READ** — `docs/spec.md:128,367,385`.

## N* claim eligibility

- Use `N* = T / (c_conv - c_measured)`; it is defined only when `c_conv > c_measured`. **READ** — `docs/spec.md:152`.
- A checkpoint is claim-eligible only if, on that comparison set, repaired feasibility is 1.0 and mean gap is at most 0.5 percentage points; report feasibility, gap, and N* together. Do not promote an arithmetic N* at a failing checkpoint to an efficiency claim. **READ** — `docs/spec.md:160,387`.
- Use measured per-design cost including F0/F2 verification and repair, or F1 step count plus repair; retain the registered T accounting. **READ** — `docs/spec.md:152,381,383`.

## Frozen configurations and files

- Freeze the three A7 D5 selected defaults (slot 1): F0-R1 SHA-256 `51b51edf334b9e06e9455bf6dfc58f4576311c55fbe2230ca366f21c50b4e255`; F1-R1 `cd66365bf31408dc9cc7912311d6841b7af9ecf999b7f4c91d43b07472787977`; F2-R3 `c27e3e50cd834369e21c86e659a33194813e38a3cb5ca9d6f4f6170154305750`. **READ** — `docs/verification_record.md:307-311`; `results/p12a/manifest.json:35504-35529,103004-103035,109676-109702`.
- Record the five frozen test split hashes: T1 `017e9af9fe717ddee9d52602556af20ed9c43a235d062e706468ac7099c05866`; T2 `b3fe99a72f38633118c70b600e8358140768bc15d3a7db62e5a0b5fe117aa779`; T3 `f6121c825afa15ce4beb9b3ddaad970638be18953a574c5f55e161750aef1129`; T4 `1603fc4517b341ebf316fcd9e1612d1b664d06e119cba62c750ee369d1fab2ea`; T5 `72e0a67a1025af5beee7efdc5ba245c2ecd1a933beb57a3781e92b5df631bbf6`. Re-record/check them at Gate 4. **READ** — `docs/spec.md:178,331-341`.
- Freeze primary family as P1–P4; P3 is best RL vs mass-order GA at budget 20 on T1. **READ** — `docs/spec.md:164-170,405`.
- **Assumption:** use annotated tag `p12b-freeze` at the freeze commit, after all choices and synthetic-only analysis checks are recorded. **READ** — `docs/spec.md:178`; `docs/patch_plan.md:37`.

## Order and open assumptions

- Complete the P14–P16 Stage 2 audit before P12b; freeze/tag P12b before P13 Stage 1 runs. **READ** — `docs/spec.md:391`; `docs/patch_plan.md:39`.
- **Assumption:** P12b will not change split contents or hashes; if the audit requires a protocol change, record an approved spec amendment before freeze. **READ** — `docs/spec.md:178,391`; `docs/a7_proposal.md:43`.
- **Assumption:** exact synthetic fixtures, script filenames, and the tag annotation text are implementation choices; record them in the freeze amendment and tag, keeping all real test results sealed until after freeze. **READ** — `docs/spec.md:170,178,180`; `docs/patch_plan.md:37`.
