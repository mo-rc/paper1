"""P9: landscape and saturation diagnostics, the F1 horizon check, the reward-ordering assertion on
V and the Gate 3 record (spec sections 9 and 12; patch plan P9). One script reproduces everything.

Run from the repository root:
    python scripts/landscape_diagnostics.py [workbook.xlsx]             full run over all 34,841 contexts:
                                                                        writes paper/tables/p9_*.csv and
                                                                        docs/gate3_record.md (committed),
                                                                        results/p9/*.csv with *_meta.json
                                                                        (results/ is ignored)
    python scripts/landscape_diagnostics.py [workbook.xlsx] --check     regenerate in a temporary folder and
                                                                        compare with the committed files (exit 1
                                                                        if any differs)
    python scripts/landscape_diagnostics.py [workbook.xlsx] --limit N   sample run: the first N contexts per
                                                                        split file; nothing committed, the P7
                                                                        snapshot assertions are skipped, and the
                                                                        results go to results/p9_sample
    --out DIR                                                           write the runstore results to DIR instead

What the script computes (one vectorised enumeration pass per context, 91 checker calls each, plus
the heuristic's own measured calls; nothing trains, nothing changes the checker, the physics, the
objective or the splits):
  monotonicity counter  c1: a lighter section is feasible while a heavier one below it is not (any
                        pair, plus the adjacent-edge count c1_edges); c2: an infeasible section lies
                        strictly between the optimum and the heuristic's trial section (the patch
                        plan's phrasing); c2_block: the same between the optimum and the first
                        feasible section at or above the trial (exactly the stretch the heuristic's
                        downward walk must pass)
  F1 horizon check      fewest F1 actions from the trial section to the optimum on the actual action
                        graph (mass step up/down, lightest section of the next strictly deeper or
                        shallower series; accept terminates and is not counted; a no-op past either
                        end costs a step but never shortens a path, so it is not an edge). The script
                        reports the distribution and the share of contexts needing more than
                        HORIZON_F1 = 12 steps (spec section 9). It never changes the horizon: an
                        excess is recorded and flagged for approval, per instruction.
  governing check       Checker.check at the optimum with the context's config applied: the checker's
                        own tie-break, not a reimplementation
  alternatives          feasible sections within 5 % of the optimal mass; of those, the ones whose
                        depth differs from the optimum's by at least 50 mm (spec section 9)
  saturation            per set with V as the headline line: heuristic exact-match share over the
                        feasible contexts, false abstentions, infeasible outputs (rechecked), mean
                        heuristic calls; the ordered scan is exact by definition (the first feasible
                        section in mass order is the lightest feasible section; P7 verified
                        enumeration = ordered scan on every context) and its mean call count is read
                        from the mask
  reward ordering       reward_checks.assert_ordering on every validation context, per family
                        (R1, R2, R3 at beta 25/50/100, R-C, R-D): the smallest feasible candidate
                        return must exceed the largest infeasible candidate return, in float64
                        log-space, margin at or above the analytic bound
On a full run the per-file feasible counts and mean heuristic calls must reproduce the committed P7
snapshot (results/baselines1/run_summary.json, commit b5aadf4); on a sample run that assertion is
skipped, as recorded in the metas.
"""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/ (run from the repository root)
from ub_rl.runstore import hardware_info, limit_threads, write_meta, write_results  # noqa: E402

limit_threads()  # before numpy is imported: spec section 10, single CPU thread

import csv  # noqa: E402
import json  # noqa: E402
import platform  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from collections import Counter  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402

from ub_rl import reward_checks as RC  # noqa: E402
from ub_rl import splits as S  # noqa: E402
from ub_rl.baselines import CountingChecker, heuristic  # noqa: E402
from ub_rl.catalogue import parse_workbook, sha256_file  # noqa: E402
from ub_rl.checker import CHECKS, Checker  # noqa: E402
from ub_rl.landscape import HORIZON_F1, diagnose, f1_distances  # noqa: E402

DEFAULT_WORKBOOK = "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
SPLIT_FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]
SET_ORDER = ["train", "val", "t1", "t2", "t3-E1", "t3-E2", "t3-E3", "t4-A", "t4-B", "t5", "s12-val", "s12-t1",
             "s12-t2", "s12-E1", "s12-E2", "s12-E3", "ref"]
