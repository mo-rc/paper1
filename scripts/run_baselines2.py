"""P8: run the trimmed Stage 1 baselines II - the categorical-native GA and the supervised MLP variant (i)
(spec section 9 as trimmed by Amendment A5; plan docs/p8_plan.md). No RL.

Usage, from the repository root:
    python scripts/run_baselines2.py [workbook.xlsx]           full run: GA tuning on V (12 configurations,
                                                               budgets 20 and |C|, seeds 0-2), GA on T1-T5 and
                                                               the reference (seeds 0-9, budgets 20 and |C|),
                                                               MLP trained on the 2,197 enumeration labels,
                                                               MLP tuning on V, MLP on T1-T5 (seeds 0-9)
    python scripts/run_baselines2.py [workbook.xlsx] --limit N first N contexts per file (sample run; the
                                                               acceptance assertions then cover that subset)
    --out DIR                                                  write results to DIR instead of
                                                               results/baselines2 and skip the committed
                                                               snapshot

Writes `results/baselines2/`: `ref_<file>.csv` (the enumeration reference per context), `ga_tune.csv` +
`ga_tuning_selection.json`, `ga_<file>.csv`, `mlp_labels.json`, `mlp_tune.csv` + `mlp_tuning_selection.json`,
`mlp_<file>.csv`, each with a `*_meta.json`, plus `run_summary.json` and its meta. `results/` is ignored by
git; generated results are not committed. Unless --out is given, the committed snapshot
`paper/tables/baselines2_run_output.txt` (printed summary, SHA-256 of the result files, run commit) is
written, as P7's baselines1_run_output.txt.

The run asserts the P8 acceptance criteria itself and exits 1 on any failure:
  - the GA at budget |C| equals the enumeration optimum on every context run (a cost data point, not a
    GA-quality result - recorded in the summary);
  - every output design is rechecked with a fresh checker call (spec section 9 end-to-end);
  - every written result file reloads through the store (a result file without its meta file is rejected);
  - the committed split files match `data/splits/SHA256SUMS` before anything is evaluated.

Tuning (Amendment A5): the first drawn configuration is the default; a later configuration replaces the
current best only if the V mean gap improves by at least 0.5 percentage points with feasibility not lower,
applied in draw order; the rule and the scores are recorded in the selection metas and the summary. The GA
tuning calls (its evaluation calls) and the MLP tuning calls (verification + repair on V) are added to each
method's cost in the summary.

Deterministic except wall-clock timings and timestamps. Single-thread: `runstore.limit_threads()` runs before
numpy and torch are imported."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/
from ub_rl.runstore import hardware_info, limit_threads, load_results, write_meta, write_results  # noqa: E402

limit_threads()  # before numpy and torch are imported: spec section 10, single CPU thread

import json  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
from dataclasses import asdict  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

import baselines2_summary  # noqa: E402  (same directory: prints the committed-snapshot table)
from ub_rl import baselines, baselines2, mlp_baseline, splits as S  # noqa: E402
from ub_rl.catalogue import parse_workbook, sha256_file  # noqa: E402
from ub_rl.checker import Checker  # noqa: E402

DEFAULT_WORKBOOK = "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
GA_FILES = ["test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "reference"]  # A5: GA on T1-T5 + reference
MLP_FILES = ["test_t1", "test_t2", "test_t3", "test_t4", "test_t5"]               # A5: MLP on T1-T5 (literal)
TUNE_FILE = "val"                                                                 # A5: tuning on V only
ENV_FILE = "src/ub_rl/checker.py"
HASHED_FILES = ["src/ub_rl/checker.py", "src/ub_rl/context.py", "src/ub_rl/config.py", "src/ub_rl/splits.py",
                "src/ub_rl/catalogue.py", "src/ub_rl/baselines.py", "src/ub_rl/runstore.py",
                "src/ub_rl/baselines2.py", "src/ub_rl/mlp_baseline.py", "scripts/run_baselines2.py"]
COLUMNS = ["id", "set", "method", "seed", "budget", "config", "status", "section_index", "section_name",
           "mass_kg_m", "gap_pct", "calls", "verification_calls", "wall_seconds", "verified"]
REF_COLUMNS = ["id", "set", "status", "section_index", "section_name", "mass_kg_m"]
SNAPSHOT_PATH = Path("paper/tables/baselines2_run_output.txt")


def git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                                             text=True).strip())
    except Exception:
        commit, dirty = "unknown", None
    return commit, dirty


def check_split_manifest():
    lines = Path("data/splits/SHA256SUMS").read_text(encoding="ascii").strip().splitlines()
    manifest = {name: h for h, name in (line.split("  ") for line in lines)}
    files = ["train", TUNE_FILE] + GA_FILES
    bad = [name for name in files if sha256_file(Path("data/splits") / f"{name}.csv") != manifest[f"{name}.csv"]]
    if bad:
        raise SystemExit(f"split files do not match data/splits/SHA256SUMS: {bad}")
    return manifest


def row_of(kc, r, method, seed, budget, config, res, calls_verify, wall, mref, verified):
    mass = "" if res.index < 0 else f"{float(kc.mass[res.index]):.1f}"
    gap = ""
    if res.index >= 0 and mref >= 0:
        gap = 0.0 if res.index == mref else 100.0 * (kc.mass[res.index] / kc.mass[mref] - 1.0)
        gap = f"{gap:.6f}"
    return {
        "id": r["id"], "set": r["set"], "method": method, "seed": seed, "budget": budget, "config": config,
        "status": res.status, "section_index": res.index,
        "section_name": "" if res.index < 0 else kc.cat.names[res.index], "mass_kg_m": mass, "gap_pct": gap,
        "calls": res.calls, "verification_calls": calls_verify, "wall_seconds": f"{wall:.6f}", "verified": verified,
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
              n_feasible, n_abstain, elapsed, kc):
    if split_name is None:  # run summary: the split reference is the whole manifest
        split_file, split_sha = "data/splits/SHA256SUMS (all split files)", sha256_file("data/splits/SHA256SUMS")
    else:
        split_file, split_sha = f"data/splits/{split_name}.csv", sha256_file(Path("data/splits") / f"{split_name}.csv")
    return {
        "status": "complete",
        "method": method,
        "script": "scripts/run_baselines2.py",
        "commit": commit, "working_tree_dirty": dirty,
        "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE], "file_sha256": hashes,
        "catalogue_sha256": catalogue_sha, "catalogue_set": "C", "catalogue_rows": len(kc),
        "catalogue_order": "mass ascending, ties by smaller depth, then catalogue order (spec section 9)",
        "split_file": split_file, "split_sha256": split_sha,
        "n_contexts": n, "n_feasible": n_feasible, "n_abstain": n_abstain,
        "checker_config": kc.cfg.as_dict(),
        "python": platform.python_version(), "numpy": np.__version__,
        "hardware": hardware, "threads_limited_to": threads,
        "limit": limit, "started_utc": started, "elapsed_seconds": elapsed,
        "n_checker_invocations": kc.invocations, "n_section_evaluations": kc.sections,
    }


def score_of(rows, config_id):
    """(mean gap, feasibility share) of one configuration over its V rows. Gap = inf when it outputs no
    design; gap is the mean over rows with a feasible output (Amendment A5 reading, recorded)."""
    mine = [r for r in rows if str(r["config"]) == str(config_id)]
    feas = [float(r["gap_pct"]) for r in mine if r["status"] == "feasible"]
    return (float("inf") if not feas else float(np.mean(feas)), len(feas) / max(len(mine), 1))


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
        outdir = Path(argv[argv.index("--out") + 1])
    else:
        outdir = Path("results/baselines2")
    outdir.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    catalogue_sha = sha256_file(workbook)

    # ------------------------------------------------ enumeration references (gap denominators)
    refs = {}    # file -> list of (row dict, context, MethodResult)
    ref_out = {}  # file -> stored reference rows
    for fname in [TUNE_FILE] + GA_FILES:
        rows, ctxs = S.load_split(fname)
        if limit is not None:
            rows, ctxs = rows[:limit], ctxs[:limit]
        stored, out = [], []
        for r, ctx in zip(rows, ctxs):
            res, _, _, _ = run_method(kc, ctx, baselines.enumerate)
            stored.append((r, ctx, res))
            out.append({"id": r["id"], "set": r["set"], "status": res.status, "section_index": res.index,
                        "section_name": "" if res.index < 0 else kc.cat.names[res.index],
                        "mass_kg_m": "" if res.index < 0 else f"{float(kc.mass[res.index]):.1f}"})
        refs[fname] = stored
        ref_out[fname] = out
        n_feas = sum(1 for x in out if x["status"] == "feasible")
        meta = base_meta("ref", fname, len(rows), commit, dirty, hashes, started, catalogue_sha, hardware,
                         threads, limit, n_feas, len(rows) - n_feas, time.perf_counter() - t0, kc)
        write_results(outdir / f"ref_{fname}.csv", out, REF_COLUMNS, meta)

    # ------------------------------------------------ GA tuning on V (Amendment A5)
    ga_configs = baselines2.draw_ga_configs()
    ga_tune_rows = []
    for cfg in ga_configs:
        for budget in baselines2.GA_BUDGETS:
            for seed in baselines2.GA_TUNE_SEEDS:
                for r, ctx, ref in refs[TUNE_FILE]:
                    fn = (lambda k, c, b=budget, sd=seed, cid=r["id"], cf=cfg:
                          baselines2.ga(k, c, b, sd, cid, cf))
                    res, wall, vc, ver = run_method(kc, ctx, fn)
                    ga_tune_rows.append(row_of(kc, r, "ga", str(seed), str(budget), str(cfg.id), res, vc, wall,
                                               ref.index, ver))
    ga_scores = [score_of(ga_tune_rows, cfg.id) for cfg in ga_configs]
    ga_selected = baselines2.select_config(ga_scores)
    ga_tune_calls = sum(int(r["calls"]) for r in ga_tune_rows)
    n_val = len(refs[TUNE_FILE])
    meta = base_meta("ga_tune", TUNE_FILE, n_val, commit, dirty, hashes, started, catalogue_sha, hardware,
                     threads, limit, sum(1 for r in ga_tune_rows if r["status"] == "feasible"),
                     sum(1 for r in ga_tune_rows if r["status"] != "feasible"), time.perf_counter() - t0, kc)
    meta.update({"seeds": list(baselines2.GA_TUNE_SEEDS), "budgets": list(baselines2.GA_BUDGETS),
                 "configs": [asdict(c) for c in ga_configs], "tuning_rule": baselines2.TUNING_RULE,
                 "tuning_calls_ga_evals": ga_tune_calls})
    write_results(outdir / "ga_tune.csv", ga_tune_rows, COLUMNS, meta)
    sel = {"rule": baselines2.TUNING_RULE,
           "gap_reading": "gap is the mean over rows with a feasible output; a configuration that outputs no "
                          "design on V has gap = infinity; feasibility is the share of (budget, seed, context) "
                          "rows with a feasible output (both budgets pooled, draw order)",
           "scores": [{"config": asdict(cfg), "mean_gap_pct": (None if g == float("inf") else round(g, 6)),
                       "feasibility": round(f, 6)} for cfg, (g, f) in zip(ga_configs, ga_scores)],
           "selected_config": asdict(ga_configs[ga_selected]), "tuning_calls_ga_evals": ga_tune_calls,
           "n_contexts_V": n_val}
    sel_file = outdir / "ga_tuning_selection.json"
    sel_file.write_text(json.dumps(sel, indent=2) + "\n", encoding="ascii", newline="\n")
    write_meta(sel_file, {**base_meta("ga_tuning_selection", TUNE_FILE, n_val, commit, dirty, hashes, started,
                                      catalogue_sha, hardware, threads, limit, 0, 0,
                                      time.perf_counter() - t0, kc), "tuning_rule": baselines2.TUNING_RULE})
    print(f"GA tuning: {len(ga_tune_rows)} rows on V; selected configuration {ga_selected} "
          f"{asdict(ga_configs[ga_selected])}")

    # ------------------------------------------------ GA on T1-T5 + reference (seeds 0-9, budgets 20 and |C|)
    ga_cfg = ga_configs[ga_selected]
    ga_per_file = {}
    for fname in GA_FILES:
        out = []
        for r, ctx, ref in refs[fname]:
            for budget in baselines2.GA_BUDGETS:
                for seed in baselines2.GA_SEEDS:
                    fn = (lambda k, c, b=budget, sd=seed, cid=r["id"], cf=ga_cfg:
                          baselines2.ga(k, c, b, sd, cid, cf))
                    res, wall, vc, ver = run_method(kc, ctx, fn)
                    if budget == n and (res.status, res.index) != (ref.status, ref.index):
                        raise SystemExit(f"GA budget |C| != enumeration on context {r['id']}: {res} vs {ref}")
                    out.append(row_of(kc, r, "ga", str(seed), str(budget), str(ga_cfg.id), res, vc, wall,
                                      ref.index, ver))
        n_ctx = len(refs[fname])
        n_feas_ref = sum(1 for _, _, ref in refs[fname] if ref.status == "feasible")
        meta = base_meta("ga", fname, n_ctx, commit, dirty, hashes, started, catalogue_sha, hardware, threads,
                         limit, n_feas_ref, n_ctx - n_feas_ref, time.perf_counter() - t0, kc)
        meta.update({"seeds": list(baselines2.GA_SEEDS), "budgets": list(baselines2.GA_BUDGETS),
                     "config": asdict(ga_cfg), "tuning_rule": baselines2.TUNING_RULE,
                     "ga_fitness_note": ("feasible sections by mass (lightest best); infeasible sections below "
                                         "every feasible one by utilisation overrun max(0, U_max - 1), least "
                                         "first, then mass"),
                     "ga_budget_C_note": ("budget |C| evaluates every section (the duplicate rule redraws from "
                                          "unseen sections), so it equals the enumeration optimum on every "
                                          "context; the budget-91 result is a cost data point, not a "
                                          "GA-quality result")})
        write_results(outdir / f"ga_{fname}.csv", out, COLUMNS, meta)
        ga_per_file[fname] = _stats(refs[fname], out, ga_cfg.id)
        print(f"ga_{fname}: {len(out)} rows (config {ga_cfg.id})")

    # ------------------------------------------------ MLP labels (spec section 9 variant (i))
    train_rows, train_ctxs = S.load_split("train")
    if limit is not None:
        train_rows, train_ctxs = train_rows[:limit], train_ctxs[:limit]
    needed = limit if limit is not None else mlp_baseline.N_LABELS
    labels, label_ids, skipped = [], [], 0
    for r, ctx in zip(train_rows, train_ctxs):
        if len(labels) == needed:
            break
        ref, _, _, _ = run_method(kc, ctx, baselines.enumerate)
        if ref.index >= 0:
            labels.append((ctx, ref.index))
            label_ids.append(r["id"])
        else:
            skipped += 1  # no feasible section on this context: skipped in file order (decided, recorded)
    n_labels = len(labels)
    label_cost_full = n_labels * n
    label_cost_scan = sum(opt + 1 for _, opt in labels)
    labels_json = {"n_labels": n_labels, "context_ids": label_ids, "labels": [opt for _, opt in labels],
                   "n_skipped_no_feasible_ref": skipped,
                   "label_note": "the first rows of train.csv in file order that have a feasible enumeration "
                                 "optimum (rows whose context has no feasible section are skipped)",
                   "cost_full_enumeration_calls": label_cost_full,
                   "cost_ordered_scan_calls": label_cost_scan,
                   "cost_note": "full enumeration = n_labels * |C|; ordered scan with certificate = sum of "
                                "(optimum rank + 1) per label (spec section 9)"}
    lab_file = outdir / "mlp_labels.json"
    lab_file.write_text(json.dumps(labels_json, indent=2) + "\n", encoding="ascii", newline="\n")
    write_meta(lab_file, {**base_meta("mlp_labels", "train", n_labels, commit, dirty, hashes, started,
                                      catalogue_sha, hardware, threads, limit, n_labels, skipped,
                                      time.perf_counter() - t0, kc), "n_labels": n_labels})
    print(f"MLP labels: {n_labels} labels, {skipped} train rows skipped (no feasible section); "
          f"costings {label_cost_full} / {label_cost_scan} calls")

    # ------------------------------------------------ MLP tuning on V (Amendment A5)
    import torch  # imported here so limit_threads() already ran; mlp_baseline imported it anyway
    mlp_configs = mlp_baseline.draw_mlp_configs()
    mlp_tune_rows = []
    for cfg in mlp_configs:
        model, mean, std = mlp_baseline.train_mlp(labels, cfg, 0, n)
        for r, ctx, ref in refs[TUNE_FILE]:
            pred = mlp_baseline.predict(model, mean, std, ctx)
            fn = lambda k, c, p=pred: mlp_baseline.evaluate_mlp(k, c, p)
            res, wall, vc, ver = run_method(kc, ctx, fn)
            mlp_tune_rows.append(row_of(kc, r, "mlp", "0", "", str(cfg.id), res, vc, wall, ref.index, ver))
    mlp_scores = [score_of(mlp_tune_rows, cfg.id) for cfg in mlp_configs]
    mlp_selected = baselines2.select_config(mlp_scores)
    mlp_tune_calls = sum(int(r["verification_calls"]) + int(r["calls"]) for r in mlp_tune_rows)
    meta = base_meta("mlp_tune", TUNE_FILE, n_val, commit, dirty, hashes, started, catalogue_sha, hardware,
                     threads, limit, sum(1 for r in mlp_tune_rows if r["status"] == "feasible"),
                     sum(1 for r in mlp_tune_rows if r["status"] != "feasible"), time.perf_counter() - t0, kc)
    meta.update({"configs": [asdict(c) for c in mlp_configs], "tuning_rule": baselines2.TUNING_RULE,
                 "train_seed": 0, "n_labels": n_labels,
                 "tuning_calls_note": "training costs 0 checker calls (labels already costed); the tuning calls "
                                      "are the V verification + repair calls, added to the classifier's cost",
                 "tuning_calls_verification_and_repair": mlp_tune_calls})
    write_results(outdir / "mlp_tune.csv", mlp_tune_rows, COLUMNS, meta)
    sel = {"rule": baselines2.TUNING_RULE,
           "gap_reading": "gap is the mean over rows with a feasible output; a configuration that outputs no "
                          "design on V has gap = infinity; feasibility is the share of V contexts with a "
                          "feasible output (draw order)",
           "scores": [{"config": asdict(cfg), "mean_gap_pct": (None if g == float("inf") else round(g, 6)),
                       "feasibility": round(f, 6)} for cfg, (g, f) in zip(mlp_configs, mlp_scores)],
           "selected_config": asdict(mlp_configs[mlp_selected]), "train_seed": 0, "n_labels": n_labels,
           "tuning_calls_verification_and_repair": mlp_tune_calls, "n_contexts_V": n_val}
    sel_file = outdir / "mlp_tuning_selection.json"
    sel_file.write_text(json.dumps(sel, indent=2) + "\n", encoding="ascii", newline="\n")
    write_meta(sel_file, {**base_meta("mlp_tuning_selection", TUNE_FILE, n_val, commit, dirty, hashes, started,
                                      catalogue_sha, hardware, threads, limit, 0, 0,
                                      time.perf_counter() - t0, kc), "tuning_rule": baselines2.TUNING_RULE})
    print(f"MLP tuning: {len(mlp_tune_rows)} rows on V; selected configuration {mlp_selected} "
          f"{asdict(mlp_configs[mlp_selected])}")

    # ------------------------------------------------ MLP on T1-T5 (seeds 0-9)
    mlp_cfg = mlp_configs[mlp_selected]
    mlp_per_file = {}
    for fname in MLP_FILES:
        out = []
        for seed in baselines2.GA_SEEDS:
            model, mean, std = mlp_baseline.train_mlp(labels, mlp_cfg, seed, n)
            for r, ctx, ref in refs[fname]:
                pred = mlp_baseline.predict(model, mean, std, ctx)
                fn = lambda k, c, p=pred: mlp_baseline.evaluate_mlp(k, c, p)
                res, wall, vc, ver = run_method(kc, ctx, fn)
                out.append(row_of(kc, r, "mlp", str(seed), "", str(mlp_cfg.id), res, vc, wall, ref.index, ver))
        n_ctx = len(refs[fname])
        n_feas_ref = sum(1 for _, _, ref in refs[fname] if ref.status == "feasible")
        meta = base_meta("mlp", fname, n_ctx, commit, dirty, hashes, started, catalogue_sha, hardware, threads,
                         limit, n_feas_ref, n_ctx - n_feas_ref, time.perf_counter() - t0, kc)
        meta.update({"seeds": list(baselines2.GA_SEEDS), "config": asdict(mlp_cfg),
                     "tuning_rule": baselines2.TUNING_RULE, "n_labels": n_labels,
                     "search_calls_note": "the classifier performs no search: the calls column is 0 and the "
                                          "verification_calls column holds the end-to-end verify + repair calls"})
        write_results(outdir / f"mlp_{fname}.csv", out, COLUMNS, meta)
        mlp_per_file[fname] = _stats(refs[fname], out, mlp_cfg.id)
        print(f"mlp_{fname}: {len(out)} rows (config {mlp_cfg.id})")

    # ------------------------------------------------ store self-check (P7 convention)
    expected = {f"ref_{f}": len(refs[f]) for f in [TUNE_FILE] + GA_FILES}
    expected["ga_tune"] = len(ga_tune_rows)
    expected.update({f"ga_{f}": len(refs[f]) * len(baselines2.GA_SEEDS) * len(baselines2.GA_BUDGETS)
                     for f in GA_FILES})
    expected["mlp_tune"] = len(mlp_tune_rows)
    expected.update({f"mlp_{f}": len(refs[f]) * len(baselines2.GA_SEEDS) for f in MLP_FILES})
    for name, n_rows in expected.items():
        rows_loaded, meta_loaded = load_results(outdir / f"{name}.csv")
        assert meta_loaded["status"] == "complete"
        assert len(rows_loaded) == n_rows, f"{name}: {len(rows_loaded)} != {n_rows}"

    # ------------------------------------------------ run summary + meta
    summary = {
        "script": "scripts/run_baselines2.py", "commit": commit, "working_tree_dirty": dirty,
        "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE],
        "catalogue_sha256": catalogue_sha, "catalogue_set": "C", "catalogue_rows": n,
        "limit": limit, "started_utc": started, "elapsed_seconds": time.perf_counter() - t0,
        "python": platform.python_version(), "numpy": np.__version__, "torch": torch.__version__,
        "hardware": hardware,
        "ga": {
            "tuning_rule": baselines2.TUNING_RULE,
            "tuning_gap_reading": ("gap is the mean over V rows with a feasible output; feasibility is the "
                                   "share of (budget, seed, context) rows with a feasible output; both budgets "
                                   "pooled; a configuration that outputs no design has gap = infinity"),
            "selected_config": asdict(ga_cfg), "tuning_scores": [{"id": c.id, **dict(zip(("mean_gap_pct",
                                   "feasibility"), (None if g == float("inf") else round(g, 6), round(f, 6))))}
                                 for c, (g, f) in zip(ga_configs, ga_scores)],
            "tuning_calls_ga_evals": ga_tune_calls,
            "fitness_note": ("feasible sections by mass (lightest best); infeasible sections below every "
                             "feasible one by utilisation overrun max(0, U_max - 1), least first, then mass"),
            "budget_C_note": ("budget |C| evaluates every section (the duplicate rule redraws from unseen "
                              "sections), so it equals the enumeration optimum on every context and seed; the "
                              "budget-91 result is a cost data point, not a GA-quality result"),
            "files": ga_per_file,
        },
        "mlp": {
            "tuning_rule": baselines2.TUNING_RULE,
            "selected_config": asdict(mlp_cfg), "train_seeds": list(baselines2.GA_SEEDS),
            "tuning_scores": [{"id": c.id, **dict(zip(("mean_gap_pct", "feasibility"),
                               (None if g == float("inf") else round(g, 6), round(f, 6))))}
                              for c, (g, f) in zip(mlp_configs, mlp_scores)],
            "labels": labels_json,
            "tuning_calls_verification_and_repair": mlp_tune_calls,
            "cost_note": ("training costs 0 checker calls (the labels are costed); tuning adds the V "
                          "verification + repair calls; the matched-call position uses both label costings"),
            "files": mlp_per_file,
        },
        "n_checker_invocations": kc.invocations, "n_section_evaluations": kc.sections,
    }
    sfile = outdir / "run_summary.json"
    sfile.write_text(json.dumps(summary, indent=2) + "\n", encoding="ascii", newline="\n")
    write_meta(sfile, base_meta("summary", None, sum(len(v) for v in refs.values()), commit, dirty, hashes,
                                started, catalogue_sha, hardware, threads, limit,
                                sum(f["n_feasible_ref"] for f in ga_per_file.values()),
                                sum(f["n_abstain_ref"] for f in ga_per_file.values()),
                                time.perf_counter() - t0, kc))
    print(f"wrote results to {outdir}/ (store self-check passed)")

    # ------------------------------------------------ committed snapshot (skipped with --out: tests use --out)
    if "--out" not in argv:
        day = datetime.now(timezone.utc).date().isoformat()
        head = [
            f"# P8 Stage 1 baselines II: run-output snapshot ({day}, "
            f"{('--limit %d sample' % limit) if limit else 'full run'})",
            f"# Run made from commit {commit} "
            f"({'clean working tree' if dirty is False else 'dirty working tree' if dirty else 'unknown tree'}).",
            f"# Printed output of: python scripts/baselines2_summary.py {outdir}",
            "# The SHA-256 lines below are the sha256sum of the result files (the same hashes are recorded in"
            " each *_meta.json).",
            "# results/ stays git-ignored; archive the folder (e.g. Zenodo) at submission.",
            "# The GA fitness uses utilisation overrun for infeasible sections; the budget-91 result is a cost"
            " data point, not a GA-quality result (recorded in run_summary.json).",
        ]
        hashes_lines = [f"{sha256_file(p)}  {p.name}" for p in sorted(outdir.glob("*.csv"))]
        SNAPSHOT_PATH.write_text("\n".join(head + baselines2_summary.summarise(outdir) + [""] + hashes_lines)
                                 + "\n", encoding="ascii", newline="\n")
        print(f"wrote committed snapshot {SNAPSHOT_PATH}")
    print(f"elapsed {time.perf_counter() - t0:.1f} s")


def _stats(stored, rows, config_id):
    """Per-file summary numbers for the run summary: exact, false abstain, mean gap (ref-feasible contexts)."""
    ref = {r["id"]: ref for r, _, ref in stored}
    mine = [r for r in rows if str(r["config"]) == str(config_id)]
    ex = fa = 0
    gaps = []
    for r in mine:
        if ref[r["id"]].status != "feasible":
            continue
        if r["status"] != "feasible":
            fa += 1
        else:
            g = float(r["gap_pct"])
            gaps.append(g)
            ex += g == 0
    return {"rows": len(mine), "exact": ex, "false_abstain": fa,
            "mean_gap_pct": (None if not gaps else round(float(np.mean(gaps)), 6)),
            "n_feasible_ref": sum(1 for ref in ref.values() if ref.status == "feasible"),
            "n_abstain_ref": sum(1 for ref in ref.values() if ref.status != "feasible")}


if __name__ == "__main__":
    main()
