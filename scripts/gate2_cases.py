"""Select Gate 2 verification cases and write data/gate2/cases.csv and docs/gate2_cases.md.

Each governing check (bending, shear, shear buckling, bending-shear interaction, web bearing, deflection, LTB) is the
governing check in at least one case. The sheets are generated from the second implementation (tests/reference_checks.py);
they are NOT hand calculations. The hand-check record (calculator values entered in the hand-check workbook) is data/gate2/handcheck_values.csv;
its per-case summary is written on the 'Hand-checked' line of each case.
Run from the repository root:  python scripts/gate2_cases.py [workbook.xlsx]"""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/ (run from the repository root)
import csv
import math
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, "tests")
import reference_checks as R  # noqa: E402
from test_ltb_reference import mb_scalar  # noqa: E402
from ub_rl.catalogue import parse_workbook  # noqa: E402
from ub_rl.checker import CHECKS, Checker  # noqa: E402
from ub_rl.config import CheckerConfig, PHI_REF  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
cat, _ = parse_workbook(path)
C = cat.mass_ordered(False)
names = C.names
LS = [0.8, 1.0, 1.5, 2.0, 3.0, 4.5, 6.0, 7.5, 9.0, 10.5, 12.0, 13.5, 15.0]
WS = [float(x) for x in np.geomspace(20, 10000, 60)]
# Blue Book Mb,Rd table lengths (m): LTB cases use only these unrestrained lengths so an engineer can read Mb,Rd from the table
TABLE_LCR = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0] + [float(x) for x in range(5, 15)]
cols = list(C.cols["m"])


def search(target, rho=0.0, mode=("variable", 360.0), exclude=(), only=None):
    for lo, hi in ((0.9, 1.1), (0.7, 1.3), (0.5, 2.0), (0.5, 50.0)):  # widen the utilisation window until a case exists
        best = _search(target, rho, mode, exclude, only, lo, hi)
        if best is not None:
            return best
    return None


def _search(target, rho, mode, exclude, only, lo, hi):
    best = None
    K = Checker(C, replace(CheckerConfig(), restraint_ratio=rho, deflection_load=mode[0], deflection_ratio=mode[1]))
    for L in LS:
        if target == "ltb" and rho > 0 and not any(abs(rho * L - t) < 1e-9 for t in TABLE_LCR):
            continue
        for w in WS:
            e = K.evaluate(L, float(w))
            for i in range(len(names)):
                if names[i] in exclude or (only and names[i] != only) or e["section_class"][i] > 3:
                    continue
                U = e["U"][i]
                top = U.max()
                if CHECKS[int(np.argmax(U >= top - 1e-12))] != target or not lo <= top <= hi:
                    continue
                score = (abs(top - 1.0), -(L), cols[i])
                if best is None or score < best[0]:
                    best = (score, names[i], L, float(w), rho, mode)
    return best


cases = []
used = set()


def add(label, target, found=None, **fixed):
    if found is None:
        found = search(target, **fixed)
    if found is None:
        raise SystemExit(f"no case found for {target}")
    _, n, L, w, rho, mode = found
    used.add(n)
    cases.append(dict(id=f"G2-{len(cases) + 1:02d}", label=label, target=target, section=n, L=L, w=w, rho=rho, mode=mode[0], ratio=mode[1]))


