"""Summary of the P7 baseline designs: per set, how often the heuristic and each random-search budget reach the
optimum (gap 0), how often they wrongly abstain, and their mean gap. Reads the design files written by
scripts/run_baselines1.py (default results/baselines1) through the result store, so a file without a valid meta
file stops the script. Contexts where enumeration abstains are left out of every count except `rows`.

    python scripts/baselines1_summary.py [results/baselines1]
"""
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ub_rl.runstore import load_results  # noqa: E402

SETS = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]


def summarise(directory):
    """Lines of the summary table for the design files in `directory`."""
    d = Path(directory)
    out = []
    for s in SETS:
        ref = {r["id"]: r["status"] for r in load_results(d / f"enumeration_{s}.csv")[0]}
        for m in ("heuristic", "random"):
            g = collections.defaultdict(lambda: [0, 0, 0, 0.0, 0])  # rows, exact, false abstain, gap sum, gap count
            for r in load_results(d / f"{m}_{s}.csv")[0]:
                a = g[r["budget"] or "-"]
                a[0] += 1
                if ref[r["id"]] != "feasible":
                    continue
                if r["status"] != "feasible":
                    a[2] += 1
                    continue
                x = float(r["gap_pct"])
                a[1] += x == 0
                a[3] += x
                a[4] += 1
            for k, (n, ex, fa, gs, ng) in sorted(g.items(), key=lambda kv: (kv[0] == "-", int(kv[0]) if kv[0] != "-" else 0)):
                out.append(f"{s:13s} {m:9s} budget {k:>3s}  exact {ex:6d}  false-abstain {fa:6d}  "
                           f"mean gap {gs / max(ng, 1):7.3f}%  (rows {n})")
    return out


if __name__ == "__main__":
    print("\n".join(summarise(sys.argv[1] if len(sys.argv) > 1 else "results/baselines1")))
