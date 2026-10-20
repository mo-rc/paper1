"""Parse the Blue Book workbook and write the derived catalogue to data/catalogue/ (not tracked).
Usage: python scripts/build_catalogue.py [path-to-xlsx]"""
import csv, json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from ub_rl.catalogue import parse_workbook  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
XLSX = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "raw", "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx")


def main():
    cat, report = parse_workbook(XLSX)
    C = cat.mass_ordered(False)
    cplus = cat.mass_ordered(True)
    rank_c = {n: i for i, n in enumerate(C.names)}
    rank_cp = {n: i for i, n in enumerate(cplus.names)}
    out = os.path.join(ROOT, "data", "catalogue")
    os.makedirs(out, exist_ok=True)
    keys = list(cat.cols)
    with open(os.path.join(out, "ub_catalogue.csv"), "w", newline="") as f:
        wr = csv.writer(f, lineterminator="\n")
        wr.writerow(["name", "series", "plus", "xlsx_row", "index_C", "index_Cplus"] + keys)
        for i, n in enumerate(cat.names):
            wr.writerow([n, cat.series[i], int(cat.plus[i]), int(cat.rows[i]), rank_c.get(n, ""), rank_cp[n]] + [repr(float(cat.cols[k][i])) for k in keys])
    report["units"]["_note"] = "units as in the workbook header row 10"
    with open(os.path.join(out, "ub_catalogue_report.json"), "w") as f:
        json.dump(report, f, indent=1)
    print(f"rows {report['rows']}; '+' rows excluded from C: {report['plus_rows']}; C {report['primary_set_C']}; sha256 ok {report['sha256_ok']}")
    print("units:", {k: v for k, v in report["units"].items() if k != "_note"})
    print("max abs consistency deviations (published values are rounded):", report["consistency_max_abs_deviation"])


if __name__ == "__main__":
    main()
