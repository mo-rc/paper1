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
