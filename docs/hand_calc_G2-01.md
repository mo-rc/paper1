# Hand calculation: formulas step by step (inputs shown for G2-01, the reference beam; other cases in section 5)

**Purpose.** Work through every step with a calculator, write your answer in the "Your result" column, then type it into the yellow cell of the sheet **G2-01** (the sheet row name is given in each step).
The formulas are the ones the program uses (`src/ub_rl/checker.py`): Eurocode 3 (EN 1993-1-1, EN 1993-1-5) with the UK National Annex.

**Rules.** Use only the inputs below. Do not look at the grey "Program" column or at `gate2_cases.md` until you have finished. Differences up to 0.5 % are rounding.

## 1. Inputs (given, the same for everyone)

| Symbol | Meaning | Value | Unit |
|---|---|---|---|
| Section | UB, S355 | 457x191x74 | |
| m | mass per metre | 74.3 | kg/m |
| h | depth | 457.0 | mm |
| b | width | 190.4 | mm |
| tw | web thickness | 9.0 | mm |
| tf | flange thickness | 14.5 | mm |
| r | root radius | 10.2 | mm |
| A | area | 94.6 | cm² |
| Iy | second moment of area | 33 300 | cm⁴ |
| Wpl | plastic modulus | 1 650 | cm³ |
| cf/tf | flange ratio (Blue Book) | 5.55 | |
| cw/tw | web ratio (Blue Book) | 45.3 | |
| L | span | 9.0 | m |
| w | factored superimposed load, self-weight excluded | 56.7675 | kN/m |
| live load, unfactored | 3.0 kN/m² × 6 m tributary width | 18.0 | kN/m |
| γG, γQ, γM0 | partial factors | 1.35, 1.5, 1.0 | |
| E | Young's modulus | 210 000 | N/mm² |
| deflection rule | variable (live) load only, limit L / 360 | | |
| Blue Book Mc,y,Rd | bending table, 457x191x74 | 586 | kNm |
| Blue Book Vc,Rd | web bearing table | 895 | kN |
| Blue Book FRd | web bearing table, ss = 100 mm, c = 0 | 408 | kN |

## 2. Steps

| # | Sheet row | Formula | Your result | Unit |
|---|---|---|---|---|
| 1 | Yield strength fy | fy = 355 if max(tf, tw) ≤ 16 mm; 345 if ≤ 40; 335 if ≤ 63; 325 if ≤ 80 | | N/mm² |
| 2 | (not in sheet) | ε = √(235 / fy) | | |
| 3 | Section class | Flange: class 1 if cf/tf ≤ 9ε, class 2 if ≤ 10ε, class 3 if ≤ 14ε. Web: class 1 if cw/tw ≤ 72ε, class 2 if ≤ 83ε, class 3 if ≤ 124ε. Section class = the larger of the two | | |
| 4 | Web height hw | hw = h − 2 tf | | mm |
| 5 | Self-weight g (not a yellow row) | g = m × 9.80665 / 1000 | | kN/m |
| 6 | Total factored load wEd | wEd = w + γG × g | | kN/m |
| 7 | Design moment MEd | MEd = wEd × L² / 8 | | kNm |
| 8 | Design shear force VEd | VEd = wEd × L / 2 | | kN |
| 9 | Bending resistance Mc,Rd | Mc,Rd = Wpl × 1000 × fy / γM0 / 10⁶ (classes 1 and 2). Compare with the Blue Book 586 | | kNm |
| 10 | Bending utilisation | u_bending = MEd / Mc,Rd | | |
| 11 | Shear area Av (not a yellow row) | Av = A × 100 − 2 b tf + (tw + 2 r) tf. Av must not be less than hw × tw; take the larger | | mm² |
| 12 | Shear resistance Vpl,Rd | Vpl,Rd = Av × fy / (√3 × γM0) / 1000. Compare with the Blue Book 895 | | kN |
| 13 | Shear utilisation | u_shear = VEd / Vpl,Rd | | |
| 14 | Shear buckling needed? | Needed only if hw / tw > 72 ε. Compare and write yes or no | | |
| 15 | Web bearing resistance FRd | Read from the Blue Book web bearing table, ss = 100 mm, c = 0: 408 | | kN |
| 16 | Web bearing utilisation | u_bearing = VEd / FRd | | |
| 17 | (not in sheet) | Live load Qk = (27 / 56.7675) × w / 1.5, with w the load of the case (G2-01: w = 56.7675, so Qk = 18.0). Deflection under the variable-load rule uses Qk only. For G2-08 (total load) see the last item of section 4 | | kN/m |
| 18 | Deflection | δ = 5 × Qk × (L × 1000)⁴ / (384 × E × Iy × 10⁴). Qk in kN/m is used as N/mm | | mm |
| 19 | Deflection limit | limit = L × 1000 / 360 | | mm |
| 20 | Deflection utilisation | u_deflection = δ / limit | | |
| 21 | Bending-shear interaction | If VEd ≤ 0.5 × Vpl,Rd, shear does not reduce the moment resistance, so the utilisation equals u_bending. Otherwise use the rule in section 3 | | |
| 22 | Highest utilisation | Largest of u_bending, u_shear, u_bearing, u_deflection, u_interaction | | |
| 23 | Lateral-torsional buckling | Not applicable in G2-01 (beam fully restrained). See section 4 for G2-09 to G2-11 | not used | |