ENV_FILE = "src/ub_rl/checker.py"
HASHED_FILES = ["src/ub_rl/checker.py", "src/ub_rl/context.py", "src/ub_rl/config.py", "src/ub_rl/splits.py",
                "src/ub_rl/baselines.py", "src/ub_rl/landscape.py", "src/ub_rl/reward_checks.py",
                "scripts/landscape_diagnostics.py"]
COMMITTED = ["p9_landscape.csv", "p9_horizon.csv", "p9_governing.csv", "p9_alternatives.csv", "p9_saturation.csv",
             "p9_rewards.csv"]

# P7 committed snapshot (results/baselines1/run_summary.json, commit b5aadf4): the heuristic matched the
# enumeration optimum in every feasible context, with these per-file feasible counts and mean calls
# (means over all n contexts including abstentions). A full run must reproduce them exactly.
EXPECTED_P7 = {
    "train": (16723, 13.553), "val": (796, 14.193), "test_t1": (1635, 13.74), "test_t2": (388, 15.302),
    "test_t3": (609, 19.229), "test_t4": (1404, 9.883), "test_t5": (3102, 13.863),
    "v12_substudy": (4500, 2.416), "reference": (4, 8.75),
}


# ------------------------------------------------------------------ shared helpers (context_audit style)
def write_rows(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="ascii") as f:
        wr = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)


def git_info():
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], text=True).strip())
    except Exception:
        commit, dirty = "unknown", None
    return commit, dirty


def f2(x):
    return f"{x:.2f}"


def f3(x):
    return f"{x:.3f}"


def f4(x):
    return f"{x:.4f}"


def f6(x):
    return f"{x:.6f}"


