# Verification record (checker)

Status of clause details used by `src/ub_rl/checker.py`. "Confirmed" means read in a public SCI source named below. The Gate 2 sections below are results; Gate 2 was accepted on 23 October 2026 (`docs/gate2_signoff.md`).

## Confirmed in public sources

| Item | Value used | Source |
|---|---|---|
| eta (EN 1993-1-1 6.2.6(3), EN 1993-1-5 5.1) | 1.0 | SCI AD 368: NA.2.4 of the UK NA to BS EN 1993-1-5 |
| hw | h - 2 tf | SCI AD 368, AD 537 |
| Shear buckling applies if | hw/tw > 72 eps / eta | SCI AD 368 |
| S355 UB needing the check | 406x140x39 and 762x267x134 only | SCI AD 368; the checker flags the same two |
| Shear buckling model | transverse stiffeners at supports only (lambda_w = hw / (86.4 tw eps)), non-rigid end post, flange contribution ignored | SCI AD 368; Blue Book explanatory notes |
| Blue Book Vc,Rd | 566 kN (406x140x39), 1970 kN (762x267x134) | SCI AD 368 |
| Web bearing, stiff bearing limit | ss <= hw | SCI AD 537 (EN 1993-1-5 6.3(1)) |
| Web bearing, l_y for type (c) | smallest of eqs 6.10, 6.11, 6.12 (6.5(3) cites 6.11-6.13 in error) | Blue Book explanatory notes |
| Web bearing, m2 | both assumptions evaluated; a branch is valid only if consistent with lambda_F; higher valid resistance taken | SCI AD 378 |
| fy by thickness | 355, 345, 335, 325 N/mm2 | spec section 5; Blue Book S355 table |

## Discrepancy

- SCI AD 368 gives Vb,Rd = 1768 kN for 762x267x134. That equals eta fy hw tw / sqrt(3) with no chi_w reduction. The method stated in the same note gives 1722 kN (chi_w = 0.974), which the checker uses. For 406x140x39 the note's 488 kN is reproduced within 0.4% (the note rounds eps to 0.81). Closed in the Gate 2 section below (no design impact).

## Not confirmed (formulas taken from secondary sources or by reasoning)

- Wording of EN 1993-1-1 and EN 1993-1-5 clauses was not read from the standards. Web bearing formulas (kF, l_e, m1, m2, Fcr, chi_F) follow published reproductions of EN 1993-1-5 section 6 (Kolekova and Balaz 2013; SCI notes). Gate 2 compares them with the Blue Book web resistance tables.
- Web bearing for c = 0 and ss = 100 mm with fork supports is the spec's assumption; the checker applies type (c) with the load at the end.
- EN 1993-1-5 7.1 (bending-shear with shear buckling) is implemented from the standard formula; it can affect only the two sections above.
- Class 3 sections with shear above 0.5 Vpl,Rd are treated as infeasible (no reduced-yield elastic rule implemented). No Class 3 or 4 section exists in C or C+, so this is inactive. One Class 2 section exists.
- Classification uses the tabulated cf/tf and cw/tw (rounded in the table). Differences between tabulated and recomputed ratios are at most 0.05 (cw/tw) and 0.005 (cf/tf); `consistency_max_abs_deviation` in the parser report.
- Deflection limits (span/360, span/200, span/250 on total load) are public practice, not read in the UK NA text.
- UK NA values of gamma_M0 and gamma_M1 (1.0) and the 6.10 load combination are used as stated in the spec.
- Self-weight enters the factored load with gamma_G = 1.35 and the deflection load (total case) unfactored.

## LTB (amendment A1, 2026-10-19)

Implemented in `Checker._ltb`. Tests: `tests/test_ltb.py` (defaults unchanged, Mcr against a scalar restatement, load-position effect, chi bounds, monotonicity in restraint spacing, curve selection, conservatism of the intermediate-restraint factors, reference optima per restraint ratio, configuration validation), `tests/test_ltb_reference.py` (a second, scalar implementation written separately; Mcr, chi, Mb,Rd and utilisation agree to 1e-9 over 8 restraint and load-position cases, 6 random contexts each, all sections up to class 3) and `tests/test_context.py` (the seven-parameter context).

| Item | Value | Source |
|---|---|---|
| C1, C2 (UDL, k = 1) | 1.127, 0.454 | NCCI SN003 (SteelConstruction.info SN003a/b) |
| C1, C2 (central point load, k = 1) | 1.348, 0.630 | NCCI SN003 (not used yet; UDL only) |
| lambda_LT,0, beta | 0.4, 0.75 | EN 1993-1-1 6.3.2.3 recommended values, cited in public worked examples |
| zg sign | positive when the load acts towards the shear centre; top-flange loading gives zg = +h/2 (reduces Mcr) | NCCI SN003 worked example (public) |
| G | E / (2 (1 + 0.3)) = 80,769 N/mm2 (changed from 81,000 after the Blue Book comparison) | EN 1993-1-1 3.2.6; Blue Book Mb,Rd table |

**Intermediate restraints.** With restraints between the supports, the critical segment does not carry the full-span UDL moment shape. Using the UDL factors (C1 = 1.127, kc = 0.94) there would be unconservative: the lightest feasible section changes in 386 of 600 contexts (64 %) when the uniform-moment factors (C1 = 1, kc = 1) are used instead (`scripts/ltb_factor_sensitivity.py`: 300 contexts at each of ratios 0.25 and 0.5, L 9 to 15 m, w 56 to 100 kN/m, numpy default_rng seed 0). The checker therefore uses the uniform-moment factors for 0 < ratio < 1 (conservative, applied at the maximum design moment) and the UDL factors only at ratio 1. Per-segment moment diagrams are a Gate 2 sensitivity.

**Known artefact near ratio 1.** The factors jump at ratio 1, so the model is not monotone between about 0.5 and 1. For 533x210x101 (L = 9 m, 56.7675 kN/m): Mcr = 857 kNm at ratio 0.5, 343 at 0.9, 301 at 0.99 and 334 at 1.0 (utilisation 1.05, 1.88, 2.09, 1.92). The lightest feasible section in the reference case is 762x267x134 (133.9 kg/m) at 0.9, 762x267x147 (146.9) at 0.95 and 0.99, and 686x254x140 (140.1) at 1.0. Less restraint is therefore judged slightly safer at ratio 1 than at 0.99. This is a modelling artefact, not a property of the structure. **Rule:** `Context` accepts restraint ratios 0 (continuous), values in (0, 0.5] and exactly 1; values in (0.5, 1) are rejected so a policy cannot learn the artefact. `CheckerConfig` still accepts any ratio in [0, 1] for sensitivity runs.

Not confirmed (to be closed at Gate 2 against the Blue Book Mb,Rd tables):

