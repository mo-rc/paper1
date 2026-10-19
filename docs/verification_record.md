# Verification record (checker, patch 0004)

Status of clause details used by `src/ub_rl/checker.py`. "Confirmed" means read in a public SCI source named below. Nothing here is a Gate 2 result.

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

- SCI AD 368 gives Vb,Rd = 1768 kN for 762x267x134. That equals eta fy hw tw / sqrt(3) with no chi_w reduction. The method stated in the same note gives 1722 kN (chi_w = 0.974), which the checker uses. For 406x140x39 the note's 488 kN is reproduced within 0.4% (the note rounds eps to 0.81). To be resolved at Gate 2 against the Blue Book table.

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
| G | 81,000 N/mm2 | EN 1993-1-1 |

**Intermediate restraints.** With restraints between the supports, the critical segment does not carry the full-span UDL moment shape. Using the UDL factors (C1 = 1.127, kc = 0.94) there would be unconservative: on 600 random contexts at ratios 0.25 and 0.5 the lightest feasible section changes in about 63 % of cases when the uniform-moment factors (C1 = 1, kc = 1) are used instead. The checker therefore uses the uniform-moment factors for 0 < ratio < 1 (conservative, applied at the maximum design moment) and the UDL factors only at ratio 1. The factor jumps at ratio 1, which is accepted as a conservative modelling choice. Per-segment moment diagrams are a Gate 2 sensitivity.

Not confirmed (to be closed at Gate 2 against the Blue Book Mb,Rd tables):

- Curve selection for rolled I sections (h/b <= 2: b, alpha 0.34; > 2: c, alpha 0.49) and kc = 0.94 for a UDL are taken from reproductions of EN 1993-1-1 Tables 6.5 and 6.6, not read from the standard.
- The f-factor form and the condition under which LTB may be ignored are written from the standard formulas as reproduced in guides.
- The Blue Book Mb,Rd values may use a different equivalent-uniform-moment treatment; the comparison must use the same moment diagram and load position as the tabulated cases.
- The UK NA position on 6.3.2.3 for UB sections is assumed to retain the recommended values; not read in the NA text.
- Only UDL is implemented; point-load patterns need C1 = 1.348 and kc = 0.86 and a different moment distribution for the interaction and bearing checks.
- The second implementation shares the catalogue and the classification with the checker and was written by the same author, so it checks the arithmetic, not the understanding of the standard.

Exploratory reference-case optima (L = 9 m, 56.7675 kN/m, self-weight included, shear-centre loading), ratios 0, 0.25, 1/3, 0.5, 1.0: 457x191x74, 533x210x82, 533x210x92, 610x229x101, 686x254x140. Top-flange loading: 457x191x74, 533x210x82, 533x210x92, 610x229x113, 610x305x149. Unvalidated until Gate 2.