# ------------------------------------------------------------------ the run
def build(root, workbook, limit=None, out_results=None):
    """Run the diagnostics and write every output under root (paper/tables and docs — the committed
    outputs on a full run) and the runstore results (root/results/p9, p9_sample for --limit, or
    out_results). Returns the summary dict."""
    root = Path(root)
    t0 = time.perf_counter()
    # the split files must be the committed ones (never change the splits)
    manifest = {}
    for line in Path("data/splits/SHA256SUMS").read_text(encoding="ascii").splitlines():
        sha, name = line.split()
        manifest[name] = sha
    bad = [n for n in SPLIT_FILES if sha256_file(Path("data/splits") / f"{n}.csv") != manifest[f"{n}.csv"]]
    if bad:
        raise RuntimeError(f"split files differ from the committed manifest: {bad}")

    cat, _ = parse_workbook(workbook)
    C = cat.mass_ordered(False)
    K = Checker(C)
    kc = CountingChecker(K)  # counts the heuristic's checker calls (the enumeration uses K directly)
    f1_d = f1_distances(K.cat.series, K.h)
    hashes = {p: sha256_file(p) for p in HASHED_FILES}
    commit, dirty = git_info()
    hardware = hardware_info()
    rdir = Path(out_results) if out_results else root / "results" / ("p9_sample" if limit else "p9")
    # committed outputs (paper/tables, docs) are written under root only on a full run; a sample run
    # keeps its tables and record next to its results (nothing committed, per the patch plan)
    troot = rdir if limit is not None else root

    agg = {}  # set -> aggregates across the split files
    files = []  # per-file summaries
    val_ctxs = []  # the validation contexts for the reward-ordering assertion
    horizon_excess = []  # (set, n_gt12, n_feasible) — recorded, never acted on
    for fname in SPLIT_FILES:
        rows, ctxs = S.load_split(fname)
        if limit:
            rows, ctxs = rows[:limit], ctxs[:limit]
        if fname == "val":
            val_ctxs = ctxs
        ctx_rows = []
        heur_calls_total = 0
        n_feasible = n_abstain = heur_exact = false_abstain = infeasible_outputs = 0
        for r, ctx in zip(rows, ctxs):
            e = K.evaluate_context(ctx)
            d = diagnose(K, ctx, f1_d, e=e)
            hres = heuristic(kc, ctx)  # measured calls, memoised within the context
            heur_calls_total += hres.calls
            opt = d["opt"]
            n_feasible += opt >= 0
            n_abstain += opt < 0
            inf_out = 0
            if hres.index >= 0:  # recheck every output: the saturation feasibility column
                if not bool(kc.evaluate_context(ctx, [hres.index])["feasible"][0]):
                    inf_out = 1
            infeasible_outputs += inf_out
            heur_exact += int(hres.index == opt)
            false_abstain += int(opt >= 0 and hres.index < 0)
            scan_calls = int(opt + 1) if opt >= 0 else len(kc)  # ordered scan: exact by definition
            ctx_rows.append({
                "id": r["id"], "set": r["set"], "file": fname, "feasible": int(opt >= 0),
                "opt": opt, "optimum_name": C.names[opt] if opt >= 0 else "",
                "mass_kg_m": f"{K.mass[opt]:.1f}" if opt >= 0 else "", "depth_mm": f"{K.h[opt]:.0f}" if opt >= 0 else "",
                "trial": d["trial"] if opt >= 0 else "", "f1_distance": d["f1_distance"] if opt >= 0 else "",
                "c1": d.get("c1", 0), "c1_edges": d.get("c1_edges", 0), "c2": d.get("c2", 0),
                "c2_block": d.get("c2_block", 0), "walk_start": d.get("walk_start", ""),
                "governing": d.get("governing", ""), "u_opt": f6(d["u_opt"]) if "u_opt" in d else "",
                "n_within5": d.get("n_within5", 0), "n_depth50": d.get("n_depth50", 0),
                "heuristic_index": hres.index, "heuristic_exact": int(hres.index == opt),
                "heuristic_calls": hres.calls, "scan_calls": scan_calls,
            })
            a = agg.setdefault(r["set"], {"n": 0, "n_feasible": 0, "opts": set(), "c1": 0, "c1_edges": 0,
                                          "c2": 0, "c2_block": 0, "within5": 0, "within5_gt1": 0, "depth50": 0,
                                          "depth50_any": 0, "horizon": Counter(), "heur_exact": 0,
                                          "heur_calls": 0, "scan_calls": 0, "heur_outputs": 0,
                                          "false_abstain": 0, "infeasible_outputs": 0, "governing": Counter()})
            a["n"] += 1
            a["heur_exact"] += int(hres.index == opt)
            a["heur_calls"] += hres.calls
            a["scan_calls"] += scan_calls
            a["heur_outputs"] += int(hres.index >= 0)
            a["false_abstain"] += int(opt >= 0 and hres.index < 0)
            a["infeasible_outputs"] += inf_out
            if opt >= 0:
                a["n_feasible"] += 1
                a["opts"].add(opt)
                a["c1"] += d["c1"]
                a["c1_edges"] += d["c1_edges"]
                a["c2"] += d["c2"]
                a["c2_block"] += d["c2_block"]
                a["within5"] += d["n_within5"]
                a["within5_gt1"] += int(d["n_within5"] > 1)
                a["depth50"] += d["n_depth50"]
                a["depth50_any"] += int(d["n_depth50"] > 0)
                a["horizon"][d["f1_distance"]] += 1
                a["governing"][d["governing"]] += 1
        # per-context results with a runstore meta (results/ is ignored by git)
        path = rdir / f"p9_contexts_{fname}.csv"
        write_results(path, ctx_rows,
                      ["id", "set", "file", "feasible", "opt", "optimum_name", "mass_kg_m", "depth_mm", "trial",
                       "f1_distance", "c1", "c1_edges", "c2", "c2_block", "walk_start", "governing", "u_opt",
                       "n_within5", "n_depth50", "heuristic_index", "heuristic_exact", "heuristic_calls",
                       "scan_calls"],
                      {"status": "complete", "method": "p9_landscape", "commit": commit,
                       "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE],
                       "catalogue_sha256": sha256_file(workbook), "catalogue_set": "C", "catalogue_rows": len(kc),
                       "split_file": f"data/splits/{fname}.csv", "split_sha256": manifest[f"{fname}.csv"],
                       "n_contexts": len(rows), "n_feasible": n_feasible, "n_abstain": n_abstain,
                       "limit": limit, "file_sha256": hashes, "hardware": hardware,
                       "elapsed_seconds": round(time.perf_counter() - t0, 3)})
        files.append({"file": fname, "n": len(rows), "n_feasible": n_feasible, "n_abstain": n_abstain,
                      "heuristic_exact": heur_exact, "false_abstain": false_abstain,
                      "infeasible_outputs": infeasible_outputs,
                      "mean_heuristic_calls": f3(heur_calls_total / len(rows)),
                      "mean_scan_calls": f2(sum(r["scan_calls"] for r in ctx_rows) / len(rows))})
        # P7 snapshot assertion on full runs only (sample runs are explicitly not this evidence)
        if limit is None:
            n_exp, calls_exp = EXPECTED_P7[fname]
            assert n_feasible == n_exp, f"{fname}: {n_feasible} feasible contexts, P7 snapshot has {n_exp}"
            assert round(heur_calls_total / len(rows), 3) == calls_exp, \
                f"{fname}: mean heuristic calls {round(heur_calls_total / len(rows), 3)}, P7 snapshot has {calls_exp}"
    p7_ok = limit is None  # the snapshot was asserted above on full runs; skipped by design on samples

    # ------------------------------------------------ the per-set tables
    sets_present = [s for s in SET_ORDER if s in agg]
    write_rows(troot / "paper" / "tables" / "p9_landscape.csv",
               [{"set": s, "n": agg[s]["n"], "n_feasible": agg[s]["n_feasible"],
                 "n_optima_distinct": len(agg[s]["opts"]), "c1": agg[s]["c1"], "c1_edges": agg[s]["c1_edges"],
                 "c2": agg[s]["c2"], "c2_block": agg[s]["c2_block"]} for s in sets_present],
               ["set", "n", "n_feasible", "n_optima_distinct", "c1", "c1_edges", "c2", "c2_block"])

    horizon_rows, horizon_ok = [], True
    for s in sets_present:
        h, nf = agg[s]["horizon"], agg[s]["n_feasible"]
        gt12 = sum(v for k, v in h.items() if k > HORIZON_F1)
        if gt12:
            horizon_ok = False
            horizon_excess.append((s, gt12, nf))
        row = {"set": s, "n_feasible": nf}
        for k in range(HORIZON_F1 + 1):
            row[f"d{k}"] = h[k]
        row.update({"gt12": gt12, "share_gt12": f4(gt12 / nf) if nf else "0.0000",
                    "max_d": max(h) if nf else "",
                    "flag": f"APPROVAL NEEDED: {gt12} of {nf} contexts need more than {HORIZON_F1} F1 steps"
                            if gt12 else ""})
        horizon_rows.append(row)
    write_rows(troot / "paper" / "tables" / "p9_horizon.csv", horizon_rows,
               ["set", "n_feasible"] + [f"d{k}" for k in range(HORIZON_F1 + 1)] + ["gt12", "share_gt12", "max_d", "flag"])

    governing_rows = [{"set": s, "n_feasible": agg[s]["n_feasible"],
                       **{c: agg[s]["governing"][c] for c in CHECKS}} for s in sets_present]
    write_rows(troot / "paper" / "tables" / "p9_governing.csv", governing_rows, ["set", "n_feasible"] + list(CHECKS))

    alternatives_rows = [{"set": s, "n_feasible": agg[s]["n_feasible"],
                          "mean_within5": f2(agg[s]["within5"] / agg[s]["n_feasible"]) if agg[s]["n_feasible"] else "",
                          "n_within5_gt1": agg[s]["within5_gt1"],
                          "mean_depth50": f2(agg[s]["depth50"] / agg[s]["n_feasible"]) if agg[s]["n_feasible"] else "",
                          "n_depth50_any": agg[s]["depth50_any"]} for s in sets_present]
    write_rows(troot / "paper" / "tables" / "p9_alternatives.csv", alternatives_rows,
               ["set", "n_feasible", "mean_within5", "n_within5_gt1", "mean_depth50", "n_depth50_any"])

    # saturation: V is the headline line (first row); ordered scan exact by definition (P7 verified
    # enumeration = ordered scan on every context), its mean call count read from the mask
    saturation_rows = []
    for s in ["val"] + [x for x in sets_present if x != "val"]:
        a, nf = agg[s], agg[s]["n_feasible"]
        sat_met = int(nf > 0 and (a["heur_exact"] / nf) >= 0.99 and a["infeasible_outputs"] == 0
                      and a["false_abstain"] == 0)
        saturation_rows.append({
            "set": s, "n": a["n"], "n_feasible": nf, "n_abstain": a["n"] - nf,
            "heuristic_outputs": a["heur_outputs"], "heuristic_exact": a["heur_exact"],
            "exact_share": f4(a["heur_exact"] / nf) if nf else "", "false_abstain": a["false_abstain"],
            "infeasible_outputs": a["infeasible_outputs"],
            "feasibility_share": f4((a["heur_outputs"] - a["infeasible_outputs"]) / a["heur_outputs"])
                                 if a["heur_outputs"] else "",
            "heuristic_calls_mean": f3(a["heur_calls"] / a["n"]), "scan_calls_mean": f2(a["scan_calls"] / a["n"]),
            "ordered_scan_exact": 1, "saturation_rule_met": sat_met})
    write_rows(troot / "paper" / "tables" / "p9_saturation.csv", saturation_rows,
               ["set", "n", "n_feasible", "n_abstain", "heuristic_outputs", "heuristic_exact", "exact_share",
                "false_abstain", "infeasible_outputs", "feasibility_share", "heuristic_calls_mean",
                "scan_calls_mean", "ordered_scan_exact", "saturation_rule_met"])

    # reward-ordering assertion on every validation context, per family (float64 log-space)
    rewards_report = RC.assert_ordering(K, val_ctxs)
    write_rows(troot / "paper" / "tables" / "p9_rewards.csv",
               [{"family": r["family"], "beta": r["beta"], "key": r["key"], "n": r["n"],
                 "n_nonvacuous": r["n_nonvacuous"], "n_vacuous": r["n_vacuous"],
                 "min_margin": f6(r["min_margin"]), "max_margin": f6(r["max_margin"]),
                 "margin_bound": f6(r["margin_bound"]), "violations": r["violations"], "pass": r["pass"]}
                for r in rewards_report["rows"]],
               ["family", "beta", "key", "n", "n_nonvacuous", "n_vacuous", "min_margin", "max_margin",
                "margin_bound", "violations", "pass"])

    summary = {
        "script": "scripts/landscape_diagnostics.py", "commit": commit, "working_tree_dirty": dirty,
        "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE],
        "catalogue_sha256": sha256_file(workbook), "catalogue_set": "C", "catalogue_rows": len(kc),
        "split_manifest_sha256": sha256_file("data/splits/SHA256SUMS"), "limit": limit,
        "n_contexts_total": sum(f["n"] for f in files), "p7_snapshot_ok": p7_ok,
        "horizon": HORIZON_F1, "horizon_confirmed": horizon_ok, "horizon_excess": horizon_excess,
        "horizon_rows": horizon_rows, "governing": {r["set"]: r for r in governing_rows},
        "alternatives": {r["set"]: r for r in alternatives_rows},
        "files": files, "sets": {s: {"n": agg[s]["n"], "n_feasible": agg[s]["n_feasible"],
                                     "n_optima_distinct": len(agg[s]["opts"]), "c1": agg[s]["c1"],
                                     "c1_edges": agg[s]["c1_edges"], "c2": agg[s]["c2"],
                                     "c2_block": agg[s]["c2_block"]} for s in sets_present},
        "saturation": saturation_rows, "rewards": rewards_report,
        "n_checker_invocations": kc.invocations, "n_section_evaluations": kc.sections,
        "hardware": hardware, "python": platform.python_version(), "numpy": np.__version__,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.perf_counter() - t0, 3),
    }
    spath = rdir / "p9_summary.json"
    spath.parent.mkdir(parents=True, exist_ok=True)
    with open(spath, "w", encoding="ascii", newline="\n") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    write_meta(spath, {"status": "complete", "method": "p9_landscape", "commit": commit,
                       "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE],
                       "catalogue_sha256": sha256_file(workbook),
                       "split_file": "data/splits/SHA256SUMS (all split files)",
                       "split_sha256": sha256_file("data/splits/SHA256SUMS"),
                       "n_contexts": summary["n_contexts_total"]})

    render_gate3(troot / "docs" / "gate3_record.md", summary, hashes, commit, dirty, limit)
    if horizon_excess:
        print("APPROVAL NEEDED: the optimum lies more than 12 F1 steps from the trial section in:",
              horizon_excess, file=sys.stderr)
        print("The horizon was NOT changed; HORIZON_F1 stays 12. Flag recorded in p9_horizon.csv and the gate record.",
              file=sys.stderr)
    return summary