- kc = 0.94 for a UDL is taken from a reproduction of EN 1993-1-1 Table 6.6, not read from the standard (consistent with the Blue Book convention kc = 1 / sqrt(C1): 1 / sqrt(1.127) = 0.942). Curve selection is closed by the Blue Book comparison below.
- The f-factor form and the condition under which LTB may be ignored are written from the standard formulas as reproduced in guides.
- The Blue Book Mb,Rd values may use a different equivalent-uniform-moment treatment; the comparison must use the same moment diagram and load position as the tabulated cases.
- The UK NA position on 6.3.2.3 for UB sections is assumed to retain the recommended values; not read in the NA text.
- Only UDL is implemented; point-load patterns need C1 = 1.348 and kc = 0.86 and a different moment distribution for the interaction and bearing checks.
- The second implementation shares the catalogue and the classification with the checker and was written by the same author, so it checks the arithmetic, not the understanding of the standard.

Exploratory reference-case optima (L = 9 m, 56.7675 kN/m, self-weight included), current code, ratios 0, 0.25, 1/3, 0.5, 1.0:

| Load position | 0 | 0.25 | 1/3 | 0.5 | 1.0 |
|---|---|---|---|---|---|
| Shear centre | 457x191x74 | 533x210x82 | 533x210x92 | 610x229x101 | 686x254x140 |
| Top flange | 457x191x74 | 533x210x82 | 533x210x101 | 610x229x113 | 610x305x149 |

Reference-case optima unchanged by the Gate 2 corrections below. (An earlier version of this record listed 533x210x92 for the top-flange case at 1/3; that was computed before the conservative intermediate-restraint factors and is corrected here.)

**Not-found convention.** `lightest_feasible` and `lightest_feasible_context` both return -1 when no section is feasible (abstention).

## Gate 2 progress (2026-10-19)

Status at 2026-10-19 (superseded; Gate 2 accepted 23 October 2026, see Gate 2 status below): **partly done, not accepted.** The items below were done without the Blue Book tables; the Blue Book comparison is in the next section.

**Second implementation of the non-LTB checks** (`tests/reference_checks.py`, plain Python, written separately from the vectorised checker, following the clause text and the public SCI worked examples). `tests/test_reference_checks.py` compares every section for 10 contexts (spans 3 to 20 m, loads 40 to 800 kN/m) under three deflection rules: 10,920 comparisons of bending, shear, shear buckling, web bearing, deflection, bending-shear interaction, class and feasibility, agreement to 1e-9 (observed 3e-16). Where V > Vpl the shear check already fails and the interaction utilisation is defined differently (the checker caps rho at 1, the second implementation marks it infeasible); both are infeasible there. It shares the catalogue columns with the checker and was written by the same author team, so it checks arithmetic and reading of the clauses, not an engineer's independent judgement. The LTB second implementation is in `tests/test_ltb_reference.py`.

**Public SCI numbers** (`tests/test_external_benchmarks.py`; the Blue Book tables themselves are not public in a retrievable form):

| Item | SCI value | Checker | Note |
|---|---|---|---|
| Vc,Rd 406x140x39 (AD 368) | 566 kN | 566.0 kN | match |
| Vc,Rd 762x267x134 (AD 368) | 1970 kN | 1967.8 kN | -0.11 %, workbook rounds to 3 s.f. |
| Vb,Rd 406x140x39 (AD 368) | 488 kN | 489.8 kN | +0.37 %; the note rounds lambda_w to 0.85 and chi_w to 0.976 |
| Vb,Rd 762x267x134 (AD 368) | 1768 kN | 1722 kN | **-2.6 %, open.** 1768 equals the cap eta fy hw tw / sqrt(3), i.e. chi_w = 1, but the stated method gives lambda_w = 0.85 > 0.83 and chi_w = 0.97. Cause unresolved (typographical or an unstated input). The checker keeps the lower value; the comparison script reports this row as FAIL at 1 % |
| Sections needing shear buckling (S355) | only 406x140x39 and 762x267x134 | same two (both in C and in C+) | match |
| eta | 1.0 (UK NA to EN 1993-1-5 NA.2.4) | 1.0 | match |
| S355 design strength by thickness | 355, 345, 335, 325 N/mm2 for t <= 16, 40, 63, 80 mm | same bands | match |
| ell_y for type (c) | least of Eq 6.10, 6.11, 6.12 (SCI notes that EN 1993-1-5 6.5(3) refers to 6.11 to 6.13 in error) | three expressions used | match|
| LTB curve, lambda_LT,0, beta | h/b <= 2: curve b, alpha 0.34; lambda_LT,0 = 0.4, beta = 0.75 (UK NA NA.2.16, NA.2.17; public SCI worked example for a UKC) | same | match for the h/b <= 2 branch; the h/b > 2 branches are closed by the Blue Book comparison below (curve c for 2 < h/b <= 3.1, curve d above 3.1) |
| C1 in the Blue Book Mb,Rd tables | 1.13, 1.35, 1.77 (rounded) | NCCI SN003 values 1.127, 1.348 | the comparison script takes C1 from the table row |

**Web bearing, two valid solutions.** m2 depends on lambda_F, which depends on m2. SCI AD 378 states that where two valid solutions exist the higher resistance may be taken, and that the Blue Book tables do this; the checker follows it (`bearing_rule = "higher"`, default). The EN text order (m2 = 0 unless lambda_F > 0.5, the order of the public SCI worked example) gives a lower resistance for 6 of the 91 sections (by 17 % for 1016x305x438, 14 % for 1016x305x415, 11 % for 914x305x381, 9 % for 610x305x238, 6 % for 305x127x48, 5 % for 203x133x30) and is available as `bearing_rule = "sequential"`. In 3,000 random contexts (L 6 to 15 m, w 20 to 300 kN/m) neither the lightest feasible section nor the feasible set changes between the two rules. The sequential rule is the conservative sensitivity.

**Bending-shear interaction never decides a design.** Over all 91 sections and a grid of spans (0.3 to 15 m) and loads, the 6.2.8 interaction (or EN 1993-1-5 7.1 where shear buckling applies) governs only where the maximum utilisation is already 2.4 or more (median about 5). Near feasibility, bending, shear, web bearing or deflection governs. Shear buckling never governs by itself.

**Cases for hand checking.** `scripts/gate2_cases.py` writes `data/gate2/cases.csv` and `docs/gate2_cases.md` (14 cases: the reference beam; one case each where shear, 6.2.8 interaction, web bearing, deflection (two rules) and LTB (three restraint ratios) govern; the two shear-buckling sections; lightest, heaviest and a Class 2 section). They are generated, not hand calculations, and carry a "Hand-checked" line to sign.

**Blue Book comparison script (this part).** `scripts/compare_bluebook.py` reads `data/gate2/bluebook_values.csv`, filled by hand with Blue Book values. It is superseded for the full tables by `scripts/gate2_bluebook.py` (next section), which reads the downloaded workbooks directly; the CSV route remains for spot values.

## Gate 2: Blue Book comparison (S355, EC3 UK NA, downloaded 20/10/2026)

