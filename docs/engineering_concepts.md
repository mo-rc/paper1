# Engineering concepts behind the checker

For readers who know machine learning and code but not structural engineering. It explains what the program computes, why, the
formulas it uses (the same ones as `src/ub_rl/checker.py`), and which variable in the code each symbol is. It is not the research
proposal and not a design guide. Clause numbers are Eurocode 3 (EN 1993-1-1 and EN 1993-1-5) with the UK National Annex; the
program implements them as listed in `docs/verification_record.md`, which also states what is verified and what is open.

## 1. The problem in one page

A **beam** is a horizontal member that carries load across a span between two supports. Here: one simply supported steel I-beam
(a Universal Beam, UB, from the SCI Blue Book catalogue), steel grade S355, carrying a uniformly distributed load (UDL).

The design question: **which catalogue section is the lightest that is still safe?**

"Safe" is a list of checks. Each check compares a **demand** (what the load does to the beam) with a **resistance** (what the
beam can take):

```
utilisation = demand / resistance        passes if utilisation <= 1.0
```

A section is **feasible** if every check passes. The program returns every utilisation, the largest one (the **governing** check) and
the feasible flag. For the learning problem, a section is the action, the context (span, load, restraint, deflection rule, depth
cap) is the state, utilisations are the constraint values, mass is the cost, and an unsafe section is never rewarded.

Two kinds of limit state are checked:

| Limit state | Meaning | Checks here |
|---|---|---|
| Ultimate (ULS) | the beam must not fail or collapse | classification, bending, shear, shear buckling, bending-shear interaction, web bearing, lateral-torsional buckling |
| Serviceability (SLS) | the beam must stay usable | deflection |

ULS uses factored (increased) loads. SLS uses unfactored (characteristic) loads.

## 2. Notation: symbol, meaning, unit, name in the code

Inside the code the units are mm, N and N/mm2; at the interface (results, tables) they are m, kN and kNm. The catalogue is in cm
units and is converted when the checker is built (A x 100, Iy x 1e4, W x 1e3, Iw x 1e12).

| Symbol | Meaning | Unit (interface) | In the code |
|---|---|---|---|
| L | span between supports | m | `L` |
| w | factored superimposed UDL (self-weight excluded) | kN/m | `w` |
| g | self-weight of the section per metre | kN/m | `Checker.self_w`, `cfg.self_weight` |
| w_Ed | total factored UDL = w + 1.35 g | kN/m | `w_Ed` |
| V_Ed | design shear force (largest, at a support) | kN | `V_Ed` |
| M_Ed | design bending moment (largest, at mid-span) | kNm | `M_Ed` |
| h, b | section depth, flange width | mm | `catalogue['h']`, `['b']` |
| tw, tf | web thickness, flange thickness | mm | `['tw']`, `['tf']` |
| r | root radius (fillet between web and flange) | mm | `['r']` |
| hw | web height between flanges = h - 2 tf | mm | `Checker.hw` |
| cf, cw | width of the flange outstand, depth of the web, counted for local buckling | mm | `['cf_tf']`, `['cw_tw']` (ratios) |
| A | cross-section area | cm2 (table), mm2 (code) | `['A']` |
| Iy, Iz | second moment of area about the strong axis y-y, weak axis z-z | cm4 (table), mm4 (code) | `Checker.Iy`, `Checker.Iz` |
| Wel,y | elastic section modulus = Iy / (h/2) | cm3 | `Checker.Wel` |
| Wpl,y | plastic section modulus | cm3 | `Checker.Wpl` |
| It | torsion constant (St Venant) | cm4 | `Checker.It` |
| Iw | warping constant | dm6 (table), mm6 (code) | `Checker.Iw` |
| fy | yield strength of the steel | N/mm2 | `Checker.fy` |
| E, G | Young's modulus, shear modulus | N/mm2 | `E_STEEL`, `G_STEEL` (config.py) |
| epsilon | sqrt(235 / fy), scales the class limits | none | `Checker.eps` |
| class | section class 1 to 4 | none | `Checker.cls` |
| gamma_M0, gamma_M1 | partial safety factors on resistance | none | `cfg.gamma_M0`, `cfg.gamma_M1` |
| Mc,Rd | design bending resistance | kNm | `Checker.Mc` |
| Vpl,Rd | design plastic shear resistance | kN | `Checker.Vpl` |
| Vb,Rd | shear buckling resistance (web part) | kN | `Checker.Vbw` |
| F_Rd | web bearing resistance at a support | kN | `Checker.F_Rd` |
| Mcr | elastic critical moment (lateral-torsional buckling) | kNm | `M_cr` (result key) |
| Mb,Rd | lateral-torsional buckling resistance | kNm | `M_b_Rd` (`CheckResult`) |
| Lcr | distance between lateral restraints | m | `restraint_ratio * L` |
| u | utilisation = demand / resistance | none | `u_bending`, `u_shear`, ... |

