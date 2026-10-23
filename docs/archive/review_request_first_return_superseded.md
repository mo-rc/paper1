# Review request: engineering check of the beam-design checker

**For:** the supervising structural engineer. **You do not need to read any code.**

## What this is

A program checks a simply supported steel I-beam (S355, UDL) against Eurocode 3 with the UK National Annexes: classification, bending, shear, shear buckling, web bearing, lateral-torsional buckling and deflection. A learning method will later propose beams, and this program decides whether each proposal is safe. If the program is wrong, every result built on it is wrong, so it needs an engineer's check before anything else is done. The people who wrote it cannot be the ones who accept it.

## What has already been checked (by the authors)

- The resistances (bending, shear, web bearing, LTB resistance) for all 107 UB sections agree with the SCI Blue Book tables to table rounding.
- A second, separately written version of the program gives the same results.
- This does **not** cover the chain from loads to utilisation (actions, combinations, deflection, interaction), and it does not cover the assumptions below. That is what needs your check.

## What we ask you to do

**1. Answer yes or no on each assumption** (table below).

**2. Check cases by hand.** `docs/gate2_cases.md` has 14 worked cases, G2-01 to G2-14. Each shows the section, loads, actions, resistances and every utilisation. The loads of some cases are deliberately extreme or small so that one check governs; they are not design loads. Please recompute the 8 required cases (table below) with your own method (hand, spreadsheet, or the design software you normally use) and compare. Where a number differs by more than rounding (0.5 % is the pre-set tolerance), note it. A worked example of case G2-01, step by step, is in `docs/review_worked_example.md`. The three LTB cases use unrestrained lengths listed in the Blue Book table, so Mb,Rd can be read directly. All 14 cases (8 required, 6 optional) are also in an Excel workbook (hand-calculation formulas, program values, yellow cells for your own values, automatic differences), built by `scripts/make_hand_check_workbook.py` and sent separately because it contains Blue Book data.

| Case | Why it matters | Required |
|---|---|---|
| G2-01 reference beam | The case used throughout | yes |
| G2-02 shear governs | Shear resistance and shear area | yes |
| G2-06 web bearing governs | Bearing resistance, ss = 100 mm | yes |
| G2-07, G2-08 deflection (variable load L/360; total load L/250) | Serviceability limits and loads | yes |
| G2-09, G2-10, G2-11 LTB (restraint at 1/3 span, 1/2 span, none) | LTB resistance and moment factors | yes |
| G2-03, G2-04 the two shear-buckling sections; G2-05 bending-shear interaction | Occur only far above the usable range | optional |
| G2-12, G2-13, G2-14 lightest, heaviest, Class 2 sections | Edge cases | optional |

**3. Say what is missing.** Is there a check you would expect for this member that is not in the list above?

**4. Sign the form** at the end and return it.

If you cannot do this yourself, a colleague or PhD student experienced in Eurocode 3 can, but they should not be someone who worked on the program.

## Assumptions to confirm

| # | Assumption | Agree? |
|---|---|---|
| 1 | EN 1993-1-1 and EN 1993-1-5 with UK NAs; S355; gamma_M0 = gamma_M1 = 1.0 | Agree |
| 2 | Load combination EN 1990 6.10: 1.35 dead, 1.5 live; self-weight added with 1.35 | Agree |
| 3 | Yield strength by plate thickness: 355, 345, 335, 325 N/mm2 for t up to 16, 40, 63, 80 mm | Agree |
| 4 | Deflection: variable load only, span/360 (primary); also span/200 and span/250 on total load | Not agree |
| 5 | Web bearing: stiff bearing 100 mm, c = 0, unstiffened web, load at the end; where two valid solutions exist the higher resistance is taken (SCI AD 378 and the Blue Book) | Agree |
| 6 | Shear buckling: stiffeners at the supports only, eta = 1.0 (affects 406x140x39 and 762x267x134 only) | Agree |
| 7 | Class 4 sections are treated as unsafe; none exists in the catalogue | Agree |
| 8 | LTB: base case fully restrained; restraint spacing as a fraction of the span; moment factors C1 = 1.127 and kc = 0.94 only when restraints are at the supports, and the conservative uniform-moment values (C1 = 1, kc = 1) when restraints are between the supports; load at the shear centre | Agree |
| 9 | Catalogue: the 91 sections of BS EN 10365 as the main set; all 107 as a sensitivity set | Agree |
| 10 | UDL only; simply supported; one span | Agree |
| 11 | LTB buckling curve and parameters (UK NA, rolled I sections): curve b for h/b <= 2, c for 2 < h/b <= 3.1, d above 3.1; lambda_LT,0 = 0.4, beta = 0.75; kc = 1/sqrt(C1) (0.94 for C1 = 1.127); EN 1993-1-1 6.3.2.3 | Agree |
| 12 | LTB utilisation = maximum span moment divided by the buckling resistance of a segment of length Lcr (conservative where the moment is lower in the segment) | Agree |

Not validated and not used in any result: loads on the top flange (destabilising).

Not in the program (outside the scope of this study): axial force, torsion, web openings, intermediate point loads, connections, fire, vibration, composite action.

## Sign-off form

Name and role: ____________________   Date: __________

| Case | Recomputed? | Agrees (rounding)? | Notes |
|---|---|---|---|
| G2-01 | | | |
| G2-02 | | | |
| G2-06 | | | |
| G2-07 | | | |
| G2-08 | | | |
| G2-09 | | | |
| G2-10 | | | |
| G2-11 | | | |

Assumptions 1 to 12: agree with all / disagree with items: ____________________

Missing or wrong checks: ____________________

I have compared the cases above with my own calculation and found the program consistent with Eurocode 3 and the UK NA except as noted.

Signature: ____________________