`scripts/gate2_bluebook.py` and `tests/test_bluebook.py` compare the checker with `UB-bending-S355-EC3UKNA-UK-10-20-2026.xlsx` (SHA-256 c2fedba5...ce3dd) and `UB-webbearingbuckling-S355-EC3UKNA-UK-10-20-2026.xlsx` (SHA-256 fb34eee1...b1b92) for all 107 sections. The tables are rounded to 3 significant figures and computed from unrounded section data; a value agrees if it lies within the checker interval obtained by moving each published input by its own rounding, plus half a unit in the last table digit. The workbooks are not committed (licence); the tests skip if they are absent.

| Quantity | Compared | Outside rounding | Largest relative difference |
|---|---|---|---|
| Class, Iy | 107 | 0 | - |
| Mc,y,Rd | 107 | 0 | 0.44 % (input rounding) |
| Vc,Rd | 107 | 0 | 0.40 % (input rounding) |
| FRd, c = 0, ss <= hw | 1323 | 0 | - |
| FRd, c = 0, ss > hw | 68 | 0 unconservative | checker lower (see below) |
| Mb,Rd (17 lengths x 7 values of C1) | 12,733 | 0 | - |

457x191x74 as tabulated: Mc,y,Rd 586 kNm, Vc,Rd 895 kN, FRd (ss = 100, c = 0) 408 kN, class 1; checker 585.8, 894.6, 407.7.

**Corrections made because of this comparison (found before any RL training).**

1. **Buckling curve.** The checker stopped at curve c (alpha 0.49) for h/b > 2. The table requires curve d (alpha 0.76) for h/b > 3.1, the UK NA selection: b for h/b <= 2, c for 2 < h/b <= 3.1, d above. It applies to 16 sections (10 in C: the 1016x305 series; 6 "+" rows: 533x165x66/75/85 and 610x178x82/92/100). With curve c the checker overstated Mb,Rd by up to 15.8 % (unconservative) for these.
2. **Shear modulus.** G = 81,000 changed to E / (2 (1 + nu)) = 80,769 N/mm2. With 81,000, 25 of 12,733 Mb,Rd values lay outside the interval (at most about 0.2 %).

**UK NA curve table, second source.** The curve selection (rolled I: b for h/b <= 2, c for 2 < h/b <= 3.1, d above 3.1; welded: c for h/b <= 2, d for 2 < h/b <= 3.1, nothing above 3.1; lambda_LT,0 = 0.4 and beta = 0.75 rolled, 0.2 and 1.0 welded) is also given by Bentley STAAD.Pro Help, clause 6.3.2.3(1), which reproduces UK NA NA.2.17. The NA text itself has not been read.

**Convention confirmed.** The Blue Book Mb,Rd uses kc = 1 / sqrt(C1) with the load at the shear centre; it is reproduced for C1 = 1.00 to 2.50 and Lcr = 1 to 14 m (17 lengths x 7 values of C1 x 107 sections). The checker's intermediate-restraint rule (C1 = 1, kc = 1) is exactly the C1 = 1.00 row of the table; the full-span UDL rule (C1 = 1.127, kc = 0.94) lies between the 1.00 and 1.13 rows. Top-flange loading (zg = +h/2) is not covered by the table and remains unvalidated.

**Stiff bearing longer than hw.** The checker limits ss to hw (EN 1993-1-5 6.3(1), SCI AD 537). The table does not: for sections with hw < ss (the smallest hw is 111.8 mm, 127x76x13) the table values at ss >= 150 mm are up to 29 % higher. The checker is lower than the table in all 68 such values (conservative). The limit never acts at the study value ss = 100 mm, so the frozen study is unaffected. Not changed; to be decided if ss > 100 mm is ever used.

**'+' markers.** In these two files 91 sections carry '+' and the 16 sections marked '+' in the section properties table are unmarked; the footnote text is identical. The markers of these two files are not used. The set C (91 rows) is defined by the section properties table (spec section 4). To be re-checked against a fresh download of the properties table.

**Bearing rule.** The default `bearing_rule = "higher"` is the rule the Blue Book table follows (0 of 1323 values outside rounding). With `sequential`, 186 of the same 1323 values fall outside rounding, in 90 sections (checker below the table), so `sequential` is a conservative sensitivity only, not the table convention.

**Items closed by decision or measurement (2026-10-20).**

- *762x267x134 Vb,Rd (1722 kN checker vs 1768 kN in SCI AD 368).* Closed, no design impact. Replacing Vb,Rd of both shear-buckling sections by its largest possible value (chi_w = 1) changes the feasibility of no section in 20,004 random contexts per setting (three deflection rules, sets C and C+, plus four extreme short-span cases); `tests/test_shear_buckling_impact.py` repeats this on a smaller sample. The checker keeps the lower, method-consistent value.
- *'+' markers.* The 91/16 split of the section properties table is used (spec section 4). The two resistance workbooks mark the opposite 91 sections, which contradicts their own footnote ("in addition to the range of BS EN 10365": 91 of 107 would be additions). The study already runs the 107-row sensitivity (C+), which covers either reading. The resistance-workbook markers are ignored.
- *Top-flange loading.* Not validated (the Blue Book table is for load at the shear centre). It stays a configuration option, is not exposed in `Context`, and is not used in any primary or pre-registered result.
- *Per-segment moment diagrams.* Not implemented. The uniform-moment factors used for intermediate restraint are conservative (they equal the C1 = 1.00 row of the Blue Book table); the loss in quality is a documented limitation.

**Review by someone who did not write the checker.** Done: the supervising engineer agreed the 12 assumptions and signed the form (`docs/gate2_signoff.md`).

## Gate 2: hand check by calculator (Muhammad Shifa, 23 October 2026)

**What was done.** For the 14 cases of `docs/gate2_cases.md`, Muhammad Shifa recomputed the results with a calculator and entered them in the hand-check workbook (`scripts/make_hand_check_workbook.py`). Inputs: the case sheet and the Blue Book properties table; Blue Book values for Mc,Rd, Vc,Rd, FRd and Mb,Rd; the formulas of `docs/hand_calc_G2-01.md`. The record is `data/gate2/handcheck_values.csv` (program value, entered value, difference).

**Result.** All 234 cells entered (the Section class cells of G2-04 and G2-08 were entered in a second upload). No entered value differs from the program by more than 0.5 % (largest 0.28 %, G2-12). 127 of the 201 non-integer entries equal the program value to nine digits, as expected when the same formulas and inputs are evaluated without intermediate rounding; the others differ by rounded Blue Book values and rounded intermediate steps (at most 0.28 %).

**What it shows and what it does not.** It shows that the program's arithmetic reproduces the listed formulas on the 14 cases. It does not show that the formulas match EN 1993-1-1, EN 1993-1-5 and the UK National Annex, because the formulas listed are the program's own. The supervising engineer reviewed and agreed the 12 assumptions in `docs/review_request.md` (`docs/gate2_signoff.md`).

