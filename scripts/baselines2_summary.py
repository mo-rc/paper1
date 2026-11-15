"""Summary of the P8 baseline designs: per set, how often the GA (budgets 20 and |C|) and the MLP reach the
optimum (gap 0), how often they wrongly abstain, and their mean gap. Reads the files written by
scripts/run_baselines2.py (default results/baselines2) through the result store, so a file without a valid
meta file stops the script. Contexts where enumeration abstains are left out of every count except `rows`
(the P7 summary convention). The GA budget-91 result equals enumeration by construction and is a cost data
point, not a GA-quality result (recorded in run_summary.json).

    python scripts/baselines2_summary.py [results/baselines2]
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ub_rl.runstore import load_results  # noqa: E402

SETS = ["test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "reference"]
GA_SETS = SETS                                    # A5: the GA runs on T1-T5 and the reference
MLP_SETS = SETS[:-1]                              # A5: the MLP runs on T1-T5 only (literal reading)


def summarise(directory):
    """Lines of the summary table for the design files in `directory`."""
    d = Path(directory)
    out = []
    for s in SETS:
        ref = {r["id"]: r["status"] for r in load_results(d / f"ref_{s}.csv")[0]}
        methods = []
        if s in GA_SETS:
            methods.append(("ga", ["20", "91"]))
        if s in MLP_SETS:
            methods.append(("mlp", ["-"]))  # the MLP performs no search, so it has no budget column
        for m, budgets in methods:
            g = collections.defaultdict(lambda: [0, 0, 0, 0.0, 0])  # rows, exact, false abstain, gap sum, count
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
            for k in budgets:
                n, ex, fa, gs, ng = g[k]
                out.append(f"{s:13s} {m:5s} budget {k:>3s}  exact {ex:6d}  false-abstain {fa:6d}  "
                           f"mean gap {gs / max(ng, 1):7.3f}%  (rows {n})")
    return out


if __name__ == "__main__":
    print("\n".join(summarise(sys.argv[1] if len(sys.argv) > 1 else "results/baselines2")))