The subscript **Ed** means "design value of an action effect" (demand); **Rd** means "design value of a resistance"; **Rk** means
characteristic (before dividing by gamma). **y-y** is bending in the plane of the web (the strong axis).

## 3. The beam and its section

```
        b
   |<-------->|          flange (thickness tf)
   ############  ---
        #         |
        #         |  hw = h - 2 tf     web (thickness tw)
        #         |
   ############  ---                   h = total depth
        r = root radius where web meets flange
```

The section carries bending mainly in the two flanges (one in compression, one in tension, like the chords of a truss), and shear
mainly in the web. That is why an I-section is efficient.

**Section properties** describe the geometry with single numbers. The program reads them from the Blue Book table (it never
recomputes them from the dimensions):

- **A**, area. Mass per metre = A x 0.785 kg/m per cm2 (steel density 7850 kg/m3).
- **Iy**, second moment of area about the strong axis = sum of (area x distance squared from the axis). It controls stiffness:
  deflection is inversely proportional to Iy.
- **Wel,y = Iy / (h/2)**, elastic section modulus. The moment at which the extreme fibre first reaches fy is Wel x fy.
- **Wpl,y**, plastic section modulus. When the whole section has yielded (every fibre at fy, tension below and compression above the
  plastic neutral axis) the moment is Wpl x fy. For an idealised I-section without fillets:
  `Wpl = b tf (h - tf) + tw hw^2 / 4`. Wpl is always larger than Wel; for the 107 UBs the ratio Wpl/Wel is 1.11 to 1.19 (the "shape factor").
- **Iz**, weak-axis second moment, **It**, torsion constant, **Iw**, warping constant: needed only for lateral-torsional buckling
  (section 6.7) because that failure mode combines sideways bending with twisting.

## 4. Material

Steel grade **S355**: nominal yield strength fy depends on the thickest element t = max(tf, tw), because thick plates cool slower:

```
fy = 355 N/mm2 if t <= 16 mm;  345 if t <= 40;  335 if t <= 63;  325 if t <= 80
```

- **Young's modulus E = 210 000 N/mm2**: stiffness in tension and compression (stress / strain). Enters deflection and buckling.
- **Shear modulus G = E / (2 (1 + nu)) = 80 769 N/mm2** with Poisson's ratio nu = 0.3. Enters torsion (Mcr).
- **epsilon = sqrt(235 / fy)** (0.814 for S355). Higher strength steel buckles locally earlier, so the class limits shrink with epsilon.

## 5. Loads and the forces they cause

**Load types.** Dead load G (permanent: floor, finishes, self-weight), live load Q (variable: people, furniture). Floor loads are in
kN/m2 and become a line load on the beam: `line load (kN/m) = floor load (kN/m2) x tributary width (m)`.

**Factors (EN 1990, equation 6.10, UK NA).** For ULS the loads are increased: `factored = 1.35 G + 1.5 Q`. The reference case
(dead 3.675, live 3.0 kN/m2, width 6 m) gives `w = (1.35 x 3.675 + 1.5 x 3.0) x 6 = 56.7675 kN/m`. The program adds the beam's own
weight: `w_Ed = w + 1.35 g`, with `g = mass (kg/m) x 9.80665 / 1000` (kN/m).

**Statics of a simply supported beam under a UDL** (position x measured from the left support):

```
reactions:        R = w_Ed L / 2                     (each support)
shear force:      V(x) = w_Ed (L/2 - x)              (largest at the supports: V_Ed = w_Ed L / 2)
bending moment:   M(x) = w_Ed x (L - x) / 2          (largest at mid-span:     M_Ed = w_Ed L^2 / 8)
```

```
 w_Ed (kN/m)  v v v v v v v v v v v v v
             ===========================
             /\                         /\          shear V(x): +V_Ed at the left support, 0 at mid-span, -V_Ed at the right
            R                           R           moment M(x): 0 at the supports, M_Ed at mid-span (a parabola)
```

The interaction check (section 6.5) evaluates M(x) and V(x) at 101 equally spaced positions along the span.

## 6. The checks, one by one

Every check below ends with its utilisation. All of them must be 1.0 or less.

### 6.1 Classification (local buckling), EN 1993-1-1 Table 5.2