**Gate 2 status.** Accepted, 23 October 2026. All 12 assumptions agreed and the review form signed by the supervising engineer (Dr. Mudasir Hussain; `docs/gate2_signoff.md`); the 14 cases were recomputed by calculator by Muhammad Shifa (the supervising engineer did not recompute individual cases); resistances agree with the Blue Book for all 107 sections.

## P6: context box audit (2026-10-24, revised 2026-10-25)

Run by Claude (AI assistant) for the project lead in the project session of 2026-10-24 to 2026-10-25; the first version of the audit files was superseded on 2026-10-25 after review (A2, revision note). Reproduction on the project lead's machine: `python scripts/context_audit.py --check` reported `checked 21 files; differing or missing: none` (reported by the project lead on 2026-10-25, for the first version). Repeated for the revised files (commit `09a7ec0`, after P6b to P6d): on the project lead's machine (Python 3.12.12, pytest 9.1.1, workbooks present) `python -m pytest tests/` reported `155 passed` and `python scripts/context_audit.py --check` reported `checked 22 files; differing or missing: none` (reported by the project lead on 2026-10-25). The catalogue workbook SHA-256, the checker SHA-256 and the splits SHA-256 are in `docs/context_audit.md`.

Enumeration over C for every context-file row (one checker call each on C and on C+) by `scripts/context_audit.py`; tables `paper/tables/audit_*.csv`, summary `docs/context_audit.md`. The reference optima at restraint ratios 0, 0.25, 0.5 and 1 reproduce the optima recorded above (457x191x74, 533x210x82, 610x229x101, 686x254x140). The checker, config and context code are unchanged. Tests: `tests/test_splits.py`.

## P7: Stage 1 baselines I and run infrastructure (2026-11-11)

**What was built** (new: `src/ub_rl/baselines.py`, `src/ub_rl/runstore.py`, `scripts/run_baselines1.py`, `tests/test_baselines1.py`): the four Stage 1 baselines of spec section 9 — enumeration (exact reference), ordered scan (mass order, stop at the first feasible section, exact), heuristic iteration (trial section = first section in mass order with Wpl >= M_Ed/355 from the superimposed factored UDL w, up in mass order until feasible, then down while the next-lighter section stays feasible) and random search (budgets 10, 20, 50, |C|, seeds 0-9). Call accounting: the cost unit is checker calls = section evaluations (a vectorised evaluation of k sections counts as k calls); a `CountingChecker` wrapper measures the calls each method actually makes and the reported number is read from the counter, never computed by the method itself. Every output design is rechecked with a fresh checker call (1 verification call for a feasible output, 0 for abstention; stored in `verification_calls`, not added to the search `calls`, spec section 9 end-to-end). Result store (spec section 12): one CSV per method and split file under `results/baselines1/` with `*_meta.json` carrying `status: "complete"`, the commit, the SHA-256 of the environment file (`src/ub_rl/checker.py`, unchanged), catalogue and split SHA-256, the checker config, the hardware and the single-thread limits; a result file without its meta file is rejected on load. Wall time is measured per design with the BLAS threads pinned to 1 before numpy is imported (spec section 10). The run script asserts on the run itself: enumeration == ordered scan on every context, random search at budget |C| == enumeration, every output rechecked, every split file matches `data/splits/SHA256SUMS` before anything is evaluated, and every written file reloads through the store.

**Decisions recorded (method conventions, no spec change):** random search draws distinct sections uniformly without replacement and outputs the lightest feasible sampled section; at budget |C| it evaluates every section, equals enumeration for every seed, and is evaluated once per context then stored under all 10 seeds (recorded in the meta, not assumed silently). The heuristic is local: feasibility is not monotone in mass order, so its output is not guaranteed to be the enumeration optimum; the gap is a result.

**What was run and what it showed.** Built and tested on the project lead's machine (conda `rl_env`, Python 3.12.12, pytest 9.1.1, numpy 2.3.5) on 2026-11-11: `python -m pytest -q` reported `167 passed` (155 existing + 12 new P7 tests). Smoke run `python scripts/run_baselines1.py --limit 200` (1,604 contexts across the 9 split files): the script's assertion held — enumeration equals ordered scan on every context; enum calls 91.0 everywhere; ordered-scan mean calls 45.75 (reference) to 82.405 (T3, which carries most abstentions); heuristic mean calls 2.62 on the v1.2 sub-study (the preliminary diagnostics of the unverified checker measured 2.6) and 9.1-22.1 on the seven-parameter sets; random mean calls 42.75 = the mean of the four budgets. The environment-file SHA-256 in the metas is `3b6ab914…`, matching the P6 record — the checker, physics, objective and fixed assumptions are unchanged. The full run over the 34,841 contexts is pending on the project lead's machine (single-threaded; measured extrapolation about 50 minutes on this hardware, an Intel i3-3110M recorded in the metas). **Status: delivered; full-run acceptance pending.**

## P7b: fixes to P7 after review (2026-11-11)

Written by Claude (AI assistant) for the project lead; patch on top of commit `c99614a`. Three changes, no change to the checker, physics, objective or any assumption:

1. **Random search seeding.** The P7 script built the generator from the seed alone, so every context received the same sections for a given seed and budget (seed 0, budget 10: 5 distinct outputs over 100 val contexts). The order is now fixed per (seed, context id) by a Fisher-Yates shuffle driven by `random.Random` (independent of the NumPy version, as in the splits); budgets are nested prefixes of it (31 distinct outputs in the same check). The numbers for random search in the P7 paragraph above are superseded; the call counts (budget) do not change.
2. **Heuristic call count.** The heuristic evaluated the section below the first feasible one a second time after moving up. A section already evaluated in a context is now remembered, so calls are distinct sections (spec section 10): mean calls on the first 100 val contexts 16.61, earlier 17.25. Outputs are unchanged. The heuristic figures in the P7 paragraph above (for example 2.62 on the v1.2 sub-study) are superseded.
3. **Result store.** `write_results` now records `result_sha256` and `n_rows` in the meta file and removes an old meta file before rewriting; `load_results` rejects a CSV that differs from the recorded hash or row count.

Tests: 7 new (random order stable, per seed and context, nested; heuristic never evaluates a section twice; edited CSV, wrong row count and interrupted rewrite rejected). Run by Claude on a clone of `review` at `c99614a`: `python -m pytest -q` reported `174 passed` (167 + 7); `python scripts/run_baselines1.py --limit 100` reported `enumeration == ordered scan on every context: True` and wrote 36 result files. The full run is for the project lead.

## P7: full run on every split file (2026-11-11)

Run by the project lead (machine in `results/baselines1/*_meta.json`) on `review` with P7b applied: `python scripts/run_baselines1.py`, then `python scripts/baselines1_summary.py results/baselines1`. Numbers below are copied from the printed output; Claude did not run this.