# ------------------------------------------------------------------ the Gate 3 record (deterministic)
def render_gate3(path, summary, hashes, commit, dirty, limit):
    def md_table(cols, rows):
        lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        lines += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
        return "\n".join(lines)

    sets = [s for s in SET_ORDER if s in summary["sets"]]
    sat = {r["set"]: r for r in summary["saturation"]}
    val = sat["val"]
    lines = ["# Gate 3 record - P9 landscape and saturation diagnostics", ""]
    lines += [f"Provenance: `scripts/landscape_diagnostics.py`, commit {commit},"
              f"{' working tree dirty' if dirty else ' clean'}; environment `src/ub_rl/checker.py` "
              f"sha256 {hashes[ENV_FILE][:16]}...; catalogue workbook sha256 {summary['catalogue_sha256'][:16]}...; "
              f"split manifest `data/splits/SHA256SUMS` sha256 {summary['split_manifest_sha256'][:16]}...; "
              f"catalogue C ({summary['catalogue_rows']} sections); {summary['n_contexts_total']} contexts"
              f"{f' (sample run, first {limit} contexts per split file)' if limit else ' (full run)'}; heuristic call "
              f"accounting measured by the checker wrapper. Generated deterministically; `--check` reproduces "
              f"this record byte for byte.", ""]
    lines += ["## Saturation (headline line: V)", "",
              "Heuristic iteration against the enumeration optimum, per set. The ordered scan is exact by "
              "definition - its first feasible section in mass order is the lightest feasible section - and P7 "
              "verified enumeration = ordered scan on every context; its mean call count below is read from the "
              "enumeration mask. Heuristic outputs are rechecked; false abstentions are counted.", "",
              md_table(["set", "n", "n_feasible", "heuristic exact", "exact share", "false abstain",
                        "infeasible outputs", "feasibility share", "heuristic calls (mean)",
                        "scan calls (mean)", "rule met"],
                       [{"set": s, "n": sat[s]["n"], "n_feasible": sat[s]["n_feasible"],
                         "heuristic exact": sat[s]["heuristic_exact"], "exact share": sat[s]["exact_share"],
                         "false abstain": sat[s]["false_abstain"], "infeasible outputs": sat[s]["infeasible_outputs"],
                         "feasibility share": sat[s]["feasibility_share"],
                         "heuristic calls (mean)": sat[s]["heuristic_calls_mean"],
                         "scan calls (mean)": sat[s]["scan_calls_mean"], "rule met": sat[s]["saturation_rule_met"]}
                        for s in ["val"] + [x for x in sets if x != "val"]]), ""]
    lines += ["Saturation rule (spec section 12): heuristic iteration or the classifier at exact match >= 0.99 and "
              "feasibility 1.0 on V. Reading used here: the exact share is over the feasible contexts (abstentions "
              "excluded, false abstentions counted against it), and feasibility is the share of heuristic outputs "
              "that are feasible (rechecked; an abstention is not an output). On V: exact share "
              f"{val['exact_share']}, false abstain {val['false_abstain']}, infeasible outputs "
              f"{val['infeasible_outputs']} -> the rule is "
              f"{'MET' if val['saturation_rule_met'] else 'NOT MET'} on V.", ""]
    lines += ["## Monotonicity counter", "",
              "c1: a lighter section is feasible while a heavier one below it is not (any pair; c1_edges is the "
              "adjacent-edge count). c2: an infeasible section strictly between the optimum and the heuristic's "
              "trial section (the patch plan's phrasing). c2_block: the same between the optimum and the first "
              "feasible section at or above the trial - exactly the stretch the downward walk must pass, so "
              "c2_block = 0 means the walk reaches the optimum structurally.", "",
              md_table(["set", "n_feasible", "distinct optima", "c1", "c1_edges", "c2", "c2_block"],
                       [{"set": s, "n_feasible": summary["sets"][s]["n_feasible"],
                         "distinct optima": summary["sets"][s]["n_optima_distinct"], "c1": summary["sets"][s]["c1"],
                         "c1_edges": summary["sets"][s]["c1_edges"], "c2": summary["sets"][s]["c2"],
                         "c2_block": summary["sets"][s]["c2_block"]} for s in sets]), ""]
    c1_total = sum(summary["sets"][s]["c1"] for s in sets)
    c2b_total = sum(summary["sets"][s]["c2_block"] for s in sets)
    if c1_total == 0:
        lines += ["Feasibility is monotone in mass order on every split: no lighter section is feasible where a "
                  "heavier one below it is not. The heuristic and the ordered scan are therefore equal "
                  "structurally, which explains the P7 result (the heuristic matched the enumeration optimum in "
                  "all 29,161 feasible contexts).", ""]
    else:
        lines += [f"Monotonicity fails in {c1_total} contexts (c1); c2_block = {c2b_total}. The P7 zero gap "
                  f"forces c2_block = 0 in every feasible context (the stretch from the optimum to the walk start "
                  f"has no infeasible section, so the downward walk reaches the optimum); non-monotone dips above "
                  f"the trial cannot be reached by the walk. These counts are the recorded explanation.", ""]
    lines += ["## F1 horizon check (spec section 9, horizon %d)" % HORIZON_F1, "",
              "Fewest F1 actions from the trial section to the optimum on the actual action graph (mass step "
              "up/down, lightest section of the next strictly deeper or shallower series; accept terminates and "
              "is not counted; a no-op past either end costs a step but never shortens a path, so it is not an "
              "edge). Gate 3 verifies the optimum lies within 12 steps of the trial section on every split.", "",
              md_table(["set", "n_feasible", "max steps", "share needing more than 12"],
                       [{"set": r["set"], "n_feasible": r["n_feasible"], "max steps": r["max_d"],
                         "share needing more than 12": r["share_gt12"]} for r in summary["horizon_rows"]]), ""]
    if summary["horizon_confirmed"]:
        lines += [f"The F1 horizon of {HORIZON_F1} is confirmed: on every split, every feasible context's optimum "
                  f"is reachable from the trial section in at most {HORIZON_F1} F1 actions.", ""]
    else:
        lines += ["**APPROVAL NEEDED - the F1 horizon of 12 is NOT confirmed.** The sets below need more than 12 "
                  "steps; the horizon was not changed, per instruction:", ""]
        for s, n, nf in summary["horizon_excess"]:
            lines += [f"- {s}: {n} of {nf} feasible contexts need more than {HORIZON_F1} steps", ""]
    lines += ["## Governing check at the optimum", "",
              "Checker.check at each context's optimum with the context's config applied (the checker's own "
              "tie-break, not a reimplementation); counts of the governing utilisation per set.", "",
              md_table(["set", "n_feasible"] + list(CHECKS),
                       [{"set": s, "n_feasible": summary["governing"][s]["n_feasible"],
                         **{c: summary["governing"][s][c] for c in CHECKS}} for s in sets]), ""]
    lines += ["## Alternatives (within 5 % of optimal mass; depth differing by >= 50 mm)", "",
              md_table(["set", "n_feasible", "mean within 5 %", "with > 1", "mean depth >= 50", "any"],
                       [{"set": s, "n_feasible": a["n_feasible"], "mean within 5 %": a["mean_within5"],
                         "with > 1": a["n_within5_gt1"], "mean depth >= 50": a["mean_depth50"],
                         "any": a["n_depth50_any"]} for s in sets for a in [summary["alternatives"][s]]]), ""]
    lines += ["## Reward ordering on V (float64 log-space)", "",
              "The assertion: for every validation context and every family, the smallest return over all feasible "
              "candidates exceeds the largest return over all infeasible candidates, in float64 log-space, with a "
              "margin at or above the analytic bound (R1/R2/R-C 0.988, R3 10, R-D 0.5). A candidate is a "
              "(section, calls 0..12) pair; contexts with no feasible or no infeasible candidate are vacuous and "
              "counted, not failed.", "",
              md_table(["key", "family", "beta", "n", "non-vacuous", "vacuous", "min margin", "bound", "violations", "pass"],
                       [{"key": r["key"], "family": r["family"], "beta": r["beta"], "n": r["n"],
                         "non-vacuous": r["n_nonvacuous"],
                         "vacuous": r["n_vacuous"], "min margin": r["min_margin"], "bound": r["margin_bound"],
                         "violations": r["violations"], "pass": r["pass"]}
                        for r in summary["rewards"]["rows"]]), ""]
    if all(r["pass"] for r in summary["rewards"]["rows"]):
        lines += ["The assertion holds: zero violations on every validation context and every family, margins at "
                  "or above the analytic bounds.", ""]
    else:
        lines += ["**The assertion FAILED** - see the violations column; the families are not ordered on V.", ""]
    lines += ["## What the paper can claim", ""]
    if summary["horizon_confirmed"]:
        lines += ["- Gate 3's F1 precondition holds: on every split the optimum lies within 12 F1 steps of the "
                  "trial section (spec section 9), so the horizon needs no amendment.", ""]
    else:
        lines += ["- The F1 horizon precondition is NOT confirmed; the paper must record the flagged sets and the "
                  "amendment decision before training.", ""]
    if c1_total == 0:
        lines += ["- Feasibility is monotone in mass order on every split, so the heuristic equals the ordered "
                  "scan structurally, which explains the P7 zero gap (29,161 feasible contexts, all exact).", ""]
    else:
        lines += [f"- Monotonicity fails in {c1_total} contexts; c2_block = {c2b_total} is the recorded "
                  f"explanation of why the P7 zero gap still holds.", ""]
    if val["saturation_rule_met"]:
        lines += ["- Saturation on V: the heuristic reaches exact match >= 0.99 with feasibility 1.0 on V (spec "
                  "section 12), so the study reports that a learned policy has no quality headroom on V; RL still "
                  "runs for sample efficiency, diversity and cost, and no quality-superiority claim is possible "
                  "there.", ""]
    else:
        lines += ["- The saturation rule is NOT met on V; the study does not report the no-headroom statement, "
                  "and the P8 classifier leg decides the saturation outcome per the rule.", ""]
    if all(r["pass"] for r in summary["rewards"]["rows"]):
        lines += ["- The reward-ordering property holds on every validation context for every family in float64 "
                  "log-space, so the families separate feasible from infeasible candidates (Gate 3's reward "
                  "asserts).", ""]
    lines += ["## Assumptions and readings", "",
              "1. Saturation exact share is over feasible contexts; false abstentions count against it; "
              "feasibility is the share of rechecked heuristic outputs that are feasible.",
              "2. The ordered scan is exact by definition and P7-verified; it is not re-run, its mean call count "
              "comes from the enumeration mask.",
              "3. Mean heuristic calls are over all n contexts including abstentions (the P7 convention).",
              "4. The horizon check counts actions on the actual F1 graph; accept terminates and is not counted; "
              "no-ops past the ends are not graph edges.",
              "5. Catalogue C only (91 sections); C+ is a sensitivity and out of scope here.",
              "6. On a full run the per-file feasible counts and mean heuristic calls must reproduce the P7 "
              "snapshot exactly (asserted by the script); sample runs skip the assertion and say so.", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="ascii", newline="\n")


