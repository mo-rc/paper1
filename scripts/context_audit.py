"""P6: generate the Stage 1 splits (spec Amendment A2), run the feasibility audit by enumeration over the catalogue C,
and write the audit tables. One script reproduces everything.

Run from the repository root:
    python scripts/context_audit.py [workbook.xlsx]           write files
    python scripts/context_audit.py [workbook.xlsx] --check   regenerate in a temporary folder and compare with the
                                                             committed files (exit 1 if any differs)

Committed outputs (deterministic):  data/splits/*.csv, data/splits/SHA256SUMS, data/splits/abstention_contexts.csv,
paper/tables/audit_*.csv, docs/context_audit.md.
Not committed (results/ is ignored): results/audit/labels_<file>.csv with a *_meta.json each.
No RL is run. The checker is called once per context (about 31,000 calls on C and again on C+)."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))  # use the repository src/ (run from the repository root)
import csv
import json
import platform
import subprocess
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ub_rl import splits as S
from ub_rl.catalogue import parse_workbook, sha256_file
from ub_rl.checker import Checker

DEFAULT_WORKBOOK = "data/raw/UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
SPLIT_FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]
SET_ORDER = ["train", "val", "t1", "t2", "t3-E1", "t3-E2", "t3-E3", "t4-A", "t4-B", "t5", "s12-val", "s12-t1", "s12-t2", "s12-E1",
             "s12-E2", "s12-E3", "ref"]
# Reference-case optima at restraint ratios 0, 0.25, 0.5, 1 (docs/verification_record.md, shear-centre row)
EXPECTED_REF = {0.0: "457x191x74", 0.25: "533x210x82", 0.5: "610x229x101", 1.0: "686x254x140"}
# Audit rules of Amendment A2 (sanity gates for the box, not claims)
RULE_ABSTAIN_MAX = 0.25  # R1: training-pool abstention share
RULE_CELL_FEASIBLE_MIN = 0.25  # R2: feasible share in every training cell
ENV_FILE = "src/ub_rl/checker.py"
HASHED_FILES = ["src/ub_rl/checker.py", "src/ub_rl/context.py", "src/ub_rl/config.py", "src/ub_rl/splits.py",
                "scripts/context_audit.py"]
L_EDGES = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
W_EDGES = [56.0, 67.0, 78.0, 89.0, 100.0]


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


def enumerate_contexts(K, C, rows):
    """One checker call per context. Returns a list of label dicts."""
    out = []
    for r in rows:
        e = K.evaluate_context(S.row_to_context(r))
        ok, okc = e["feasible"], e["feasible_code"]
        opt = int(np.argmax(ok)) if ok.any() else -1
        optc = int(np.argmax(okc)) if okc.any() else -1
        status = "feasible" if opt >= 0 else ("abstain_depth" if optc >= 0 else "abstain_code")
        out.append({"id": r["id"], "optimum_index": opt, "optimum_name": C.names[opt] if opt >= 0 else "",
                    "mass_kg_m": f"{K.mass[opt]:.1f}" if opt >= 0 else "", "depth_mm": f"{K.h[opt]:.0f}" if opt >= 0 else "",
                    "n_feasible": int(ok.sum()), "n_feasible_code": int(okc.sum()), "status": status,
                    "optimum_uncapped_index": optc, "cap_binding": int(opt >= 0 and opt != optc)})
    return out


def f4(x):
    return f"{x:.4f}"


def build(root, workbook):
    root = Path(root)
    gen = S.generate_all()
    held, attempt = S.held_out_cells()
    sdir = root / "data" / "splits"
    for name in SPLIT_FILES:
        write_rows(sdir / f"{name}.csv", gen[name], S.COLUMNS)
    write_rows(sdir / "heldout_cells.csv", S.heldout_rows(), ["restraint_ratio", "deflection_rule", "depth_cap"])

    cat, _ = parse_workbook(workbook)
    C = cat.mass_ordered(False)
    K = Checker(C)
    Cp = cat.mass_ordered(True)  # set C+ (107 sections), spec section 9
    Kp = Checker(Cp)
    plus_by_id = {}
    rows_by_set, label_by_id, labels_by_file, labels_plus = defaultdict(list), {}, {}, {}
    for fname in SPLIT_FILES:
        labels = enumerate_contexts(K, C, gen[fname])
        labels_by_file[fname] = labels
        labels_plus[fname] = enumerate_contexts(Kp, Cp, gen[fname])
        for r, lab in zip(gen[fname], labels):
            rows_by_set[r["set"]].append(r)
            label_by_id[r["id"]] = lab
        for r, lab in zip(gen[fname], labels_plus[fname]):
            plus_by_id[r["id"]] = lab

    tdir = root / "paper" / "tables"
    # ---- abstention list (none removed from any split file)
    ab = []
    for fname in SPLIT_FILES:
        for r in gen[fname]:
            st = label_by_id[r["id"]]["status"]
            if st != "feasible":
                ab.append({**{c: r[c] for c in S.COLUMNS if c != "slice_full_restraint"}, "status": st})
    write_rows(sdir / "abstention_contexts.csv", ab, [c for c in S.COLUMNS if c != "slice_full_restraint"] + ["status"])

    # ---- table 1: feasibility by set
    t1 = []
    for sname in SET_ORDER:
        rs = rows_by_set[sname]
        labs = [label_by_id[r["id"]] for r in rs]
        feas = [l for l in labs if l["status"] == "feasible"]
        masses = np.array([float(l["mass_kg_m"]) for l in feas]) if feas else np.array([np.nan])
        n = len(rs)
        t1.append({"set": sname, "n": n, "n_feasible": len(feas), "n_abstain": n - len(feas),
                   "abstain_rate": f4((n - len(feas)) / n),
                   "abstain_code": sum(l["status"] == "abstain_code" for l in labs),
                   "abstain_depth": sum(l["status"] == "abstain_depth" for l in labs),
                   "distinct_optima": len({l["optimum_index"] for l in feas}),
                   "optimum_mass_min": f"{masses.min():.1f}", "optimum_mass_median": f"{np.median(masses):.1f}",
                   "optimum_mass_max": f"{masses.max():.1f}",
                   "cap_binding": sum(l["cap_binding"] for l in feas)})
    write_rows(tdir / "audit_sets.csv", t1, list(t1[0]))

    # ---- table 2: feasibility by cell (training pool, T4-A, T4-B)
    t2 = []
    for sname in ("train", "t4-A", "t4-B"):
        cells = defaultdict(list)
        for r in rows_by_set[sname]:
            cells[(float(r["restraint_ratio"]), r["deflection_rule"], r["depth_cap"])].append(label_by_id[r["id"]]["status"])
        for (rr, rule, cap) in sorted(cells, key=lambda c: (c[0], c[1], -1 if c[2] == "none" else int(c[2]))):
            st = Counter(cells[(rr, rule, cap)])
            n = len(cells[(rr, rule, cap)])
            t2.append({"set": sname, "restraint_ratio": repr(rr), "deflection_rule": rule, "depth_cap": cap, "n": n,
                       "n_abstain": n - st["feasible"], "abstain_rate": f4((n - st["feasible"]) / n),
                       "abstain_code": st["abstain_code"], "abstain_depth": st["abstain_depth"]})
    write_rows(tdir / "audit_cells.csv", t2, list(t2[0]))

    # ---- table 3: abstention by span and factored load bin (training pool), per depth cap
    t3 = []
    for cap in ("none", "700", "800", "900"):
        for i in range(len(L_EDGES) - 1):
            for j in range(len(W_EDGES) - 1):
                sel = []
                for r in rows_by_set["train"]:
                    L, w = float(r["span"]), float(r["w_factored"])
                    inL = L_EDGES[i] <= L < L_EDGES[i + 1] or (i == len(L_EDGES) - 2 and L == L_EDGES[-1])
                    inW = W_EDGES[j] <= w < W_EDGES[j + 1] or (j == len(W_EDGES) - 2 and w == W_EDGES[-1])
                    if r["depth_cap"] == cap and inL and inW:
                        sel.append(label_by_id[r["id"]]["status"] != "feasible")
                t3.append({"depth_cap": cap, "span_from": f"{L_EDGES[i]:.0f}", "span_to": f"{L_EDGES[i + 1]:.0f}",
                           "w_from": f"{W_EDGES[j]:.0f}", "w_to": f"{W_EDGES[j + 1]:.0f}", "n": len(sel),
                           "n_abstain": sum(sel), "abstain_rate": f4(sum(sel) / len(sel)) if sel else ""})
    write_rows(tdir / "audit_span_load_bins.csv", t3, list(t3[0]))

    # ---- table 4: coverage and shift of each set against the training ranges
    ranges = {"span": S.SPAN, "width": S.WIDTH, "dead": S.DEAD, "live": S.LIVE, "w_factored": S.W_BOX}
    t4 = []
    for sname in SET_ORDER:
        rs = rows_by_set[sname]
        for p, (lo, hi) in ranges.items():
            v = np.array([float(r[p]) for r in rs])
            out = int(((v < lo) | (v > hi)).sum())
            t4.append({"set": sname, "parameter": p, "min": f"{v.min():.4f}", "max": f"{v.max():.4f}",
                       "train_range": f"{lo:g}-{hi:g}", "n_outside_train_range": out, "share_outside": f4(out / len(v))})
        rv = sorted({float(r["restraint_ratio"]) for r in rs})
        t4.append({"set": sname, "parameter": "restraint_ratio", "min": f"{rv[0]:.4f}", "max": f"{rv[-1]:.4f}",
                   "train_range": "values 0, 0.25, 0.5, 1",
                   "n_outside_train_range": sum(float(r["restraint_ratio"]) not in S.RESTRAINT_TRAIN for r in rs),
                   "share_outside": f4(sum(float(r["restraint_ratio"]) not in S.RESTRAINT_TRAIN for r in rs) / len(rs))})
        t4.append({"set": sname, "parameter": "in_hole", "min": "", "max": "", "train_range": "excluded from training",
                   "n_outside_train_range": sum(S.in_hole(float(r["span"]), float(r["w_factored"])) for r in rs),
                   "share_outside": f4(sum(S.in_hole(float(r["span"]), float(r["w_factored"])) for r in rs) / len(rs))})
        t4.append({"set": sname, "parameter": "held_out_cell", "min": "", "max": "", "train_range": "excluded from training",
                   "n_outside_train_range": sum((float(r["restraint_ratio"]), r["deflection_rule"], S.cap_from_str(r["depth_cap"]))
                                                in held for r in rs),
                   "share_outside": f4(sum((float(r["restraint_ratio"]), r["deflection_rule"], S.cap_from_str(r["depth_cap"]))
                                           in held for r in rs) / len(rs))})
    write_rows(tdir / "audit_coverage.csv", t4, list(t4[0]))

    # ---- table 5: reference case at each training restraint value
    t5 = []
    for r in gen["reference"]:
        lab = label_by_id[r["id"]]
        exp = EXPECTED_REF[float(r["restraint_ratio"])]
        t5.append({"id": r["id"], "restraint_ratio": r["restraint_ratio"], "optimum": lab["optimum_name"],
                   "mass_kg_m": lab["mass_kg_m"], "expected": exp, "match": int(lab["optimum_name"] == exp),
                   "optimum_Cplus": plus_by_id[r["id"]]["optimum_name"]})
    write_rows(tdir / "audit_reference.csv", t5, list(t5[0]))

    # ---- table 8: set C+ (107 sections) against C
    t8 = []
    for sname in SET_ORDER:
        rs = rows_by_set[sname]
        feas = [r for r in rs if label_by_id[r["id"]]["status"] == "feasible"]
        lighter = sum(1 for r in feas if plus_by_id[r["id"]]["status"] == "feasible"
                      and float(plus_by_id[r["id"]]["mass_kg_m"]) < float(label_by_id[r["id"]]["mass_kg_m"]))
        t8.append({"set": sname, "n": len(rs), "abstain_C": len(rs) - len(feas),
                   "abstain_Cplus": sum(plus_by_id[r["id"]]["status"] != "feasible" for r in rs),
                   "feasible_only_in_Cplus": sum(1 for r in rs if label_by_id[r["id"]]["status"] != "feasible"
                                                 and plus_by_id[r["id"]]["status"] == "feasible"),
                   "optimum_lighter_in_Cplus": lighter, "share_lighter": f4(lighter / len(feas)) if feas else ""})
    write_rows(tdir / "audit_cplus.csv", t8, list(t8[0]))

    # ---- table 6: audit rules
    tr = {r["set"]: r for r in t1}["train"]
    cell_rates = [1.0 - float(c["abstain_rate"]) for c in t2 if c["set"] == "train"]
    n_dup = sum(c - 1 for c in Counter(tuple(r[k] for k in S.COLUMNS[2:9]) for f in SPLIT_FILES for r in gen[f]).values())
    t6 = [
        {"rule": "R1", "description": "guard: training-pool abstention share", "value": tr["abstain_rate"], "threshold": f"<= {RULE_ABSTAIN_MAX}",
         "pass": int(float(tr["abstain_rate"]) <= RULE_ABSTAIN_MAX)},
        {"rule": "R2", "description": "guard: smallest feasible share over the 40 training cells", "value": f4(min(cell_rates)),
         "threshold": f">= {RULE_CELL_FEASIBLE_MIN}", "pass": int(min(cell_rates) >= RULE_CELL_FEASIBLE_MIN)},
        {"rule": "R3", "description": "reference optima match the verification record (4 restraint values)",
         "value": str(sum(r["match"] for r in t5)), "threshold": "= 4", "pass": int(all(r["match"] for r in t5))},
        {"rule": "R4", "description": "duplicate contexts across all split files", "value": str(n_dup), "threshold": "= 0",
         "pass": int(n_dup == 0)},
        {"rule": "R5", "description": "held-out cells: contexts of train, val, t1, t2, t3 (E1-E3) in a held-out cell",
         "value": str(sum(int(c["n_outside_train_range"]) for c in t4 if c["parameter"] == "held_out_cell"
                          and c["set"] in ("train", "val", "t1", "t2", "t3-E1", "t3-E2", "t3-E3"))),
         "threshold": "= 0", "pass": 0},
    ]
    t6[-1]["pass"] = int(t6[-1]["value"] == "0")
    write_rows(tdir / "audit_rules.csv", t6, list(t6[0]))

    # ---- table 7: alternative depth caps on every 4th training-pool row (why 500 and 600 mm are not used)
    t7 = []
    sub = gen["train"][::4]
    for cap in ("500", "600", "650", "750"):
        for rr in S.RESTRAINT_TRAIN:
            sel = [r for r in sub if float(r["restraint_ratio"]) == rr]
            ab_n = 0
            for r in sel:
                e = K.evaluate_context(S.row_to_context({**r, "depth_cap": cap}))
                ab_n += int(not e["feasible"].any())
            t7.append({"depth_cap": cap, "restraint_ratio": repr(rr), "n": len(sel), "n_abstain": ab_n,
                       "abstain_rate": f4(ab_n / len(sel))})
    write_rows(tdir / "audit_cap_alternatives.csv", t7, list(t7[0]))

    # ---- table 9: effective marginals of the training pool (uniform draws, then rejection by w range, hole and held-out cells)
    tm = []
    tr_rows = rows_by_set["train"]
    cont = {p_: np.array([float(r[p_]) for r in tr_rows]) for p_ in ("span", "width", "dead", "live", "w_factored")}
    for p_, v in cont.items():
        for stat, val in (("mean", v.mean()), ("sd", v.std()), ("min", v.min()), ("p5", np.percentile(v, 5)),
                          ("p50", np.percentile(v, 50)), ("p95", np.percentile(v, 95)), ("max", v.max())):
            tm.append({"parameter": p_, "statistic": stat, "value": f"{val:.4f}"})
    for a_, b_ in (("width", "dead"), ("width", "live"), ("dead", "live")):
        tm.append({"parameter": f"{a_},{b_}", "statistic": "correlation", "value": f"{np.corrcoef(cont[a_], cont[b_])[0, 1]:.4f}"})
    for key, name in (("restraint_ratio", "restraint_ratio"), ("deflection_rule", "deflection_rule"), ("depth_cap", "depth_cap")):
        cnt = Counter(r[key] for r in tr_rows)
        for val in sorted(cnt):
            tm.append({"parameter": name, "statistic": f"share {val}", "value": f4(cnt[val] / len(tr_rows))})
    write_rows(tdir / "audit_marginals.csv", tm, list(tm[0]))
    marg_ = {(r["parameter"], r["statistic"]): r["value"] for r in tm}

    # ---- manifest
    lines = []
    for name in SPLIT_FILES + ["heldout_cells", "abstention_contexts"]:
        lines.append(f"{sha256_file(sdir / (name + '.csv'))}  {name}.csv")
    (sdir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")

    # ---- short document, generated so that every number comes from the tables
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "context_audit.md").write_text(render_doc(t1, t5, t6, t8, held, attempt, lines, {"workbook": sha256_file(workbook), "checker": sha256_file(ENV_FILE), "splits": sha256_file("src/ub_rl/splits.py")}, marg_), encoding="ascii", newline="\n")

    # ---- labels (not committed) and meta
    rdir = root / "results" / "audit"
    commit, dirty = git_info()
    hashes = {p: sha256_file(p) for p in HASHED_FILES}
    for fname in SPLIT_FILES:
        out = rdir / f"labels_{fname}.csv"
        write_rows(out, labels_by_file[fname], list(labels_by_file[fname][0]))
        meta = {"status": "complete", "script": "scripts/context_audit.py", "commit": commit, "working_tree_dirty": dirty,
                "environment_file": ENV_FILE, "environment_sha256": hashes[ENV_FILE], "file_sha256": hashes,
                "catalogue_sha256": sha256_file(workbook), "catalogue_rows": len(C), "split_file": f"data/splits/{fname}.csv",
                "split_sha256": sha256_file(sdir / f"{fname}.csv"), "n_contexts": len(labels_by_file[fname]),
                "checker_calls": len(labels_by_file[fname]), "python": platform.python_version(), "numpy": np.__version__}
        (rdir / f"labels_{fname}_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="ascii", newline="\n")
    return t6


def render_doc(t1, t5, t6, t8, held, attempt, manifest, prov, marg):
    L = ["# Context box and splits: feasibility audit (patch P6)", "",
         "Generated by `python scripts/context_audit.py`; the numbers are copied from `paper/tables/audit_*.csv`. "
         "Definitions and rules: `docs/spec.md`, Amendment A2. Preparation only: no RL training has been run.", "",
         "## Provenance", "",
         f"- Catalogue workbook `UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx`, SHA-256 `{prov['workbook']}`",
         f"- `src/ub_rl/checker.py` (environment file), SHA-256 `{prov['checker']}`",
         f"- `src/ub_rl/splits.py`, SHA-256 `{prov['splits']}`",
         "- Who ran the audit and when: `docs/verification_record.md`, section P6.", "",
         "## Sets", "",
         "| Set | n | Feasible | Abstain | Abstain rate | No section passes the code checks | Feasible sections all deeper than the cap | Distinct optima |",
         "|---|---|---|---|---|---|---|---|"]
    for r in t1:
        L.append(f"| {r['set']} | {r['n']} | {r['n_feasible']} | {r['n_abstain']} | {r['abstain_rate']} | {r['abstain_code']} | "
                 f"{r['abstain_depth']} | {r['distinct_optima']} |")
    code = [f"{r['set']} ({r['abstain_code']})" for r in t1 if int(r["abstain_code"]) > 0]
    L += ["", "Abstention contexts are listed in `data/splits/abstention_contexts.csv`; none is removed from any split file. "
          "Contexts that no section can carry (code checks fail for every section, whatever the cap): " + (", ".join(code) or "none") +
          ". Results on every test set are reported on feasible contexts with n_feasible and n_abstain shown (A2, reporting rule).", "",
          "## Reference case by restraint ratio", "", "| Restraint ratio | Lightest feasible UB (C) | Expected (verification record) | Lightest in C+ (107 sections) |", "|---|---|---|---|"]
    for r in t5:
        L.append(f"| {r['restraint_ratio']} | {r['optimum']} | {r['expected']} | {r['optimum_Cplus']} |")
    L += ["", "## Effective distribution of the training pool", "",
          "Parameters are drawn uniformly and then rejected if the factored UDL is outside its range, the context lies in the hole, "
          "or its (restraint, rule, cap) cell is held out, so the marginals are not uniform. Full table: `paper/tables/audit_marginals.csv`.", "",
          "| Parameter | Mean | SD | p5 | p50 | p95 |", "|---|---|---|---|---|---|"]
    for p_ in ("span", "width", "dead", "live", "w_factored"):
        L.append(f"| {p_} | {float(marg[(p_, 'mean')]):.3f} | {float(marg[(p_, 'sd')]):.3f} | {float(marg[(p_, 'p5')]):.3f} | "
                 f"{float(marg[(p_, 'p50')]):.3f} | {float(marg[(p_, 'p95')]):.3f} |")
    L += ["", "Correlations: " + ", ".join(f"{k} {float(marg[(k, 'correlation')]):.3f}" for k in ("width,dead", "width,live", "dead,live")) + ".", "",
          "## Set C+ (107 sections) against C", "",
          "C is the primary catalogue. C+ adds the 16 rows the workbook marks \"+\" (additional to BS EN 10365); no rule for their stock "
          "availability is recorded (spec sections 4 and 15), so C+ is a sensitivity check only.", "",
          "| Set | Abstain in C | Abstain in C+ | Feasible only in C+ | Optimum lighter in C+ | Share of feasible |", "|---|---|---|---|---|---|"]
    for r in t8:
        L.append(f"| {r['set']} | {r['abstain_C']} | {r['abstain_Cplus']} | {r['feasible_only_in_Cplus']} | "
                 f"{r['optimum_lighter_in_Cplus']} | {r['share_lighter']} |")
    r1 = {r["rule"]: r for r in t6}
    L += ["", "## Audit rules (A2)", "",
          f"R1 and R2 are regression guards: they were fixed after the first audit and the observed values (R1 {r1['R1']['value']}, "
          f"R2 {r1['R2']['value']}) are far from their thresholds, so they cannot fail on this box. R3 to R5 are the substantive checks.", "",
          "| Rule | Description | Value | Threshold | Pass |", "|---|---|---|---|---|"]
    for r in t6:
        L.append(f"| {r['rule']} | {r['description']} | {r['value']} | {r['threshold']} | {'yes' if int(r['pass']) else 'NO'} |")
    L += ["", "## Held-out cells for T4-A (seed 506, draw %d)" % attempt, "", "| Restraint ratio | Deflection rule | Depth cap |", "|---|---|---|"]
    for r, rule, cap in held:
        L.append(f"| {r:g} | {rule} | {S._cap_str(cap)} |")
    L += ["", "## File hashes (SHA-256)", "", "```"] + manifest + ["```", "",
          "Other tables: `audit_cplus.csv` (the 107-section catalogue C+ against C), `audit_cap_alternatives.csv` (abstention with the caps 500, 600, 650, 750 mm that are not used), `audit_cells.csv` (abstention by restraint, rule and cap), `audit_span_load_bins.csv` (by span and load bin), "
          "`audit_coverage.csv` (ranges of each set against the training ranges), `audit_cplus.csv` (C+ against C). "
          "The v1.2 sub-study sets (`s12-*`, two parameters, full restraint) are in `data/splits/v12_substudy.csv`."]
    return "\n".join(L) + "\n"


def compare(tmp, workbook_unused=None):
    """Compare every committed output with the regenerated one."""
    names = [f"data/splits/{n}.csv" for n in SPLIT_FILES + ["heldout_cells", "abstention_contexts"]] + ["data/splits/SHA256SUMS",
             "docs/context_audit.md"] + [f"paper/tables/{p.name}" for p in sorted((Path(tmp) / "paper" / "tables").glob("audit_*.csv"))]
    bad = []
    for n in names:
        a, b = Path(n), Path(tmp) / n
        if not a.exists() or a.read_bytes() != b.read_bytes():
            bad.append(n)
    return names, bad


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    workbook = args[0] if args else DEFAULT_WORKBOOK
    if "--check" in sys.argv:
        with tempfile.TemporaryDirectory() as tmp:
            build(tmp, workbook)
            names, bad = compare(tmp)
        print(f"checked {len(names)} files; differing or missing: {bad if bad else 'none'}")
        sys.exit(1 if bad else 0)
    t6 = build(".", workbook)
    for r in t6:
        print(f"{r['rule']} {'pass' if int(r['pass']) else 'FAIL'}: {r['description']} = {r['value']} (threshold {r['threshold']})")
    print("wrote data/splits/, paper/tables/audit_*.csv, docs/context_audit.md, results/audit/")


if __name__ == "__main__":
    main()