**Acceptance criteria met.** 34,841 contexts; `enumeration == ordered scan on every context: True`; calls logged per design; 36 result files each with its meta file. Feasible and abstain counts per set equal `paper/tables/audit_sets.csv` (train 16,723 / 3,277; val 796 / 204; T1 1,635 / 365; T2 388 / 112; T3 609 / 891; T4 1,404 / 96; T5 3,102 / 735; v1.2 sub-study 4,500 / 0; reference 4 / 0). The printed summary output and the SHA-256 of all 36 result CSVs (same hashes as in the `*_meta.json` files) are committed in `paper/tables/baselines1_run_output.txt`, so every number below can be checked against the committed snapshot; `results/` itself stays git-ignored and is archived at submission (e.g. Zenodo).

**Mean checker calls per context** (enumeration 91 everywhere; random search 42.75 = mean of budgets 10, 20, 50, 91):

| Set | Ordered scan | Heuristic |
|---|---|---|
| train | 63.24 | 13.55 |
| val | 64.24 | 14.19 |
| T1 | 63.56 | 13.74 |
| T2 | 66.77 | 15.30 |
| T3 | 81.92 | 19.23 |
| T4 | 59.57 | 9.88 |
| T5 | 63.91 | 13.86 |
| v1.2 sub-study | 57.34 | 2.42 |
| reference | 45.75 | 8.75 |

**Heuristic iteration reaches the optimum in every context where a feasible section exists, in every set** (29,161 of 29,161: gap 0, no false abstention). It abstains exactly where enumeration abstains.

**Random search** (10 seeds per context), over the eight sets other than reference: mean gap 25.1 to 36.2 % at budget 10, 14.3 to 16.1 % at 20, 3.9 to 5.1 % at 50, and 0 at 91 (the whole catalogue). Wrong abstentions on train (167,230 seed runs in contexts with a feasible section): 58,150 (34.8 %) at budget 10, 35,460 (21.2 %) at 20, 12,912 (7.7 %) at 50, 0 at 91.

**Meaning for the project.** On catalogue C with these contexts the conventional heuristic leaves no quality gap, so a learned selector cannot improve on it in mass or feasibility; any benefit has to be in checker calls or in behaviour outside what the heuristic covers. This is a Stage 1 result. It changes no physics, objective or assumption; how it is reported and what it implies for the comparison is the saturation analysis of P9.

**Why the zero gap (sampled check, 2026-11-11).** Review asked why the heuristic shows gap 0 although feasibility is not monotone in mass order. Claude ran the cheap monotonicity counter on a sample — val (1,000), reference (4) and the first 2,000 train contexts, 2,486 feasible in total: the reviewer's pattern (a lighter section feasible while a heavier one below it is not) occurs in 676 of 796 feasible val contexts (2,010 adjacent edges) and in 1,428 of 1,686 train contexts (4,294 edges; reference has none), so feasibility is genuinely non-monotone. But no sampled context has an infeasible section between the optimum and the heuristic's trial section: the feasible sections form a contiguous block from the optimum up to the trial, and every dip sits among sections heavier than the trial, which the downward walk never meets. The heuristic therefore reaches the optimum structurally on the sample, not by luck. The counter is part of P9 (see the P9 line in `docs/patch_plan.md`); the full count over all 34,841 contexts (P9 full run, 2026-11-11) finds c1 in 23,573 contexts and c2 = c2_block = 0 in every context, so no context breaks the block (`docs/gate3_record.md`).

## P9: landscape and saturation diagnostics (2026-11-11; Amendment A3 sets the F1 horizon to 13 steps)

**What was built.** `src/ub_rl/reward_checks.py` (the five reward families and the float64 log-space ordering assertion with analytic margin bounds), `src/ub_rl/landscape.py` (monotonicity counter c1/c2/c2_block, all-pairs F1 action-graph distances, per-context diagnostics with `Checker.check` at the optimum), and `scripts/landscape_diagnostics.py` (one script: enumeration pass, landscape/horizon/governing/alternatives tables, the saturation table with V as the headline line and the ordered-scan row, the reward assertion on V, the Gate 3 record; `--check` rebuilds in a temporary folder and compares the committed files; `--limit N` is a sample that writes nothing committed and skips the P7 snapshot assertion by design; full runs must reproduce the P7 snapshot per file and are the only runs that write the committed outputs). Tests: 9 + 10 + 6 new; `python -m pytest -q` reported 200 passed on `review`.

**Sample run (`--limit 12` = 100 contexts), run by Claude on the project lead's machine.** 3.96 s wall (3.65 s user, 69.5 MB peak RSS), single-threaded; outputs under `results/p9_sample/` (nothing committed). Findings on the sample:
- Monotonicity genuinely fails: c1 in 58 of 100 contexts (c1_edges 191); c2 = 0 and c2_block = 0 in every sampled context — the feasible block from the optimum to the walk start is contiguous everywhere, which is the structural explanation of the P7 zero gap.
- F1 horizon: the optimum is at most 9 F1 steps from the trial section on the sample (t2), at most 8 elsewhere — no context needs more than 12, so no flag. The full-run verdict is recorded in `docs/gate3_record.md`; the horizon is never changed by the script.
- Saturation on the sampled V (12 contexts): heuristic exact 12/12 of the feasible, 0 false abstentions, 0 infeasible outputs (rechecked), mean heuristic calls 13.67, mean ordered-scan calls 62.58 → the rule (exact match >= 0.99, feasibility 1.0) is MET on the sample.
- Reward ordering: the assertion passed on the sampled V for every family (R1, R2, R3 at beta 25/50/100, R-C, R-D), margins at or above the analytic bounds.