A thin plate in compression (the flange tip or the web) can buckle locally (wrinkle) before the steel yields. The class says how
slender the plates are and so how much bending the section can reach:

| Class | Behaviour | Bending resistance uses |
|---|---|---|
| 1 | plastic moment reached and the section can rotate (plastic hinge) | Wpl |
| 2 | plastic moment reached, limited rotation | Wpl |
| 3 | yield at the extreme fibre, then local buckling | Wel |
| 4 | local buckling before yield | effective section (not implemented) |

Ratios (given by the Blue Book as `cf/tf` for the flange and `cw/tw` for the web) are compared with the limits:

```
flange outstand (compression):  class 1 if cf/tf <= 9 eps;   class 2 if <= 10 eps;  class 3 if <= 14 eps
web in bending:                 class 1 if cw/tw <= 72 eps;  class 2 if <= 83 eps;   class 3 if <= 124 eps
section class = the larger (worse) of the flange class and the web class
```

Class 4 sections are treated as infeasible (assumption in the spec). Among the 107 UBs at S355, 106 are class 1, one is class 2 and
none is class 3 or 4. Code: `Checker.cls`.

### 6.2 Bending resistance, EN 1993-1-1 6.2.5

```
Mc,Rd = Wpl fy / gamma_M0     (class 1 and 2)           u_bending = M_Ed / Mc,Rd
Mc,Rd = Wel fy / gamma_M0     (class 3)
```

gamma_M0 = 1.0. Units: Wpl cm3 x 1000 -> mm3; x fy (N/mm2) -> N mm; / 1e6 -> kNm. Code: `Checker.Mc`, `u_bending`.

### 6.3 Shear resistance, EN 1993-1-1 6.2.6

The web resists the vertical shear force. Steel yields in shear at fy / sqrt(3) (von Mises criterion). The shear area is the part of the
section that carries shear:

```
Av = A - 2 b tf + (tw + 2 r) tf        (rolled I-section), not less than eta hw tw, with eta = 1.0
Vpl,Rd = Av fy / (sqrt(3) gamma_M0)                      u_shear = V_Ed / Vpl,Rd
```

Code: `Checker.Av`, `Checker.Vpl`, `u_shear`.

### 6.4 Shear buckling of the web, EN 1993-1-5 clauses 5.2 and 5.3

A slender web can buckle in shear before it yields. It matters only if the web is slender:

```
check required if   hw / tw > 72 eps / eta                  (eta = 1.0, UK NA)
lambda_w = hw / (86.4 tw eps)                               (web with stiffeners at the supports only)
chi_w    = min(eta, 0.83 / lambda_w)                        (Table 5.1, non-rigid end post)
Vb,Rd    = chi_w fy hw tw / (sqrt(3) gamma_M1)              u_shear_buckling = V_Ed / Vb,Rd
```

The flange contribution is ignored (conservative). In the catalogue only 406x140x39 and 762x267x134 reach this limit. Code:
`Checker.sb` (applies?), `Checker.Vbw`, `u_shear_buckling` (0 where it does not apply).

### 6.5 Bending-shear interaction, EN 1993-1-1 6.2.8 and EN 1993-1-5 7.1

Where the shear force is large the web is partly used up by shear and bending resistance falls. At each of the 101 positions x:

```
if V(x) <= 0.5 Vpl,Rd:   no reduction:  u(x) = M(x) / Mc,Rd
else:  rho = (2 V(x) / Vpl,Rd - 1)^2   (not above 1)
       Mv,Rd(x) = [ Wpl - rho (hw tw)^2 / (4 tw) ] fy / gamma_M0,  not more than Mc,Rd
       u(x) = M(x) / Mv,Rd(x)
u_bending_shear = the largest u(x)
```

For the two shear-buckling sections EN 1993-1-5 7.1 is used instead: eta3 = V(x) / Vb,Rd; if eta3 > 0.5,
`u = M / Mpl + (1 - Mf / Mpl) (2 eta3 - 1)^2` with Mpl = Wpl fy and Mf the flange-only moment `b tf (h - tf) fy`; otherwise `u = M / Mc,Rd`.
For a UDL on a simply supported beam this governs only at utilisations above about 2.4, so it never decides a realistic design.
A class 3 section with shear reduction is not implemented (none exists in the catalogue) and is treated as infeasible. Code:
`Checker._interaction`, `u_bending_shear`.

### 6.6 Web bearing at the supports, EN 1993-1-5 clause 6

