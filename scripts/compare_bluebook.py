"""Compare the checker with values typed in from the SCI Blue Book (P363) tables (Gate 2).

Usage (repository root):  python scripts/compare_bluebook.py [values.csv] [--tol 0.01] [--workbook path.xlsx]

CSV columns: section, quantity, value, unit, ss_mm, c_mm, Lcr_m, C1, kc, source, notes
Quantities: Mc_Rd (kNm), Vc_Rd (kN), Vb_Rd (kN), F_Rd (kN; needs ss_mm and c_mm), Mb_Rd (kNm; needs Lcr_m and C1, kc optional).
Rows with an empty value are skipped. For Mb_Rd state the moment diagram and load position the table uses (C1) and, if the
table gives it, kc; otherwise kc = 1/sqrt(C1) is assumed (an assumption to confirm). The workbook rounds section properties
to three significant figures, so differences of a few tenths of a percent are expected; the default tolerance is 1 %.
Exit status 1 if any row fails (checker value differs by more than the tolerance in either direction)."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/ (run from the repository root)
import argparse
import csv
import sys
from dataclasses import replace

import numpy as np

from ub_rl.catalogue import parse_workbook
from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig

DEFAULT_WORKBOOK = "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
QUANTITIES = ("Mc_Rd", "Vc_Rd", "Vb_Rd", "F_Rd", "Mb_Rd")


def _f(x):
    x = (x or "").strip()
    return float(x) if x else None


def checker_value(C, base, row, cache):
    """Return (value, note) for one CSV row."""
    name, q = row["section"].strip(), row["quantity"].strip()
    if name not in C.names:
        return None, "section not in catalogue"
    i = C.names.index(name)
    if q == "Mc_Rd":
        return float(base.Mc[i]), ""
    if q == "Vc_Rd":
        return float(base.Vpl[i]), ""
    if q == "Vb_Rd":
        v = float(base.Vbw[i])
        return (v, "") if np.isfinite(v) else (None, "shear buckling does not apply to this section")
    if q == "F_Rd":
        ss, c = _f(row.get("ss_mm")), _f(row.get("c_mm"))
        if ss is None or c is None:
            return None, "ss_mm and c_mm required"
        key = (ss, c)
        if key not in cache:
            cache[key] = (Checker(C, replace(base.cfg, stiff_bearing_ss=ss, bearing_c=c)),
                          Checker(C, replace(base.cfg, stiff_bearing_ss=ss, bearing_c=c, bearing_rule="sequential")))
        hi, seq = cache[key]
        note = f"higher-solution rule (Blue Book/AD 378); sequential rule gives {seq.F_Rd[i]:.1f}" if abs(seq.F_Rd[i] - hi.F_Rd[i]) > 1e-9 else ""
        return float(hi.F_Rd[i]), note
    if q == "Mb_Rd":
        Lcr, C1, kc = _f(row.get("Lcr_m")), _f(row.get("C1")), _f(row.get("kc"))
        if Lcr is None or C1 is None:
            return None, "Lcr_m and C1 required"
        _, _, Mb = base.ltb_resistance([i], Lcr, C1=C1, kc=kc)
        return float(Mb[0]), "" if kc is not None else "kc assumed 1/sqrt(C1)"
    return None, f"unknown quantity {q}"


def compare(rows, C, tol=0.01, base=None):
    base = base or Checker(C)
    cache, out = {}, []
    for k, row in enumerate(rows, start=2):
        table = _f(row.get("value"))
        if table is None:
            continue
        val, note = checker_value(C, base, row, cache)
        if val is None:
            out.append(dict(line=k, section=row["section"], quantity=row["quantity"], table=table, checker=None, diff=None, status="SKIP", note=note))
            continue
        d = val / table - 1.0
        status = "PASS" if abs(d) <= tol else "FAIL"
        out.append(dict(line=k, section=row["section"], quantity=row["quantity"], table=table, checker=val, diff=d, status=status,
                        note=("checker lower (conservative); " if d < 0 else "checker higher; ") + note if status == "FAIL" else note))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="?", default="data/gate2/bluebook_values.csv")
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--workbook", default=DEFAULT_WORKBOOK)
    a = ap.parse_args(argv)
    cat, _ = parse_workbook(a.workbook)
    C = cat.mass_ordered(True)  # include the "+" rows so any Blue Book section can be looked up
    with open(a.csv, newline="") as f:
        rows = list(csv.DictReader(f))
    res = compare(rows, C, a.tol)
    if not res:
        print("no rows with a value to compare")
        return 0
    print(f"{'line':>4} {'section':<14} {'qty':<6} {'table':>10} {'checker':>10} {'diff %':>8}  status  note")
    for r in res:
        cv = "-" if r["checker"] is None else f"{r['checker']:.1f}"
        dd = "-" if r["diff"] is None else f"{100 * r['diff']:+.2f}"
        print(f"{r['line']:>4} {r['section']:<14} {r['quantity']:<6} {r['table']:>10.1f} {cv:>10} {dd:>8}  {r['status']:<6}  {r['note']}")
    fails = [r for r in res if r["status"] == "FAIL"]
    n = sum(r["status"] != "SKIP" for r in res)
    print(f"\n{n - len(fails)} of {n} compared rows within {100 * a.tol:g} %; {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