**Full run (2026-11-11, project lead's machine).** Command: `python scripts/landscape_diagnostics.py` — about 2 minutes (1.81 ms per context measured on a 100-context val sample, 34,841 contexts ≈ 63 s, plus the heuristic and the reward assertion); `--check` doubles the work. The run writes `paper/tables/p9_*.csv`, `docs/gate3_record.md` and `results/p9/`, and asserts the P7 snapshot (per-file feasible counts and mean heuristic calls) exactly — the assertion passed. The first full run flagged 17 contexts of T3 (E1: 4, E2: 1, E3: 12) whose optimum needs 13 F1 steps, one more than the registered 12; the script only reports and never changes the horizon. Per spec section 9 the horizon is amended before training: **Amendment A3 (2026-11-11)** sets it to 13 steps — the largest F1 distance over all sets, needed only by those 17 T3 contexts — approved by the project lead and confirmed by the supervisor on 2026-11-11 (recorded in `docs/spec.md`; the original 12-step text stays visible). The rerun with the amended horizon, checked by `--check` (identical, 7 files), found no context beyond 13 steps and therefore no flag. Outcomes recorded in `docs/gate3_record.md` and the committed tables:
- F1 horizon 13 confirmed on every split; the 17 T3 contexts need exactly 13 steps.
- Monotonicity: c1 in 23,573 contexts (feasibility is genuinely non-monotone in mass order); c2 = 0 and c2_block = 0 in all 34,841 contexts — the feasible block from the optimum to the walk start is contiguous everywhere, which is the structural explanation of the P7 zero gap, now on the full count.
- Saturation: the rule (heuristic exact match >= 0.99 and feasibility 1.0 on V) is MET on every context set. V headline: heuristic exact on all 796 feasible val contexts (exact share 1.0000), 0 false abstentions, 0 infeasible outputs (rechecked), mean heuristic calls 14.193.
- Reward ordering on V (1,000 contexts): the assertion passed for every family (R1, R2, R3 at beta 25/50/100, R-C, R-D), 796 non-vacuous. The minimum margins sit exactly at the analytic bounds — 0.987 for R1/R2/R-C, 10 for R3, 0.5 for R-D — as predicted, attained by the val contexts whose heaviest feasible section is the heaviest section of C.

Gate 3 acceptance is complete: the diagnostics are reproducible by the one script (`--check`), the P7 snapshot is reproduced exactly, and the Gate 3 record states the saturation outcome per context set and the amended horizon.

## P8: Stage 1 baselines II verification (2026-11-16)

- P8 full run started just before commit 0314bde; the file hashes recorded by the run match the content committed in 0314bde, so the run is reproducible from that commit.
- GA code identity confirmed by a --limit 100 rerun (results/check100): all 7,200 ga_tune.csv rows identical to the full run's rows for the same V contexts, configuration, budget and seed (status, section index, gap, calls, verification fields; wall times excluded).
- MLP label accounting confirmed on the sample ((78 + 22) x 91 = 9,100 calls).

## P10: Stage 1 RL environments and rewards (2026-11-16)

- P10 built F0, F1 (horizon 13), F2 with R1 and R3 (spec section 9 as amended by A3 and A5) — `src/ub_rl/envs.py` and `tests/test_envs.py` only; the `slow` marker is registered in `tests/conftest.py`. The envs import N_MAX, STEP_COST_R1 and R3_BETAS from `reward_checks.py` (no copies) and reuse `baselines.trial_index` and the CountingChecker; calls are measured by the CountingChecker, `env.calls` is per episode and the cumulative budget is `kc.sections`. No algorithms, no training, no result files.
- Full-V ordering check passed over all 1,000 V contexts (4.6 s), run by the project lead.
- Full suite run by the project lead: 226 passed, 1 skipped (the full-V test, by design), 1 xfailed (the strict A6 test 14, a recorded negative result, not a regression).
- Carried to P11: F1 steps-taken feature, per-move versus terminal step cost, utilisation scaling or clipping, which F1 cost (steps or calls) goes into N*, F2 greedy tie-break to the lowest mass index.
- **Approved by Dr Mudasir Hussain (supervisor), recorded by the project lead on his instruction, 2026-11-16.**

## P11: Stage 1 agents and the training harness (2026-11-17)

- P11 built the three Stage 1 agents of A5 and the configuration-driven training harness on the P10 environments (`src/ub_rl/agents.py`, `src/ub_rl/replay.py`, `src/ub_rl/harness.py`, `configs/f0_r1.json`, `f1_r1.json`, `f2_r3.json` — provisional defaults, marked so in each file): REINFORCE with a learned baseline (F0-R1); Dueling Double DQN with prioritized replay and n-step returns (F1-R1); conditional GFlowNet with trajectory balance (F2-R3). The harness: configuration-driven runs, seeds, a hard call-budget stop read from the CountingChecker's cumulative `kc.sections` (never the agent's arithmetic), checkpoints at the first update boundary where training calls >= each threshold (possibly mid-episode; the actual call count is recorded in the artifact, log and meta), evaluation calls kept separate through the `budget_includes_eval` and `eval_contexts` config fields, JSONL logs, checkpoint artifacts and P7-convention metas carrying the SHA-256 of the checker, envs, harness, agents, replay, train.csv and the raw workbook. Agents never read `env.calls` or `info["calls"]`; non-finite observations, logits, Q values, TD errors, losses or logZ raise RuntimeError.
- P10 changes carried (plan decisions 3a/3c/3e): the F1 observation is 22-dim (9 context + 5 section + 7 utilisation clipped `clip(u, 0, 2)/2` + steps/13); the F2 greedy tie-break goes to the lowest mass index on exact ties; `info["feasible"]` on F0/F2.
- Per-design deployed cost = rollout calls (F0/F2: 1; F1: 1 + new visits) plus repair calls; F1's N* also reports steps (decision 3d). `verification_calls` is always 0: the rollout is the verification.
- Tests are toy smoke tests only (a few hundred calls, tiny networks, contexts drawn from train.csv, no V, no test file, no results, no tuning) and satisfy the patch-plan acceptance line (same seed reproduces the run). Learning-direction tests use no checker calls: F0 expected return −2.41 → −0.41 with the baseline MSE falling; F1 Q(s, a) moves toward its n-step target; F2 KL 0.285 → ~1e-6 and logZ error 3.17 → 0.0009 over 3,000 gradient steps.
- Full suite run by the project lead: 284 passed, 1 skipped, 1 xfailed in 1795.58s (0:29:55).
- Open item: A5's evaluation budget is unsatisfiable for F1 as written (an F1 greedy-rollout evaluation of 1,000 V contexts costs about 10,000+ calls against a 3,000-call tuning budget); to be settled by Amendment A7 before P12a. No F1 tuning or pilot config can be frozen until then.
- Carried to P12a: epsilon-greedy accept probability, PER importance-weight normalisation (batch max), no entropy bonus in F0, reproducibility check in a fresh process.
- **Approved by Dr Mudasir Hussain (supervisor), recorded by the project lead on his instruction, 2026-11-17.**

## P12a: pilots, tuning and D6 trigger (2026-11-20)

**Protocol.** P12a ran locally on branch `review` under approved Amendment A7 with the full validation split SHA-256 `9fbb20b2b11b3907daae9ad5303be85bc88360f109370b99cda95197665c5be6`. The preflight reproduced 796 feasible contexts among 1,000 V rows and 71 among the first 100. All pilot and tuning evaluations were repair-free. Feasibility percentages below use contexts with at least one feasible catalogue section; gaps are percent mass gaps. F1 steps are mean rollout moves on its 100-row subset. **VERIFIED** — `results/p12a/manifest.json`, run artifacts and saved masks.

**Pilots.** Nine runs completed: each used 10,000 training checker calls; F0/F2 evaluated 1,000 V rows, F1 evaluated the first 100. Evaluation calls are shown separately. Offline repaired metrics use the registered mass-order repair applied to full V masks; no repair ran during evaluation.

