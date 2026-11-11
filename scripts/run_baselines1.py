"""P7: run the Stage 1 baselines (enumeration, ordered scan, heuristic iteration, random search) over every
split context and store every design of every method and seed (spec section 12).

Usage, from the repository root:
    python scripts/run_baselines1.py [workbook.xlsx]           full run: all 34,841 contexts of all split files
    python scripts/run_baselines1.py [workbook.xlsx] --limit N  first N contexts per file (smoke run; the
                                                                acceptance assertions then cover that subset)
    --out DIR                                                  write results to DIR instead of results/baselines1

Writes `results/baselines1/<method>_<file>.csv` with a `*_meta.json` each (commit, environment-file SHA-256,
catalogue and split SHA-256, checker config, hardware, single-thread limits), plus `run_summary.json` and its
meta. `results/` is ignored by git; generated results are not committed.

The run asserts the P7 acceptance criteria itself and exits 1 on any failure:
  - enumeration equals ordered scan on every context run;
  - random search at budget |C| equals enumeration on every context run;
  - every output design is rechecked with a fresh checker call (spec section 9 end-to-end: verify, 1 call);
  - every written result file reloads through the store (a result file without its meta file is rejected);
  - the committed split files match `data/splits/SHA256SUMS` before anything is evaluated.

Deterministic except the wall-clock timings and timestamps. No RL is run; the checker is the environment file
until the environments exist (P10). Single-thread: `runstore.limit_threads()` runs before numpy is imported."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/
from ub_rl.runstore import hardware_info, limit_threads, load_results, write_meta, write_results  # noqa: E402

limit_threads()  # before numpy is imported: spec section 10, single CPU thread

import json  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from ub_rl import baselines  # noqa: E402
from ub_rl import splits as S  # noqa: E402
from ub_rl.catalogue import parse_workbook, sha256_file  # noqa: E402
from ub_rl.checker import Checker  # noqa: E402

DEFAULT_WORKBOOK = "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
SPLIT_FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]
METHODS = ("enumeration", "ordered_scan", "heuristic", "random")
ENV_FILE = "src/ub_rl/checker.py"
HASHED_FILES = ["src/ub_rl/checker.py", "src/ub_rl/context.py", "src/ub_rl/config.py", "src/ub_rl/splits.py",
                "src/ub_rl/catalogue.py", "src/ub_rl/baselines.py", "src/ub_rl/runstore.py",
                "scripts/run_baselines1.py"]
COLUMNS = ["id", "set", "method", "seed", "budget", "status", "section_index", "section_name", "mass_kg_m",
           "gap_pct", "calls", "verification_calls", "wall_seconds", "verified"]


def git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip())
    except Exception:
        commit, dirty = "unknown", None
    return commit, dirty


def check_split_manifest():
    lines = Path("data/splits/SHA256SUMS").read_text(encoding="ascii").strip().splitlines()
    manifest = {name: h for h, name in (line.split("  ") for line in lines)}
    bad = [name for name in SPLIT_FILES if sha256_file(Path("data/splits") / f"{name}.csv") != manifest[f"{name}.csv"]]
    if bad:
        raise SystemExit(f"split files do not match data/splits/SHA256SUMS: {bad}")
    return manifest


def row_of(kc, r, method, seed, budget, res, calls_verify, wall, mref, verified):
    mass = "" if res.index < 0 else f"{float(kc.mass[res.index]):.1f}"
    gap = ""
    if res.index >= 0:
        gap = 0.0 if mref is None or res.index == mref else 100.0 * (kc.mass[res.index] / kc.mass[mref] - 1.0)
        gap = f"{gap:.6f}"
    return {
        "id": r["id"], "set": r["set"], "method": method, "seed": seed, "budget": budget, "status": res.status,
        "section_index": res.index, "section_name": "" if res.index < 0 else kc.cat.names[res.index],
        "mass_kg_m": mass, "gap_pct": gap, "calls": res.calls, "verification_calls": calls_verify,
        "wall_seconds": f"{wall:.6f}", "verified": verified,
    }


def run_method(kc, ctx, fn):
    """Run fn, recheck its output design with a fresh checker call (1 verification call when a design is
    output, 0 on abstain), and time the whole per-design pipeline."""
    t = time.perf_counter()
    res = fn(kc, ctx)
    if res.index >= 0:
        ok = bool(kc.evaluate_context(ctx, [res.index])["feasible"][0])
        if ok != (res.status == "feasible"):
            raise RuntimeError(f"recheck failed: {res}")
    wall = time.perf_counter() - t
    return res, wall, (1 if res.index >= 0 else 0), ("" if res.index < 0 else 1)


def base_meta(method, split_name, n, commit, dirty, hashes, started, catalogue_sha, hardware, threads, limit,
              n_feasible, n_abstain, enum_equals_scan, elapsed, kc):
    if split_name is None:  # run summary: the split reference is the whole manifest
        split_file, split_sha = "data/splits/SHA256SUMS (all split files)", sha256_file("data/splits/SHA256SUMS")
    else:
        split_file, split_sha = f"data/splits/{split_name}.csv", sha256_file(Path("data/splits") / f"{split_name}.csv")
    return {
        "status": "complete",
        "method": method,
        "script": "scripts/run_baselines1.py",
        "commit": commit, "working_tree_dirty": dirty,
        "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE], "file_sha256": hashes,
        "catalogue_sha256": catalogue_sha, "catalogue_set": "C", "catalogue_rows": len(kc),
        "catalogue_order": "mass ascending, ties by smaller depth, then catalogue order (spec section 9)",
        "split_file": split_file,
        "split_sha256": split_sha,
        "n_contexts": n, "n_feasible": n_feasible, "n_abstain": n_abstain,
        "checker_config": kc.cfg.as_dict(),
        "python": platform.python_version(), "numpy": np.__version__,
        "hardware": hardware, "threads_limited_to": threads,
        "limit": limit, "enum_equals_ordered_scan": enum_equals_scan,
        "started_utc": started, "elapsed_seconds": elapsed,
        "n_checker_invocations": kc.invocations, "n_section_evaluations": kc.sections,
    }


def main():
    argv, args = sys.argv[1:], []
    for i, a in enumerate(argv):
        if a.startswith("--"):
            if a in ("--limit", "--out") and i + 1 >= len(argv):
                raise SystemExit(f"{a} needs a value")
            continue
        if argv[i - 1] in ("--limit", "--out"):
            continue
        args.append(a)
    workbook = args[0] if args else DEFAULT_WORKBOOK
    limit = None
    if "--limit" in argv:
        limit = int(argv[argv.index("--limit") + 1])
        if limit < 1:
            raise SystemExit("--limit must be at least 1")

    check_split_manifest()
    cat, _ = parse_workbook(workbook)
    C = cat.mass_ordered(False)
    kc = baselines.CountingChecker(Checker(C))
    n = len(kc)
    commit, dirty = git_info()
    started = datetime.now(timezone.utc).isoformat()
    hashes = {p: sha256_file(p) for p in HASHED_FILES}
    hardware = hardware_info()
    threads = {v: os.environ.get(v) for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}
    if "--out" in argv:
        if argv.index("--out") + 1 >= len(argv):
            raise SystemExit("--out needs a value")
        outdir = Path(argv[argv.index("--out") + 1])
    else:
        outdir = Path("results/baselines1")
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()

    summary_files = []
    expected_rows = {}  # file -> method -> number of rows, and the context count per file (store self-check)
    expected_ctxs = {}
    for split_name in SPLIT_FILES:
        rows, ctxs = S.load_split(split_name)
        if limit is not None:
            rows, ctxs = rows[:limit], ctxs[:limit]
        expected_ctxs[split_name] = len(rows)
        out = []
        for r, ctx in zip(rows, ctxs):
            res_enum, wall_enum, vc_enum, ver_enum = run_method(kc, ctx, baselines.enumerate)
            res_scan, wall_scan, vc_scan, ver_scan = run_method(kc, ctx, baselines.ordered_scan)
            res_heur, wall_heur, vc_heur, ver_heur = run_method(kc, ctx, baselines.heuristic)
            if (res_enum.status, res_enum.index) != (res_scan.status, res_scan.index):
                raise SystemExit(f"enumeration != ordered scan on context {r['id']}: {res_enum} vs {res_scan}")
            mref = res_enum.index
            out.append(row_of(kc, r, "enumeration", "", "", res_enum, vc_enum, wall_enum, mref, ver_enum))
            out.append(row_of(kc, r, "ordered_scan", "", "", res_scan, vc_scan, wall_scan, mref, ver_scan))
            out.append(row_of(kc, r, "heuristic", "", "", res_heur, vc_heur, wall_heur, mref, ver_heur))
            # random search: seeds 0-9, budgets 10/20/50. Budget |C| samples every section without replacement,
            # so it equals enumeration for every seed: evaluated once per context and stored under all seeds
            # (recorded in the meta, not assumed silently).
            for budget in baselines.RANDOM_BUDGETS[:-1]:
                for seed in baselines.RANDOM_SEEDS:
                    rng = np.random.default_rng(seed)  # fresh per context: deterministic, order-independent
                    fn = lambda k, c, b=budget, g=rng: baselines.random_search(k, c, b, g)
                    res, wall, vc, ver = run_method(kc, ctx, fn)
                    out.append(row_of(kc, r, "random", str(seed), str(budget), res, vc, wall, mref, ver))
            rng = np.random.default_rng(0)  # any seed: the full permutation covers every section
            res, wall, vc, ver = run_method(kc, ctx, lambda k, c, b=n, g=rng: baselines.random_search(k, c, b, g))
            if (res.status, res.index) != (res_enum.status, res_enum.index):
                raise SystemExit(f"random search budget |C| != enumeration on context {r['id']}")
            for seed in baselines.RANDOM_SEEDS:
                out.append(row_of(kc, r, "random", str(seed), str(n), res, vc, wall, mref, ver))

        feas = sum(1 for x in out if x["method"] == "enumeration" and x["status"] == "feasible")
        per_file = {"file": split_name, "n": len(rows), "n_feasible": feas, "n_abstain": len(rows) - feas,
                    "enum_equals_ordered_scan": True,
                    "mean_calls": {m: round(float(np.mean([int(x["calls"]) for x in out if x["method"] == m])), 3)
                                   for m in METHODS}}
        summary_files.append(per_file)
        for method in METHODS:
            mrows = [x for x in out if x["method"] == method]
            expected_rows.setdefault(split_name, {})[method] = len(mrows)
            meta = base_meta(method, split_name, len(rows), commit, dirty, hashes, started, sha256_file(workbook),
                             hardware, threads, limit, feas, len(rows) - feas, True, time.perf_counter() - t0, kc)
            if method == "random":
                meta["seeds"] = list(baselines.RANDOM_SEEDS)
                meta["budgets"] = list(baselines.RANDOM_BUDGETS)
                meta["random_budget_C_note"] = ("budget |C| samples every section without replacement, so the "
                                                "stored rows are seed-independent (evaluated once per context)")
            write_results(outdir / f"{method}_{split_name}.csv", mrows, COLUMNS, meta)
        print(f"{split_name}: {len(rows)} contexts, {feas} feasible, {len(rows) - feas} abstain; mean calls: "
              f"enum {per_file['mean_calls']['enumeration']}, scan {per_file['mean_calls']['ordered_scan']}, "
              f"heuristic {per_file['mean_calls']['heuristic']}, random {per_file['mean_calls']['random']}")

    # store self-check: every written file must reload through the store (spec section 12: a result file
    # without its meta file is rejected); the meta must report the same context count as the file holds
    for split_name in SPLIT_FILES:
        for method in METHODS:
            rows_loaded, meta_loaded = load_results(outdir / f"{method}_{split_name}.csv")
            assert meta_loaded["status"] == "complete"
            assert len(rows_loaded) == expected_rows[split_name][method]
            assert int(meta_loaded["n_contexts"]) == expected_ctxs[split_name]

    summary = {
        "script": "scripts/run_baselines1.py", "commit": commit, "working_tree_dirty": dirty,
        "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE],
        "catalogue_sha256": sha256_file(workbook), "catalogue_set": "C", "catalogue_rows": n,
        "limit": limit, "files": summary_files,
        "n_contexts_total": sum(f["n"] for f in summary_files),
        "enum_equals_ordered_scan_overall": all(f["enum_equals_ordered_scan"] for f in summary_files),
        "started_utc": started, "elapsed_seconds": time.perf_counter() - t0,
        "python": platform.python_version(), "numpy": np.__version__, "hardware": hardware,
        "random_seeds": list(baselines.RANDOM_SEEDS), "random_budgets": list(baselines.RANDOM_BUDGETS),
        "random_budget_C_note": "budget |C| samples every section without replacement and equals enumeration",
    }
    sfile = outdir / "run_summary.json"
    sfile.write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii", newline="\n")
    write_meta(sfile, base_meta("summary", None, summary["n_contexts_total"], commit, dirty, hashes,
                                started, sha256_file(workbook), hardware, threads, limit,
                                sum(f["n_feasible"] for f in summary_files),
                                sum(f["n_abstain"] for f in summary_files),
                                summary["enum_equals_ordered_scan_overall"], time.perf_counter() - t0, kc))
    print(f"total contexts: {summary['n_contexts_total']}; enumeration == ordered scan on every context: "
          f"{summary['enum_equals_ordered_scan_overall']}; wrote {len(METHODS) * len(SPLIT_FILES)} result files "
          f"+ metas + run_summary.json to {outdir}/")


if __name__ == "__main__":
    main()