**Pass rule.** The beam passes if the highest utilisation is 1.00 or less.

## 3. Bending-shear interaction when VEd > 0.5 Vpl,Rd (not needed for G2-01; used in G2-02 and G2-05)
At each position x along the span: M(x) = wEd × x × (L − x) / 2 and V(x) = wEd × (L / 2 − x).
- ρ = (2 V(x) / Vpl,Rd − 1)² if V(x) > 0.5 Vpl,Rd, otherwise 0 (ρ is not taken above 1).
- Mv,Rd(x) = (Wpl × 1000 − ρ × (hw × tw)² / (4 tw)) × fy / γM0 / 10⁶, and not more than Mc,Rd.
- u(x) = M(x) / Mv,Rd(x). The interaction utilisation is the largest u(x) along the span (the program uses 101 equally spaced positions).

## 4. Formulas for other cases (not needed for G2-01)
**Lateral-torsional buckling (G2-09, G2-10, G2-11).** Lcr = distance between lateral restraints. For the hand check, read Mb,Rd from the Blue Book buckling table at Lcr and the C1 row stated on the sheet, then u_LTB = MEd / Mb,Rd.
The program does not read the table; it computes Mb,Rd as follows (for reference only):
- Mcr = C1 π² E Iz / Lcr² × √( Iw / Iz + Lcr² G It / (π² E Iz) ), with G = E / (2 × 1.3) = 80 769 N/mm² (load at the shear centre).
- λLT = √(Wpl fy / Mcr).
- φ = 0.5 [1 + α (λLT − 0.4) + 0.75 λLT²]; χ = 1 / (φ + √(φ² − 0.75 λLT²)), not more than 1 and not more than 1 / λLT².
- α = 0.34 if h/b ≤ 2; 0.49 if 2 < h/b ≤ 3.1; 0.76 if h/b > 3.1 (UK National Annex, rolled sections).
- f = 1 − 0.5 (1 − kc) [1 − 2 (λLT − 0.8)²], not more than 1; χ,mod = χ / f, not more than 1; kc = 1 / √C1. No reduction (χ = 1) if λLT ≤ 0.4 or MEd / Mcr ≤ 0.16.
- Mb,Rd = χ,mod × Wpl × fy / 10⁶ (kNm).

**Shear buckling (G2-03, G2-04; sections 406x140x39 and 762x267x134).**
- λw = hw / (86.4 tw ε); χw = smaller of 1.0 and 0.83 / λw; Vb,Rd = χw fy hw tw / (√3 γM1) / 1000 (kN); u = VEd / Vb,Rd.
- Interaction (EN 1993-1-5, 7.1): Mpl = Wpl fy / 10⁶; Mf = b tf (h − tf) fy / 10⁶ (kNm). At each position: η3 = V(x) / Vb,Rd. If η3 > 0.5, u = M / Mpl + (1 − Mf / Mpl) (2 η3 − 1)²; otherwise u = M / Mc,Rd.

**Web bearing (G2-06).** Resistance FRd is read from the Blue Book table (ss = 100 mm, c = 0); u = VEd / FRd.

**Deflection under total load (G2-08, limit L / 250).** q = Qk + Gk + g where Qk = (live share) × w / 1.5, Gk = (1 − live share) × w / 1.35, g = self-weight (unfactored), live share = 27.0 / 56.7675.

## 5. Load and span of every case (for step 6 onwards, and for Qk in step 17)
Section properties of each case are in the blue cells at the top of its sheet. Qk = (27 / 56.7675) × w / 1.5 for every case.

| Case | Section | L (m) | w (kN/m) | Lcr / L | Deflection rule |
|---|---|---|---|---|---|
| G2-01 | 457x191x74 | 9 | 56.7675 | 0.0000 | variable L/360 |
| G2-02 | 203x133x25 | 1 | 523.7607 | 0.0000 | variable L/360 |
| G2-03 | 406x140x39 | 1 | 2542.7970 | 0.0000 | variable L/360 |
| G2-04 | 762x267x134 | 1.5 | 7290.6162 | 0.0000 | variable L/360 |
| G2-05 | 203x133x30 | 1.5 | 985.3815 | 0.0000 | variable L/360 |
| G2-06 | 1016x305x222 | 2 | 886.8683 | 0.0000 | variable L/360 |
| G2-07 | 305x127x42 | 7.5 | 27.4325 | 0.0000 | variable L/360 |
| G2-08 | 762x267x147 | 12 | 87.3904 | 0.0000 | total L/250 |
| G2-09 | 356x171x57 | 6 | 70.7902 | 0.3333 | variable L/360 |
| G2-10 | 305x102x33 | 3 | 119.8669 | 0.5000 | variable L/360 |
| G2-11 | 1016x305x415 | 12 | 133.1817 | 1.0000 | variable L/360 |
| G2-12 | 127x76x13 | 3 | 10.0000 | 0.0000 | variable L/360 |
| G2-13 | 1016x305x584 | 9 | 400.0000 | 0.0000 | variable L/360 |
| G2-14 | 356x171x45 | 6 | 60.0000 | 0.0000 | variable L/360 |