| Entry | Seed | Raw feasibility | Raw mean gap | Offline repaired gap | Repaired feasibility | Repair abstentions | Training calls | Evaluation calls | F1 mean steps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| f0_r1 | 0 | 94.10% | 65.6571% | 62.8877% | 99.25% | 6 | 10000 | 1000 | — |
| f0_r1 | 1 | 94.10% | 65.6571% | 62.8877% | 99.25% | 6 | 10000 | 1000 | — |
| f0_r1 | 2 | 94.10% | 65.6571% | 62.8877% | 99.25% | 6 | 10000 | 1000 | — |
| f1_r1 | 0 | 66.20% | 17.5249% | 12.3397% | 100.00% | 0 | 10000 | 601 | 6.11 |
| f1_r1 | 1 | 76.06% | 25.8567% | 19.8310% | 100.00% | 0 | 10000 | 575 | 6.28 |
| f1_r1 | 2 | 76.06% | 22.6046% | 18.1627% | 100.00% | 0 | 10000 | 593 | 5.32 |
| f2_r3 | 0 | 94.10% | 65.6571% | 62.8877% | 99.25% | 6 | 10000 | 1000 | — |
| f2_r3 | 1 | 60.43% | 37.2944% | 22.5360% | 100.00% | 0 | 10000 | 1000 | — |
| f2_r3 | 2 | 94.10% | 65.6571% | 62.8877% | 99.25% | 6 | 10000 | 1000 | — |

**Tuning.** All 36 configurations completed with seed 0, a 3,000-call total budget including evaluation, and no repair. The full configuration fields are preserved in `results/p12a/manifest.json` and `paper/tables/p12a_tune_summary.csv`.

| Entry | Slot | Raw feasibility | Raw mean gap | Repaired feasibility | Offline repaired gap | Training calls | Evaluation calls | Total calls | Unused calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| f0_r1 | 1 | 34.05% | 14.8054% | 100.00% | 7.3532% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 2 | 94.10% | 65.6571% | 99.25% | 62.8877% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 3 | 37.81% | 21.4554% | 100.00% | 10.9485% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 4 | 55.28% | 61.2038% | 94.97% | 44.5076% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 5 | 52.89% | 56.8260% | 99.50% | 58.8636% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 6 | 94.10% | 65.6571% | 99.25% | 62.8877% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 7 | 56.41% | 48.9892% | 100.00% | 44.8749% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 8 | 33.04% | 15.0797% | 100.00% | 7.2951% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 9 | 11.93% | 17.0959% | 100.00% | 2.4023% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 10 | 94.10% | 65.6571% | 99.25% | 62.8877% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 11 | 94.10% | 65.6571% | 99.25% | 62.8877% | 2000 | 1000 | 3000 | 0 |
| f0_r1 | 12 | 53.39% | 66.3096% | 74.62% | 59.4448% | 2000 | 1000 | 3000 | 0 |
| f1_r1 | 1 | 61.97% | 32.6167% | 100.00% | 21.0467% | 1600 | 403 | 2003 | 997 |
| f1_r1 | 2 | 50.70% | 40.2620% | 92.96% | 28.7145% | 1600 | 970 | 2570 | 430 |
| f1_r1 | 3 | 42.25% | 41.3655% | 91.55% | 30.4618% | 1600 | 855 | 2455 | 545 |
| f1_r1 | 4 | 49.30% | 28.1371% | 94.37% | 18.9536% | 1600 | 1072 | 2672 | 328 |
| f1_r1 | 5 | 40.85% | 50.1818% | 98.59% | 37.1569% | 1600 | 869 | 2469 | 531 |
| f1_r1 | 6 | 61.97% | 36.2626% | 98.59% | 28.3895% | 1600 | 749 | 2349 | 651 |
| f1_r1 | 7 | 38.03% | 43.5963% | 92.96% | 33.9719% | 1600 | 629 | 2229 | 771 |
| f1_r1 | 8 | 53.52% | 38.9236% | 94.37% | 35.4578% | 1600 | 1104 | 2704 | 296 |
| f1_r1 | 9 | 63.38% | 40.9416% | 97.18% | 30.1344% | 1600 | 1106 | 2706 | 294 |
| f1_r1 | 10 | 45.07% | 32.0613% | 77.46% | 35.0516% | 1600 | 967 | 2567 | 433 |
| f1_r1 | 11 | 43.66% | 23.3576% | 100.00% | 11.8981% | 1600 | 655 | 2255 | 745 |
| f1_r1 | 12 | 57.75% | 30.2918% | 95.77% | 20.0136% | 1600 | 624 | 2224 | 776 |
| f2_r3 | 1 | 0.00% | — | 100.00% | 0.0000% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 2 | 32.54% | 13.2010% | 100.00% | 4.2953% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 3 | 0.00% | — | 100.00% | 0.0000% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 4 | 58.54% | 47.7122% | 100.00% | 43.6159% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 5 | 94.10% | 65.6571% | 99.25% | 62.8877% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 6 | 17.96% | 11.8090% | 100.00% | 2.1215% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 7 | 58.54% | 47.7122% | 100.00% | 43.6159% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 8 | 60.43% | 37.2944% | 100.00% | 22.5360% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 9 | 17.96% | 11.8090% | 100.00% | 2.1215% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 10 | 58.54% | 47.7122% | 100.00% | 43.6159% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 11 | 0.00% | — | 100.00% | 0.0000% | 2000 | 1000 | 3000 | 0 |
| f2_r3 | 12 | 58.54% | 47.7122% | 100.00% | 43.6159% | 2000 | 1000 | 3000 | 0 |

Tuning used 101,203 checker calls and recorded 6,797 unused calls across all configurations. F1 unused calls reflect termination after the final checkpoint evaluation.

**D5 selections.** No non-default configuration met the A7 rule, so each provisional default (slot 1) remained selected.

| Entry | Selected slot | Selected configuration | D5 result | Raw feasibility | Offline repaired gap | Total calls | Unused calls |
|---|---:|---|---|---:|---:|---:|---:|
| f0_r1 | 1 | hidden [64,64], lr 0.001, batch 64, normalize advantage false | no candidate met A7 D5; incumbent retained | 34.05% | 7.3532% | 3000 | 0 |
| f1_r1 | 1 | hidden [64,64], lr 0.001, epsilon 0.1, n 5, target sync 100, replay 10000, alpha 0.6, batch 32, beta anneal 3000 | no candidate met A7 D5; incumbent retained | 61.97% | 21.0467% | 2003 | 997 |
| f2_r3 | 1 | hidden [64,64], lr 0.001, logZ lr 0.001, batch 64, beta 50 | no candidate met A7 D5; incumbent retained | 0.00% | 0.0000% | 3000 | 0 |

F2-R3 slot 1 outputs section index 0 for all 1,000 V contexts. Its raw feasibility is 0% on the 796 contexts with feasible sections. Offline repair reaches the optimum on all 796, giving 100% repaired feasibility, zero abstentions on that denominator and a 0% repaired gap. The 204 contexts with no feasible section are excluded from the metric denominators. **VERIFIED** — slot 1 evaluation CSV and full V masks.