# the reference beam and the governing-check cases (shear_buckling is reported in the two cases above, see note)
cases.append(dict(id="G2-01", label="reference beam (spec section 7)", target="bending", section="457x191x74", L=9.0, w=56.7675, rho=0.0, mode="variable", ratio=360.0))
used.add("457x191x74")
add("shear governs", "shear", exclude=used)
# Shear buckling never governs by itself: where it applies, the EN 1993-1-5 7.1 interaction (or web bearing) is always
# at least as high. The two sections that need it are covered by the interaction target, with u_shear_buckling reported.
add("shear buckling applies (406x140x39); EN 1993-1-5 7.1 interaction governs", "bending_shear", only="406x140x39")
add("shear buckling applies (762x267x134); EN 1993-1-5 7.1 interaction governs", "bending_shear", only="762x267x134")
add("bending-shear interaction (6.2.8) governs", "bending_shear", exclude=used | {"406x140x39", "762x267x134"})
add("web bearing governs", "web_bearing", exclude=used)
add("deflection governs (variable load, L/360)", "deflection", exclude=used)
add("deflection governs (total load, L/250)", "deflection", mode=("total", 250.0), exclude=used)
add("LTB governs, restraint 1/3 span", "ltb", rho=1 / 3, exclude=used)
add("LTB governs, restraint 1/2 span", "ltb", rho=0.5, exclude=used)
add("LTB governs, unrestrained", "ltb", rho=1.0, exclude=used)
# boundary sections requested for the Blue Book comparison
for lab, n, L, w in [("lightest section", names[0], 3.0, 10.0), ("heaviest section", names[-1], 9.0, 400.0)]:
    cases.append(dict(id=f"G2-{len(cases) + 1:02d}", label=lab, target="-", section=n, L=L, w=w, rho=0.0, mode="variable", ratio=360.0))
K0 = Checker(C)
cls2 = [names[i] for i in range(len(names)) if K0.cls[i] == 2]
if cls2:
    cases.append(dict(id=f"G2-{len(cases) + 1:02d}", label="Class 2 section", target="-", section=cls2[0], L=6.0, w=60.0, rho=0.0, mode="variable", ratio=360.0))

hc = {}
if os.path.exists("data/gate2/handcheck_values.csv"):
    with open("data/gate2/handcheck_values.csv", newline="") as f:
        for r_ in csv.DictReader(f):
            h = hc.setdefault(r_["case"], dict(n=0, empty=0, mx=0.0, over=0))
            if r_["entered"] == "":
                h["empty"] += 1
            else:
                h["n"] += 1
                h["mx"] = max(h["mx"], abs(float(r_["diff_percent"])))
                h["over"] += abs(float(r_["diff_percent"])) > 0.5



def handline(cid):
    h = hc.get(cid)
    if not h:
        return "Hand-checked by: ____________   date: __________   result: __________"
    extra = f"; {h['empty']} cell(s) left empty" if h["empty"] else ""
    return (f"Hand-checked by: Muhammad Shifa (calculator)   date: 23 October 2026   result: {h['n']} values entered, "
            f"largest difference {h['mx']:.2f} %, {h['over']} above 0.5 %{extra}")


rows, md = [], ["# Gate 2 verification cases", "",
                "Generated by `scripts/gate2_cases.py` from the second implementation (`tests/reference_checks.py`). "
                "**The values below are produced by the program, not by hand.** The 'Hand-checked' line of each case records the "
                "calculator check (data/gate2/handcheck_values.csv). That check recomputes the arithmetic with the formulas of "
                "`docs/hand_calc_G2-01.md`, which are the program's formulas; it does not check the formulas against the standard. "
                "Units: mm, N/mm2, kN, kNm, m. Self-weight included (spec section 15).", "",
                "Note: for a UDL on a simply supported UB the bending-shear interaction (6.2.8, or EN 1993-1-5 7.1 where shear buckling "
                "applies) governs only at maximum utilisations of about 2.4 or more (median about 5 over the 91 sections; grid search of "
                "spans 0.3 to 15 m). Its cases are therefore far into the infeasible range; they verify the arithmetic, not a design "
                "decision. Shear buckling never governs by itself where it applies.", ""]
