# Checking the beam program by hand: a worked example

**For the supervising engineer. No programming is needed.**

## What you are asked to do

The program decides whether a steel beam is safe. For a beam and a load it prints a list of numbers called utilisations (demand divided by resistance; 1.00 or less means that check passes). We ask you to recompute those numbers yourself for eight cases and tell us where they differ. The first case is worked below so you can see exactly what is meant.

You need: the SCI Blue Book (UB tables, S355, Eurocode 3 UK NA) or the section values listed here, a calculator or spreadsheet, and the case sheets (`docs/gate2_cases.md`).

## The reference beam (case G2-01)

Beam: 457x191x74 UB, S355, simply supported, span 9.0 m, fully restrained laterally. Load: dead 3.675 kN/m2, live 3.0 kN/m2, tributary width 6 m, factors 1.35 and 1.5, self-weight added.

Section values (Blue Book): mass 74.3 kg/m; h 457.0; b 190.4; tw 9.0; tf 14.5; r 10.2 mm; A 94.6 cm2; Iy 33,300 cm4; Wpl,y 1,650 cm3; cf/tf 5.55; cw/tw 45.3. Yield strength fy = 355 N/mm2 (tf is 16 mm or less).

## Step by step

| Step | What to calculate | Result | Program shows |
|---|---|---|---|
| 1 Load | Superimposed (1.35 x 3.675 + 1.5 x 3.0) x 6 = 56.7675 kN/m. Self-weight 74.3 x 9.81 / 1000 = 0.729 kN/m, times 1.35 = 0.984 kN/m. Total wEd | 57.751 kN/m | 57.751 |
| 2 Actions | MEd = wEd L2 / 8 = 57.751 x 9^2 / 8. VEd = wEd L / 2 | MEd 584.7 kNm; VEd 259.9 kN | 584.73; 259.88 |
| 3 Class | eps = sqrt(235/355) = 0.814. Flange 5.55 is below 9 eps = 7.32. Web 45.3 is below 72 eps = 58.6 | Class 1 | Class 1 |
| 4 Bending | Mc,Rd = Wpl fy = 1650 x 10^3 x 355 (Blue Book: 586 kNm). Utilisation MEd / Mc,Rd | 585.75 kNm; 0.998 | 0.9983 |
| 5 Shear | Av = A - 2 b tf + (tw + 2r) tf = 9460 - 5522 + 426 = 4365 mm2. Vpl,Rd = Av fy / sqrt(3) (Blue Book: 895 kN). Utilisation VEd / Vpl,Rd | 894.6 kN; 0.291 | 0.2905 |
| 6 Shear buckling and interaction | hw/tw = 428 / 9 = 47.6 is below 72 eps = 58.6, so shear buckling is not checked. VEd 259.9 kN is below 0.5 Vpl,Rd = 447 kN, so shear does not reduce the moment resistance | not governing | 0.9983 (equals bending) |
| 7 Web bearing | FRd from the Blue Book web bearing table, stiff bearing 100 mm, c = 0: 408 kN. Utilisation VEd / FRd | 0.637 | 0.6374 |
| 8 Deflection | Variable load only: Qk = 3.0 x 6 = 18 kN/m. Deflection = 5 Qk L^4 / (384 E Iy) = 5 x 18 x 9000^4 / (384 x 210000 x 3.33 x 10^8). Limit L / 360 = 25 mm | 22.0 mm; 0.880 | 0.8796 |
| 9 Lateral-torsional buckling | Fully restrained in this case | not applicable | not applicable |

**Result.** The highest utilisation is bending, 0.998, so the beam passes and bending governs. The next lighter section in the catalogue, 457x191x67, fails in the program (bending 1.119), so 457x191x74 is the lightest section that passes.

## How close must the numbers be?

Within about 0.5 %. The Blue Book rounds to three significant figures (for example 585.75 kNm appears as 586), so small differences are rounding and do not count. If a number differs by more than that, please write down your value and the program's value.

## The other seven required cases

Each case sheet in `docs/gate2_cases.md` lists the section, the loads, the actions, the resistances and every utilisation. Recompute with the same steps:

| Case | What it tests | What to recompute |
|---|---|---|
| G2-02 | shear governs | step 5 |
| G2-06 | web bearing governs | step 7, resistance from the Blue Book table |
| G2-07 | deflection, variable load only, L/360 | step 8 |
| G2-08 | deflection, total load, L/250 | step 8 with the total unfactored load (dead + live + self-weight) listed on the sheet |
| G2-09 | lateral-torsional buckling, restraint every 1/3 span (356x171x57, L = 6.0 m, Lcr = 2.0 m) | utilisation = MEd / Mb,Rd, with Mb,Rd from the Blue Book buckling table at Lcr, C1 = 1.00 |
| G2-10 | lateral-torsional buckling, restraint at mid-span (305x102x33, L = 3.0 m, Lcr = 1.5 m) | as G2-09, C1 = 1.00 |
| G2-11 | lateral-torsional buckling, unrestrained (1016x305x415, L = 12.0 m) | as G2-09, using the C1 = 1.13 row; the program uses 1.127, so expect a tiny difference |

For the lateral-torsional buckling cases: Lcr is the distance between lateral restraints. Where restraints lie between the supports the program uses the uniform-moment factor (C1 = 1.00), which is conservative. The authors have compared these three cases with the Blue Book table and found Mb,Rd within 0.25 %. G2-11 uses buckling curve d (h/b above 3.1).

## What to send back

1. For each of the eight cases: "agrees", or your value and the program's value where they differ.
2. Agree or disagree for each of the 12 assumptions in `docs/review_request.md`.
3. Any check you would expect for this member that is not in the list.
4. The signed form at the end of `docs/review_request.md`.