# ------------------------------------------------------------------ --check: rebuild in a temp folder and compare
def compare(tmp):
    names = [f"paper/tables/{n}" for n in COMMITTED] + ["docs/gate3_record.md"]
    bad = [name for name in names if Path(name).read_bytes() != Path(tmp, name).read_bytes()]
    if bad:
        print("DIFFERING:", *bad, sep="\n  ")
        return 1
    print(f"identical ({len(names)} files)")
    return 0


def main(argv):
    limit, out, check = None, None, False
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--limit" and i + 1 < len(argv):
            limit = int(argv[i + 1])
            i += 2
        elif a == "--out" and i + 1 < len(argv):
            out = argv[i + 1]
            i += 2
        elif a == "--check":
            check = True
            i += 1
        else:
            positional.append(a)
            i += 1
    if len(positional) > 1:
        raise SystemExit("usage: landscape_diagnostics.py [workbook.xlsx] [--limit N] [--out DIR] [--check]")
    workbook = positional[0] if positional else DEFAULT_WORKBOOK
    if limit is not None and limit < 1:
        raise SystemExit("--limit must be at least 1")
    if check:
        if limit is not None:
            raise SystemExit("--check compares the committed full-run outputs; --limit is not allowed with it")
        tmp = Path(tempfile.mkdtemp(prefix="p9_check_"))
        build(tmp, workbook, limit=None)
        return compare(tmp)
    build(Path("."), workbook, limit=limit, out_results=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