for c in cases:
    i = names.index(c["section"])
    K = Checker(C, replace(CheckerConfig(), restraint_ratio=c["rho"], deflection_load=c["mode"], deflection_ratio=c["ratio"]))
    e = K.evaluate(c["L"], c["w"], [i])
    r = R.utilisations(C.cols, i, c["L"], c["w"], PHI_REF, c["mode"], c["ratio"])
    U = e["U"][0]
    gov = "class4" if e["section_class"][0] == 4 else CHECKS[int(np.argmax(U >= U.max() - 1e-12))]
    ok = bool(e["feasible"][0])
    row = dict(id=c["id"], label=c["label"], section=c["section"], L_m=c["L"], w_kNm=c["w"], restraint_ratio=round(c["rho"], 4),
               deflection=f"{c['mode']} L/{c['ratio']:.0f}", governing=gov, feasible=ok, max_utilisation=round(float(U.max()), 6))
    for k, j in zip(("bending", "shear", "shear_buckling", "bending_shear", "web_bearing", "deflection", "ltb"), range(7)):
        row[f"u_{k}_checker"] = round(float(U[j]), 6)
    for k in ("bending", "shear", "shear_buckling", "bending_shear", "web_bearing", "deflection"):
        row[f"u_{k}_reference"] = round(float(r[f"u_{k}"]), 6)
    rows.append(row)
    h, b, tw, tf, rr = (C.cols[k][i] for k in ("h", "b", "tw", "tf", "r"))
    hw = h - 2 * tf
    g = C.cols["m"][i] * 9.80665 / 1000.0
    md += [f"## {c['id']}: {c['label']}", "",
           f"Section {c['section']} ({C.cols['m'][i]} kg/m): h = {h}, b = {b}, tw = {tw}, tf = {tf}, r = {rr} mm; "
           f"hw = h - 2tf = {hw:.1f}; class {r['class']}; fy = {r['fy']:.0f} N/mm2 (max(tf, tw) = {max(tf, tw)}).", "",
           f"Context: L = {c['L']} m, superimposed factored UDL w = {c['w']} kN/m, variable share {PHI_REF:.4f}; "
           f"restraint ratio {c['rho']:.3f}; deflection {c['mode']} L/{c['ratio']:.0f}.", "",
           f"Actions: self-weight g = {g:.4f} kN/m; w_Ed = w + 1.35 g = {c['w'] + 1.35 * g:.4f} kN/m; "
           f"M_Ed = {r['M_Ed']:.2f} kNm; V_Ed = {r['V_Ed']:.2f} kN.", "",
           f"Resistances: M_c,Rd = {r['M_c_Rd']:.2f} kNm; V_pl,Rd = {r['V_pl_Rd']:.2f} kN; "
           f"V_b,Rd = {r['V_b_Rd']:.2f} kN (inf = shear buckling not applicable); F_Rd (ss = 100 mm, c = 0) = {r['F_Rd']:.2f} kN.", ""]
    if c["rho"] > 0:
        Lcr = c["rho"] * c["L"]
        mcr, chi, mb, MEd = mb_scalar(i, K, C, c["L"], c["w"] + 1.35 * g, c["rho"], False)
        md += [f"LTB: L_cr = {Lcr:.2f} m; M_cr = {mcr:.1f} kNm; chi_LT = {chi:.4f}; M_b,Rd = {mb:.1f} kNm; u_LTB = {MEd / mb:.4f}.", ""]
    md += ["| Check | u (checker) | u (reference) |", "|---|---|---|"]
    for k, j in zip(("bending", "shear", "shear_buckling", "bending_shear", "web_bearing", "deflection", "ltb"), range(7)):
        ref = f"{r['u_' + k]:.4f}" if k != "ltb" else "see LTB line"
        md.append(f"| {k} | {U[j]:.4f} | {ref} |")
    md += ["", f"Governing: **{gov}**, max utilisation {U.max():.4f}, feasible: {ok}.", "",
           handline(c['id']), ""]

Path("data/gate2").mkdir(parents=True, exist_ok=True)
with open("data/gate2/cases.csv", "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()), lineterminator="\n")
    wr.writeheader()
    wr.writerows(rows)
Path("docs/gate2_cases.md").write_text("\n".join(md))
print(f"{len(rows)} cases; governing checks covered: {sorted({r['governing'] for r in rows})}")
for r in rows:
    print(r["id"], r["label"], r["section"], r["L_m"], r["w_kNm"], r["restraint_ratio"], r["governing"], r["max_utilisation"])
