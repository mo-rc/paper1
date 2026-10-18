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