**D6 trigger.** None of F0-R1, F1-R1 or F2-R3 reached raw feasibility ≥ 0.99 in all three pilot seeds. The A7 decision is `run_rc=true`, selecting F1-R1 slot 1 (`tune/f1_r1/cfg01`) if R-C is authorized. This records the trigger decision only; no R-C run was performed. **VERIFIED** — all nine pilot CSVs, `results/p12a/trigger.json` and `paper/tables/p12a_trigger.csv`.

**Artifact checks.** The generated tables match the saved manifest: 9 pilot rows, 36 tuning rows and one trigger row; each metric, configuration and D5 selected flag was compared. The full pilot logs, checkpoints, metadata, evaluation CSVs, tuning artifacts and validation mask cache are under `results/p12a/`. **VERIFIED** — CSV/manifest comparison and artifact seals.

**Pilot provenance note.** Pilot `run_meta.json` files record HEAD `8eeeb40f09d40ee629d05354c5b4613914e3211f`. The runs used the working-tree correction `c["m"]` in `src/ub_rl/experiment_runner.py`, which was then committed as `c4f1c58d8a503f1ca027dd9ecd3a90b2a9e2aa6f`. The harness metadata records Git HEAD but not the dirty working-tree state or the P12a driver source hash; the pilot commit field therefore does not identify the full source state used. Pilot artifact seals, configuration and data hashes, harness/agent/replay hashes, logs and recomputed metrics were checked; this provenance limitation is retained here. **VERIFIED** — pilot metadata/artifacts and Git history.

## P12a post-hoc diagnostic (2026-11-22)

**Post-hoc; not part of A7.** **VERIFIED** — D5 selects on offline repaired gap and does not include repair-call cost. Thus constant section-0 outputs in F2 tuning slots score 0% repaired gap while costing 57.378 feasible-context mean calls/design and 64.237 whole-set calls/design (including evaluation); F2-R3 slots 3 and 11 have the same result. The diagnostic uses V-1000 and saved masks. — `paper/tables/p12a_cost_diagnostic.csv`, `paper/tables/p12a_best_constant.csv`.

**VERIFIED** — The best constant over training contexts is section 69 for R1 and R3 at beta 25/50/100; observed F0 pilot seed 0 outputs section 69, while F2 seed 1 outputs section 58 (F2 seed 0 outputs 69). Trained checkpoint mean logit SD across V / mean entropy were F0 seed 0: 0.140600 / 0.035618 nats; F2 seed 0: 2.732397 / 0.004167; F2 seed 1: 2.280934 / 0.051570. Fresh same-seed means were respectively 0.026155 / 4.504004, 0.035179 / 4.283439, and 0.039529 / 4.271815; F2 seed 1 fresh entropy is 4.271814823393 (trained entropy 0.051570441574). No V observation feature had zero variance; all three trained checkpoint modes match the saved evaluation modes, while fresh-network modes differ. — `paper/tables/p12a_best_constant.csv`, `paper/tables/p12a_policy_sensitivity.csv`.

**VERIFIED** — Corrected deployed-cost tables use sets V-1000 (F0/F2) and V-first-100 (F1). The matching heuristic means are 14.193 and 16.610 calls/design, respectively. F1’s offline repair term is an upper bound because the harness skips visited sections and the evaluation CSV omits visited indices. Within the 21 F0/F2 runs in the five identical-metric groups, each outputs a single section for all 1,000 V contexts (distinct outputs = 1; constants 69, 58, 0, 63, 48); distinct_outputs was not tabulated for the other F0/F2 runs. Zero of 45 runs are below the matching heuristic cost with repaired gap ≤0.5 percentage points. — `paper/tables/p12a_cost_diagnostic.csv`.

**READ** — Commit `2c5969c` changes P11 code after P11 acceptance through the `replay.py` `NStepBuilder` fix; it affects only `n=1` configurations, not the defaults. The full test suite must be rerun locally. — `src/ub_rl/replay.py`, Git history for `2c5969c`.

**VERIFIED** — The existing pilot provenance note remains immediately above this post-hoc section: pilot metadata recorded HEAD `8eeeb40` although runs used the uncommitted `c["m"]` correction later committed as `c4f1c58`. — `docs/verification_record.md`, `results/p12a/pilot/` metadata.

Full-suite result (local, rl_env, 2026-11-22, after P12a): 315 passed, 1 skipped, 1 xfailed in 1992.71 s (0:33:12). READ — project lead's terminal output. The P11 result was 284 passed, 1 skipped, 1 xfailed.

Post-P12a code additions, 2026-11-24: P14a-1 welded modules (commits af63c43, 2acd511) and the isolated F1 R-C variant (this commit) add new files only; no existing source or test file was edited (READ — git show --stat of each commit). Subset run (READ — project lead’s local terminal output): pytest -q tests/test_agents.py tests/test_envs.py tests/test_replay.py tests/test_harness.py tests/test_checker.py tests/test_context.py tests/test_agent_rc.py tests/test_welded_sections.py tests/test_welded_checker.py → 178 passed, 1 skipped in 90.58 s. This subset includes the new welded and R-C tests and the existing agent, environment, replay, harness, checker and context tests; it excludes tests/test_baselines2.py and the other test files. The 26 welded tests were also run by the reviewer in a separate clone (VERIFIED). The full suite has NOT been re-run since P12a (last full-suite result: 315 passed, 1 skipped, 1 xfailed). It must be re-run locally before the P12b freeze commit and before any P13 run; a failure blocks the freeze. No R-C run is authorised until the dated P12b amendment is recorded.

P14a-2 partial run, 2026-11-25, rl_env, HEAD 9375dce: pytest -q --ignore=tests/test_baselines2.py -p no:cacheprovider -> 342 passed, 1 skipped in 178.26 s. READ — project lead's terminal output. This run excludes tests/test_baselines2.py and is not comparable to the P12a total (315 passed, 1 skipped, 1 xfailed). The full suite including test_baselines2.py has NOT been re-run since P12a; it remains required before the P12b freeze and before any P13 run.

## Steel density convention (PROVISIONAL)

`rho = 7850 kg/m³`. **READ** — source: `docs/engineering_concepts.md:95`. The Stage 1 catalogue-implied density over 107 sections is min 7818.93004115, max 7884.61538462, mean 7850.52669319 kg/m³ (**VERIFIED** by calculation). Command used: `conda run -n rl_env python -c 'from pathlib import Path; from ub_rl.catalogue import parse_workbook; p=Path("data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"); full,_=parse_workbook(p); c=full.mass_ordered(include_plus=True); rho=1e4*c["m"]/c["A"]; print(f"sections={len(c)} min={rho.min():.12g} max={rho.max():.12g} mean={rho.mean():.12g}")'`. The earlier run printed the value in g/cm³ because of a unit slip in the request, not a data issue. The authoritative standard, edition and clause are not yet confirmed (candidate: EN 1993-1-1 §3.2.6, unverified recollection). To be confirmed before P15, before any Stage 2 result or claim.