At a support the reaction pushes up into the bottom flange and is carried by the web: a concentrated force that can crush or buckle
the web locally. Assumptions: the load acts on a stiff bearing length ss = 100 mm at the very end of the beam (c = 0), the web is
unstiffened, and the supports are fork supports.

```
kF  = min(2 + 6 (ss + c) / hw, 6)                         Fcr = 0.9 kF E tw^3 / hw
le  = min(kF E tw^2 / (2 fy hw), ss + c)                  m1 = fy b / (fy tw)
m2  = 0.02 (hw / tf)^2  if lambda_F > 0.5, else 0
ly  = smallest of  ss + 2 tf (1 + sqrt(m1 + m2));  le + tf sqrt(m1/2 + (le/tf)^2 + m2);  le + tf sqrt(m1 + m2)
lambda_F = sqrt(ly tw fy / Fcr);   chi_F = min(0.5 / lambda_F, 1)
F_Rd = fy chi_F ly tw / gamma_M1                          u_web_bearing = V_Ed / F_Rd
```

Because m2 depends on lambda_F, both cases are computed and the higher self-consistent resistance is taken (the rule the Blue Book
follows; `bearing_rule = "higher"`). Code: `_web_bearing`, `Checker.F_Rd`, `u_web_bearing`.

### 6.7 Lateral-torsional buckling (LTB), EN 1993-1-1 6.3.2.3

A beam bent about its strong axis can fail by the compression flange moving sideways while the section twists, like a thin ruler
bent on its flat. Lateral restraints (secondary beams, floor) prevent it. The context gives `restraint_ratio = Lcr / L`:

- 0: continuous restraint, LTB cannot occur, no check (`chi_LT = 1`).
- 0 < ratio <= 0.5 (restraints between the supports) or 1 (supports only): LTB is checked on a segment of length `Lcr = ratio x L`.

```
Mcr    = C1 pi^2 E Iz / Lcr^2 * sqrt( Iw/Iz + Lcr^2 G It / (pi^2 E Iz) )       elastic critical moment (load at shear centre)
lambda = sqrt( Wpl fy / Mcr )                                                   slenderness (Wel for class 3)
phi    = 0.5 [ 1 + alpha (lambda - 0.4) + 0.75 lambda^2 ]
chi    = 1 / ( phi + sqrt( phi^2 - 0.75 lambda^2 ) ),   not above 1, not above 1 / lambda^2
f      = 1 - 0.5 (1 - kc) [ 1 - 2 (lambda - 0.8)^2 ],  not above 1;     chi_mod = min(chi / f, 1)
chi = 1 (no LTB) if lambda <= 0.4 or M_Ed / Mcr <= 0.16
Mb,Rd  = chi_mod Wpl fy / gamma_M1                                              u_ltb = M_Ed / Mb,Rd
```

- **Mcr** is the moment at which an ideal, perfectly straight beam buckles (elastic theory, NCCI SN003). **C1** accounts for the
  moment diagram shape: 1.0 for a uniform moment (the conservative case), 1.127 for a UDL between simple supports.
  A load on the top flange lowers Mcr (extra term C2 zg); the program supports that as an option, unvalidated, and it is not used in any result.
- **alpha** is the imperfection factor of the buckling curve, chosen by h/b (UK NA, rolled sections): 0.34 (curve b) if h/b <= 2;
  0.49 (curve c) if 2 < h/b <= 3.1; 0.76 (curve d) if h/b > 3.1.
- **kc = 1 / sqrt(C1)** (0.94 for the UDL case) lifts the resistance a little because the moment is not uniform.
- **Restraint between supports** (0 < ratio <= 0.5): the critical segment does not carry the full UDL moment, so the program uses the
  uniform-moment factors (C1 = 1, kc = 1), which are conservative and equal the C1 = 1.00 row of the Blue Book table. At ratio 1 it
  uses C1 = 1.127 and kc = 0.94. M_Ed is always the largest moment in the span (conservative).

Code: `Checker._ltb_core`, `Checker._ltb`, `M_cr`, `u_ltb`, `Checker.alpha_LT`.

### 6.8 Deflection (serviceability), EN 1993-1-1 7.2

A beam must not sag so much that finishes crack or the floor feels bouncy. For a simply supported beam under a UDL q:

```
delta = 5 q L^4 / (384 E Iy)                    u_deflection = delta / (L / limit ratio)
```

The load q is unfactored (characteristic), in kN/m (which equals N/mm). Three rules are modelled:

| Rule name | Load used | Limit |
|---|---|---|
| `var360` (primary) | variable (live) load only: Qk = live share x w / 1.5 | L / 360 |
| `var200` | variable load only | L / 200 |
| `tot250` | total unfactored load: Qk + Gk + self-weight, with Gk = (1 - live share) x w / 1.35 | L / 250 |

The "live share" is fixed at 27.0 / 56.7675 (the reference case), or taken from the context's own dead and live loads. Code:
`evaluate` (deflection part), `u_deflection`, `deflection`, `deflection_limit`.

## 7. Utilisation, feasibility and the objective

```
feasible  =  every utilisation <= 1 + 1e-9   and   section class <= 3
governing =  the check with the highest utilisation (first one listed if tied)
objective =  the lightest feasible section (mass per metre), found by enumerating the catalogue in mass order
```

Mass order: mass ascending, ties by smaller depth, then catalogue order. The primary set C has 91 sections; the 16 marked "+" in the
Blue Book table are tested as a sensitivity (set C+, 107). A context can also impose a depth cap on h (a design requirement, not a code
check; `feasible_code` ignores it). If no section is feasible the lightest-feasible functions return -1 (abstain).

## 8. Where everything is in the code

| Topic | File and name |
|---|---|
| Read the Blue Book table, verify its SHA-256, order by mass | `src/ub_rl/catalogue.py`: `parse_workbook`, `Catalogue.mass_ordered` |
| All adjustable assumptions (load factors, deflection rule, bearing length, restraint, LTB factors) | `src/ub_rl/config.py`: `CheckerConfig` |
| The seven context parameters, factored load, rule names | `src/ub_rl/context.py`: `Context`, `DEFLECTION_RULES` |
| All the checks above | `src/ub_rl/checker.py`: `Checker`, `evaluate`, `evaluate_context`, `check`, `lightest_feasible_context` |
| Comparison with the Blue Book resistance tables | `src/ub_rl/bluebook.py`, `scripts/gate2_bluebook.py` |
| Second, separately written implementation | `tests/reference_checks.py` |
| Verification cases and the hand-check record | `scripts/gate2_cases.py`, `docs/gate2_cases.md`, `data/gate2/handcheck_values.csv` |

`Checker.evaluate(L, w)` returns arrays with one entry per section: `u_bending`, `u_shear`, `u_shear_buckling`, `u_bending_shear`,
`u_web_bearing`, `u_deflection` and (when restraint is set) `u_ltb`, plus `U` (all utilisations stacked), `feasible`, `section_class`,
`w_Ed`, `M_Ed`, `V_Ed`, `deflection`. `Checker.check(L, w, i)` returns the full record of one section as a `CheckResult`.

## 9. What is verified and what is not

- The checker's section resistances (class, Mc,Rd, Vc,Rd, web bearing, Mb,Rd) agree with the Blue Book tables for all 107 sections within the tables' rounding.
- A second implementation, written separately, agrees on the non-LTB checks; a calculator hand check of 14 cases agrees within 0.28 %.
- Not yet reviewed by a supervising engineer: the formulas against the standard and the assumptions (load factors, deflection limits, bearing length, restraint, LTB curve).
- Not validated: loads on the top flange; per-segment moment diagrams for intermediate restraint (the model is conservative there).
- Not modelled: axial force, torsion, web openings, point loads, connections, fire, vibration, composite action, Class 4 effective sections.

## 10. Sources

EN 1993-1-1:2005+A1:2014 and the UK National Annex; EN 1993-1-5:2006; EN 1990; SCI Blue Book (P363) tables for UBs, S355;
SCI NCCI SN003 (elastic critical moment); SCI Advisory Desk notes AD 368, AD 378, AD 537 (shear buckling and web bearing).
A reproduction of the UK NA buckling-curve table (STAAD.Pro Help, clause 6.3.2.3(1)) was used as a second source; the standard text itself has not been read by the authors.

## 11. Glossary

- **Action**: a load or imposed effect on the structure. **Action effect**: what it causes inside (shear force, bending moment).
- **Characteristic**: the nominal value, before partial factors. **Design value**: after factors.
- **Utilisation**: demand divided by resistance; the program's constraint value.
- **Governing check**: the check with the highest utilisation.
- **Restraint**: something that stops the compression flange moving sideways.
- **Simply supported**: free to rotate at both ends, no moment at the supports.
- **Tributary width**: the width of floor whose load a beam carries.
- **UB**: Universal Beam, a UK hot-rolled I-section (the catalogue unit). **S355**: steel with a nominal yield strength of 355 N/mm2.
- **Yield**: the stress at which steel starts to deform permanently. **Buckling**: sudden sideways or wrinkling failure of a slender part under compression.
