"""P12a pilots and V-only tuning under approved Amendment A7.

Experiment commands are explicit: ``pilot`` runs the three default configs at seeds 0-2;
``tune`` runs the 12 fixed configs per entry at seed 0; ``trigger`` evaluates D6; ``tables``
rebuilds the summary CSVs; and ``bench`` runs only small deterministic toy agents.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np

from . import baselines, splits
from .baselines import CountingChecker
from .catalogue import parse_workbook
from .checker import Checker
from .harness import ROOT, RunConfig, make_env, run
from .landscape import f1_distances

ENTRIES = ("f0_r1", "f1_r1", "f2_r3")
DRAW_SEED = 707
TUNING_SEED = 0
PILOT_SEEDS = (0, 1, 2)
TUNING_BUDGET = 3000
PILOT_BUDGET = 10000
EXPECTED_VAL_FEASIBLE = 796
EXPECTED_FIRST100_FEASIBLE = 71
RESULT_ROOT = ROOT / "results" / "p12a"
DEFAULT_WORKBOOK = ROOT / "data" / "raw" / "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
EVAL_COLUMNS = ("index", "output", "feasible", "repaired", "repair_calls", "steps", "calls")

GRID_FIELDS = {
    "f0_r1": ("hidden", "lr", "batch_size", "normalize_advantage"),
    "f1_r1": ("hidden", "lr", "epsilon", "n", "target_sync", "replay_size", "alpha", "batch_size"),
    "f2_r3": ("hidden", "lr", "logz_lr", "batch_size", "beta"),
}
GRID_VALUES = {
    "hidden": ([32, 32], [64, 64], [128, 128]),
    "lr": (0.01, 0.003, 0.001, 0.0003),
    "f0_batch_size": (32, 64, 128),
    "normalize_advantage": (False, True),
    "f1_lr": (0.001, 0.0003),
    "epsilon": (0.05, 0.1, 0.2),
    "n": (1, 3, 5),
    "target_sync": (50, 100, 200),
    "replay_size": (5000, 10000, 20000),
    "alpha": (0.4, 0.6, 0.8),
    "f1_batch_size": (32, 64),
    "logz_lr": (0.003, 0.001, 0.0003),
    "f2_batch_size": (32, 64, 128),
    "beta": (25, 50, 100),
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _json_sha256(value) -> str:
    raw = json.dumps(value, sort_keys=True, allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _atomic_csv(path: Path, rows, columns) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=columns, lineterminator="\n", extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _atomic_npz(path: Path, **arrays) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".npz", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            np.savez_compressed(f, **arrays)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _load_default(entry: str) -> dict:
    return json.loads((ROOT / "configs" / f"{entry}.json").read_text(encoding="utf-8"))


def _grid_values(entry: str):
    values = []
    for field in GRID_FIELDS[entry]:
        if field == "hidden":
            pool = GRID_VALUES["hidden"]
        elif field == "lr" and entry == "f1_r1":
            pool = GRID_VALUES["f1_lr"]
        elif field == "lr":
            pool = GRID_VALUES["lr"]
        elif field == "batch_size":
            pool = GRID_VALUES[f"{entry[:2]}_batch_size"]
        else:
            pool = GRID_VALUES[field]
        values.append(pool)
    return tuple(values)


def _put_grid_value(cfg: dict, entry: str, field: str, value) -> None:
    if field in ("hidden", "lr"):
        cfg["network"][field] = list(value) if field == "hidden" else value
    elif entry == "f0_r1":
        cfg.setdefault("f0", {})[field] = value
    elif entry == "f1_r1":
        cfg.setdefault("f1", {})[field] = value
    else:
        cfg.setdefault("f2", {})[field] = value


def _grid_key(cfg: dict, entry: str) -> tuple:
    values = []
    for field in GRID_FIELDS[entry]:
        if field in ("hidden", "lr"):
            v = cfg["network"][field]
        elif entry == "f0_r1":
            v = cfg["f0"][field]
        elif entry == "f1_r1":
            v = cfg["f1"][field]
        else:
            v = cfg["f2"][field]
        values.append(tuple(v) if field == "hidden" else v)
    return tuple(values)


def tuning_configs(entry: str) -> list[dict]:
    """Slot 1 is the default; slots 2-12 are a deterministic sample of other grid cells.

    Cartesian-product order follows the field order in ``GRID_FIELDS`` and value order in
    ``GRID_VALUES``. Sampling is from the grid with the default removed, so there are no duplicates.
    """
    if entry not in ENTRIES:
        raise ValueError(f"unknown entry {entry!r}")
    default = _load_default(entry)
    grid = []
    for combo in itertools.product(*_grid_values(entry)):
        candidate = deepcopy(default)
        for field, value in zip(GRID_FIELDS[entry], combo):
            _put_grid_value(candidate, entry, field, value)
        grid.append(candidate)
    default_key = _grid_key(default, entry)
    pool = [candidate for candidate in grid if _grid_key(candidate, entry) != default_key]
    if len(pool) < 11:
        raise RuntimeError(f"{entry} grid has fewer than 11 non-default configurations")
    selected = [default] + random.Random(DRAW_SEED).sample(pool, 11)
    out = []
    for slot, cfg in enumerate(selected, 1):
        cfg = deepcopy(cfg)
        cfg["seed"] = TUNING_SEED
        cfg["budget"] = TUNING_BUDGET
        cfg["checkpoints"] = [1600 if entry == "f1_r1" else 2000]
        cfg["budget_includes_eval"] = True
        cfg["eval_repair"] = False
        cfg["eval_contexts"] = "val:100" if entry == "f1_r1" else "val"
        if entry == "f1_r1":
            cfg.setdefault("f1", {})["beta_anneal_steps"] = TUNING_BUDGET
        out.append(cfg)
    return out


def pilot_config(entry: str, seed: int) -> dict:
    if entry not in ENTRIES or seed not in PILOT_SEEDS:
        raise ValueError("pilot requires a registered entry and seed 0, 1, or 2")
    cfg = _load_default(entry)
    cfg.update({"seed": int(seed), "budget": PILOT_BUDGET, "checkpoints": [PILOT_BUDGET],
                "budget_includes_eval": False, "eval_repair": False,
                "eval_contexts": "val:100" if entry == "f1_r1" else "val"})
    return cfg


def benchmark_config(entry: str, smoke: bool = False) -> dict:
    cfg = _load_default(entry)
    budget = 20 if smoke else 200
    n_eval = 2 if smoke else 20
    cfg.update({"seed": 0, "budget": budget, "checkpoints": [budget],
                "budget_includes_eval": False, "eval_repair": False,
                "eval_contexts": f"val:{n_eval}"})
    return cfg


def _split_hash(split_name="val") -> str:
    split_path = ROOT / "data" / "splits" / f"{split_name}.csv"
    sums_path = ROOT / "data" / "splits" / "SHA256SUMS"
    expected = {}
    for line in sums_path.read_text(encoding="ascii").splitlines():
        if line.strip():
            digest, filename = line.split("  ", 1)
            expected[filename] = digest
    actual = _sha256(split_path)
    if expected.get(f"{split_name}.csv") != actual:
        raise RuntimeError(f"{split_name}.csv does not match data/splits/SHA256SUMS")
    return actual


def _catalogue_and_checker():
    cat, _ = parse_workbook(DEFAULT_WORKBOOK)
    c = cat.mass_ordered(False)
    return c, Checker(c)


def _cache_inputs(val_sha: str) -> dict:
    return {"split_sha256": val_sha,
            "catalogue_workbook_sha256": _sha256(DEFAULT_WORKBOOK),
            "checker_sha256": _sha256(ROOT / "src" / "ub_rl" / "checker.py"),
            "context_sha256": _sha256(ROOT / "src" / "ub_rl" / "context.py"),
            "config_sha256": _sha256(ROOT / "src" / "ub_rl" / "config.py")}


def load_or_compute_val_masks(checker=None) -> tuple[list[dict], list, np.ndarray, dict]:
    """Load validated 91-section masks or enumerate them on V, then cache them atomically."""
    val_sha = _split_hash("val")
    rows, contexts = splits.load_split("val", root=ROOT / "data" / "splits")
    if checker is None:
        _, checker = _catalogue_and_checker()
    inputs = _cache_inputs(val_sha)
    cache_npz = RESULT_ROOT / "cache" / "val_feasibility.npz"
    cache_meta = RESULT_ROOT / "cache" / "val_feasibility_meta.json"
    if cache_npz.is_file() and cache_meta.is_file():
        try:
            meta = json.loads(cache_meta.read_text(encoding="utf-8"))
            if meta.get("status") == "complete" and meta.get("inputs") == inputs \
                    and meta.get("mask_sha256") == _sha256(cache_npz):
                with np.load(cache_npz, allow_pickle=False) as data:
                    ids = data["ids"].astype(str).tolist()
                    masks = data["masks"].astype(bool)
                if ids == [r["id"] for r in rows] and masks.shape == (len(rows), checker.n):
                    return rows, contexts, masks, {"kind": "p12a_mask_cache", **inputs}
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass  # invalid or partial caches are ignored and rebuilt from the checker

    p6_labels_path = RESULT_ROOT.parent / "audit" / "labels_val.csv"
    p6_meta_path = p6_labels_path.with_name("labels_val_meta.json")
    p6_labels = None
    p6_label_digest = None
    if p6_labels_path.is_file() and p6_meta_path.is_file():
        p6_meta = json.loads(p6_meta_path.read_text(encoding="utf-8"))
        if (p6_meta.get("status") != "complete" or p6_meta.get("split_sha256") != val_sha
                or p6_meta.get("catalogue_sha256") != inputs["catalogue_workbook_sha256"]
                or p6_meta.get("n_contexts") != len(rows)
                or p6_meta.get("file_sha256", {}).get("src/ub_rl/checker.py") != inputs["checker_sha256"]):
            raise RuntimeError("P6 labels_val.csv metadata does not match the current validation inputs")
        with open(p6_labels_path, newline="", encoding="ascii") as f:
            p6_labels = list(csv.DictReader(f))
        if [r.get("id") for r in p6_labels] != [r["id"] for r in rows]:
            raise RuntimeError("P6 labels_val.csv context IDs/order do not match val.csv")
        p6_label_digest = _sha256(p6_labels_path)

    masks = np.empty((len(contexts), checker.n), dtype=bool)
    opts = np.empty(len(contexts), dtype=np.int64)
    for i, ctx in enumerate(contexts):
        masks[i] = checker.evaluate_context(ctx)["feasible"]
        opts[i] = int(np.argmax(masks[i])) if masks[i].any() else -1
    if p6_labels is not None:
        for i, label in enumerate(p6_labels):
            if int(label["optimum_index"]) != int(opts[i]) \
                    or int(label["n_feasible"]) != int(masks[i].sum()):
                raise RuntimeError(f"P6 label mismatch at val row {i}")
    _atomic_npz(cache_npz, ids=np.asarray([r["id"] for r in rows]), masks=masks, optimum=opts)
    source = {"kind": "checker_full_mask_enumeration", **inputs}
    if p6_label_digest:
        source["p6_labels_sha256"] = p6_label_digest
    _atomic_json(cache_meta, {"status": "complete", "inputs": inputs,
                              "mask_sha256": _sha256(cache_npz), "source": source,
                              "n_contexts": len(rows), "n_sections": checker.n})
    return rows, contexts, masks, source


def representativeness_report(rows, contexts, masks, checker) -> dict:
    if len(rows) != 1000 or masks.shape != (1000, checker.n):
        raise ValueError("A7 representativeness check requires the complete 1,000-row val split")
    feasible = masks.any(axis=1)
    first = feasible[:100]
    if int(first.sum()) != EXPECTED_FIRST100_FEASIBLE:
        raise RuntimeError("A7 preflight failed: first 100 val contexts do not contain 71 feasible cases")
    if int(feasible.sum()) != EXPECTED_VAL_FEASIBLE:
        raise RuntimeError("validation feasibility count differs from the registered 796/1,000")
    distances = f1_distances(checker.cat.series, checker.h)
    trial = np.asarray([baselines.trial_index(checker, ctx) for ctx in contexts], dtype=np.int64)
    optimum = np.where(feasible, masks.argmax(axis=1), -1)
    dist = [int(distances[trial[i], optimum[i]]) for i in range(len(contexts)) if feasible[i]]

    def distribution(values):
        counts = {}
        for value in values:
            key = str(int(value))
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: int(kv[0])))

    first_dist = [int(distances[trial[i], optimum[i]]) for i in range(100) if first[i]]
    return {"n_val": 1000, "n_feasible_val": int(feasible.sum()),
            "val_feasible_share": float(feasible.mean()), "n_first100": 100,
            "n_feasible_first100": int(first.sum()),
            "first100_feasible_share": float(first.mean()),
            "trial_index_distribution_val": distribution(trial),
            "trial_index_distribution_first100": distribution(trial[:100]),
            "f1_distance_distribution_val_feasible": distribution(dist),
            "f1_distance_distribution_first100_feasible": distribution(first_dist),
            "mean_f1_distance_val_feasible": float(np.mean(dist)),
            "mean_f1_distance_first100_feasible": float(np.mean(first_dist))}


def _cfg_and_sha(config: dict) -> tuple[RunConfig, str]:
    cfg = RunConfig.from_dict(config)
    canonical = asdict(cfg)
    return cfg, _json_sha256(canonical)


def _safe_run_dir(path: Path) -> Path:
    root = RESULT_ROOT.resolve()
    resolved = path.resolve()
    if resolved == root or not resolved.is_relative_to(root):
        raise RuntimeError(f"refusing to clean output outside {root}: {resolved}")
    if path.is_symlink():
        raise RuntimeError(f"refusing to use symlink output directory: {path}")
    return resolved


def _clean_run_dir(path: Path) -> None:
    resolved = _safe_run_dir(path)
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)


def _read_eval_csv(path: Path) -> list[dict]:
    with open(path, newline="", encoding="ascii") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != EVAL_COLUMNS:
            raise RuntimeError(f"unexpected evaluation CSV schema in {path}")
        rows = list(reader)
    return [{k: int(v) for k, v in row.items()} for row in rows]


def offline_metrics(eval_rows: list[dict], masks: np.ndarray, masses: np.ndarray) -> dict:
    """A7 D5 raw metrics and offline repair derived from full enumeration masks."""
    if len(eval_rows) > len(masks):
        raise ValueError("evaluation rows exceed the validation mask set")
    feasible_contexts = 0
    raw_success = raw_gaps = 0
    repaired_success = repaired_gaps = abstentions = 0
    raw_gap_values, repaired_gap_values = [], []
    raw_feasible_by_ctx = []
    context_gaps = []
    for i, row in enumerate(eval_rows):
        ok = np.asarray(masks[i], dtype=bool)
        if not ok.any():
            continue
        feasible_contexts += 1
        optimum = int(np.argmax(ok))
        output = int(row["output"])
        if not 0 <= output < len(ok):
            raise ValueError(f"invalid section index in evaluation row {i}: {output}")
        raw_ok = bool(ok[output])
        if int(row["feasible"]) != int(raw_ok):
            raise RuntimeError(f"greedy verification and enumeration mask disagree at evaluation row {i}")
        if raw_ok:
            raw_success += 1
            raw_gap_values.append(100.0 * (float(masses[output]) / float(masses[optimum]) - 1.0))
        raw_feasible_by_ctx.append(int(row["feasible"]))

        if raw_ok:
            repaired = output
        else:
            candidates = np.flatnonzero(ok[output + 1:])
            repaired = output + 1 + int(candidates[0]) if candidates.size else -1
        if repaired >= 0:
            repaired_success += 1
            repaired_gap_values.append(100.0 * (float(masses[repaired]) / float(masses[optimum]) - 1.0))
        else:
            abstentions += 1
        context_gaps.append({"index": i, "optimum": optimum, "output": output,
                             "repaired": repaired, "raw_feasible": int(raw_ok)})
    if feasible_contexts == 0:
        raise RuntimeError("evaluation set contains no feasible contexts for metric denominators")
    raw_feasibility = raw_success / feasible_contexts
    repaired_feasibility = repaired_success / feasible_contexts
    return {"n_contexts": len(eval_rows), "n_feasible_contexts": feasible_contexts,
            "n_infeasible_contexts": len(eval_rows) - feasible_contexts,
            "raw_feasibility": raw_feasibility,
            "raw_mean_gap_pct": float(np.mean(raw_gap_values)) if raw_gap_values else None,
            "repaired_feasibility": repaired_feasibility,
            "offline_repaired_gap_pct": float(np.mean(repaired_gap_values)) if repaired_gap_values else None,
            "repair_successes": repaired_success, "repair_abstentions": abstentions,
            "mean_steps": float(np.mean([r["steps"] for r in eval_rows])) if eval_rows else 0.0,
            "mean_rollout_calls": float(np.mean([r["calls"] for r in eval_rows])) if eval_rows else 0.0,
            "offline_rows": context_gaps}


def select_entry(config_rows: list[dict]) -> dict:
    """Apply A7 D5. A non-default must clear the 0.5 percentage-point margin."""
    rows = sorted(config_rows, key=lambda r: int(r["slot"]))
    if len(rows) != 12 or int(rows[0]["slot"]) != 1:
        raise ValueError("selection requires all 12 configs with default in slot 1")
    incumbent = rows[0]["metrics"]
    if incumbent["offline_repaired_gap_pct"] is None:
        raise RuntimeError("incumbent has no offline repaired gap")
    passers = []
    for row in rows[1:]:
        m = row["metrics"]
        if (m["offline_repaired_gap_pct"] is not None
                and m["raw_feasibility"] >= incumbent["raw_feasibility"]
                and m["repaired_feasibility"] >= incumbent["repaired_feasibility"]
                and m["offline_repaired_gap_pct"] <= incumbent["offline_repaired_gap_pct"] - 0.5):
            passers.append(row)
    passing_slots = sorted(int(r["slot"]) for r in passers)
    if not passers:
        return {"selected_slot": 1, "selected_config_id": rows[0]["config_id"],
                "reason": "no candidate met A7 D5; incumbent retained", "passing_slots": []}
    best_raw = max(r["metrics"]["raw_feasibility"] for r in passers)
    passers = [r for r in passers if r["metrics"]["raw_feasibility"] == best_raw]
    best_gap = min(r["metrics"]["offline_repaired_gap_pct"] for r in passers)
    passers = [r for r in passers if r["metrics"]["offline_repaired_gap_pct"] == best_gap]
    chosen = min(passers, key=lambda r: int(r["slot"]))
    return {"selected_slot": int(chosen["slot"]), "selected_config_id": chosen["config_id"],
            "reason": "highest raw feasibility, then lowest offline repaired gap",
            "passing_slots": passing_slots}


def trigger_decision(pilot_rows: list[dict], selected_f1: dict) -> dict:
    """A7 D6: trigger R-C only if no entry clears 0.99 in each of its three pilot seeds."""
    by_entry = {e: [r for r in pilot_rows if r["entry"] == e] for e in ENTRIES}
    reached = {}
    for entry, rows in by_entry.items():
        if sorted(int(r["seed"]) for r in rows) != list(PILOT_SEEDS):
            raise ValueError(f"trigger needs all pilot seeds for {entry}")
        reached[entry] = all(float(r["metrics"]["raw_feasibility"]) >= 0.99 for r in rows)
    run_rc = not any(reached.values())
    return {"run_rc": run_rc, "entries_reaching_bar": reached,
            "selected_f1_config_id": selected_f1["selected_config_id"] if run_rc else None,
            "selected_f1_slot": selected_f1["selected_slot"] if run_rc else None,
            "threshold": 0.99, "pilot_seeds": list(PILOT_SEEDS)}


def _manifest_path() -> Path:
    return RESULT_ROOT / "manifest.json"


def _load_manifest(val_sha: str) -> dict:
    path = _manifest_path()
    if path.is_file():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") == 1 and manifest.get("eval_split_sha256") == val_sha:
                manifest.setdefault("runs", {})
                return manifest
        except (OSError, json.JSONDecodeError):
            pass
    return {"schema_version": 1, "eval_split_file": "data/splits/val.csv",
            "eval_split_sha256": val_sha, "runs": {}}


def _config_id(kind: str, entry: str, seed: int | None = None, slot: int | None = None) -> str:
    if kind == "pilot":
        return f"pilot/{entry}/seed{seed}"
    return f"tune/{entry}/cfg{slot:02d}"


def _expected_artifacts(outdir: Path, cfg: RunConfig) -> list[Path]:
    if len(cfg.checkpoints) != 1:
        raise ValueError("P12a runs require exactly one checkpoint")
    threshold = cfg.checkpoints[0]
    return [outdir / "run_meta.json", outdir / "run.jsonl",
            outdir / f"checkpoint_{threshold}.pt", outdir / f"eval_{threshold}.csv"]


def _artifact_seal(outdir: Path, cfg: RunConfig, config_sha: str, eval_sha: str) -> dict:
    names = ["run_meta.json", "run.jsonl", f"checkpoint_{cfg.checkpoints[0]}.pt",
             f"eval_{cfg.checkpoints[0]}.csv"]
    return {"status": "complete", "config_sha256": config_sha,
            "eval_split_sha256": eval_sha,
            "artifacts": {name: _sha256(outdir / name) for name in names}}


def _validate_seal(outdir: Path, cfg: RunConfig, config_sha: str, eval_sha: str) -> None:
    seal_path = outdir / "p12a_artifacts.json"
    if not seal_path.is_file():
        raise RuntimeError("P12a artifact seal is missing")
    recorded = json.loads(seal_path.read_text(encoding="utf-8"))
    if recorded != _artifact_seal(outdir, cfg, config_sha, eval_sha):
        raise RuntimeError("P12a artifact seal does not match saved run files")


def _validate_complete(outdir: Path, cfg: RunConfig, config_sha: str, eval_sha: str) -> tuple[dict, list[dict]]:
    artifacts = _expected_artifacts(outdir, cfg)
    if not all(p.is_file() for p in artifacts):
        raise RuntimeError("completed run is missing one or more expected artifacts")
    meta = json.loads((outdir / "run_meta.json").read_text(encoding="utf-8"))
    expected_harness_sha = _sha256(ROOT / "src" / "ub_rl" / "harness.py")
    expected_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    checks = {"status": "complete", "config_sha256": config_sha,
              "eval_split_file": "data/splits/val.csv", "eval_split_sha256": eval_sha,
              "harness_sha256": expected_harness_sha,
              "checker_sha256": _sha256(ROOT / "src" / "ub_rl" / "checker.py"),
              "environment_sha256": _sha256(ROOT / "src" / "ub_rl" / "envs.py"),
              "agents_sha256": _sha256(ROOT / "src" / "ub_rl" / "agents.py"),
              "replay_sha256": _sha256(ROOT / "src" / "ub_rl" / "replay.py"),
              "train_split_sha256": _split_hash("train"),
              "catalogue_workbook_sha256": _sha256(DEFAULT_WORKBOOK),
              "commit": expected_commit, "eval_repair": cfg.eval_repair}
    for key, expected in checks.items():
        actual = meta.get(key)
        if actual != expected:
            raise RuntimeError(f"run metadata mismatch for {key}: {actual!r} != {expected!r}")
    rows = _read_eval_csv(outdir / f"eval_{cfg.checkpoints[0]}.csv")
    expected_n = 100 if cfg.entry == "f1_r1" else 1000
    if len(rows) != expected_n or [r["index"] for r in rows] != list(range(expected_n)):
        raise RuntimeError("evaluation CSV row count/order does not match the A7 set")
    if any(r["repair_calls"] != 0 or r["repaired"] != r["output"] for r in rows):
        raise RuntimeError("A7 P12a evaluation unexpectedly executed repair")
    run_events = [json.loads(line) for line in (outdir / "run.jsonl").read_text().splitlines() if line]
    if not run_events or run_events[-1].get("event") != "summary":
        raise RuntimeError("run log has no final summary event")
    if meta.get("total_calls") != sum(meta.get(k, 0) for k in
                                       ("training_calls", "eval_calls", "verification_calls", "repair_calls")):
        raise RuntimeError("meta total_calls does not equal its component counters")
    if cfg.budget_includes_eval:
        if meta.get("unused_calls") != cfg.budget - meta["total_calls"] or meta["total_calls"] > cfg.budget:
            raise RuntimeError("tuning run violates the total call budget")
    elif meta.get("training_calls") != cfg.budget:
        raise RuntimeError("pilot did not reach its full registered training-call budget")
    checkpoints = meta.get("checkpoints", [])
    cp_calls = checkpoints[0].get("training_calls") if len(checkpoints) == 1 else None
    max_cp_overshoot = 1 if cfg.entry == "f1_r1" and cfg.budget_includes_eval else 0
    if (len(checkpoints) != 1 or checkpoints[0].get("threshold") != cfg.checkpoints[0]
            or not isinstance(cp_calls, int)
            or not cfg.checkpoints[0] <= cp_calls <= cfg.checkpoints[0] + max_cp_overshoot):
        raise RuntimeError("checkpoint did not fire at its configured threshold")
    return meta, rows


def _run_subprocess(config: dict, outdir: Path) -> None:
    cfg_path = None
    RESULT_ROOT.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="p12a-config-", suffix=".json", dir=RESULT_ROOT)
    cfg_path = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(config, f, indent=2, sort_keys=True)
            f.write("\n")
        env = os.environ.copy()
        src = str(ROOT / "src")
        env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[key] = "1"
        proc = subprocess.run([sys.executable, "-m", "ub_rl.harness", str(cfg_path),
                               "--outdir", str(outdir)], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        if proc.returncode:
            detail = (proc.stderr or proc.stdout)[-4000:]
            raise RuntimeError(f"harness subprocess exited {proc.returncode}: {detail}")
    finally:
        cfg_path.unlink(missing_ok=True)


def _run_one(kind: str, entry: str, config: dict, run_id: str, outdir: Path,
             manifest: dict, masks: np.ndarray, masses: np.ndarray, eval_sha: str,
             seed=None, slot=None) -> dict:
    cfg, config_sha = _cfg_and_sha(config)
    previous = manifest["runs"].get(run_id, {})
    try:
        if (previous.get("status") == "complete" or (outdir / "run_meta.json").is_file()):
            try:
                meta, eval_rows = _validate_complete(outdir, cfg, config_sha, eval_sha)
                _validate_seal(outdir, cfg, config_sha, eval_sha)
                metrics = offline_metrics(eval_rows, masks, masses)
                previous = {"status": "complete", "run_id": run_id, "kind": kind,
                            "entry": entry, "seed": seed, "slot": slot, "config": config,
                            "config_sha256": config_sha, "metrics": metrics,
                            "total_calls": meta["total_calls"],
                            "training_calls": meta["training_calls"],
                            "eval_calls": meta["eval_calls"], "unused_calls": meta["unused_calls"],
                            "outdir": str(outdir.relative_to(ROOT))}
                manifest["runs"][run_id] = previous
                _atomic_json(_manifest_path(), manifest)
                return previous
            except (OSError, ValueError, KeyError, RuntimeError, json.JSONDecodeError):
                pass  # stale/corrupt completion marker: discard this owned run directory and rerun
        _clean_run_dir(outdir)
        _run_subprocess(config, outdir)
        meta, eval_rows = _validate_complete(outdir, cfg, config_sha, eval_sha)
        _atomic_json(outdir / "p12a_artifacts.json", _artifact_seal(outdir, cfg, config_sha, eval_sha))
        metrics = offline_metrics(eval_rows, masks, masses)
        result = {"status": "complete", "run_id": run_id, "kind": kind, "entry": entry,
                  "seed": seed, "slot": slot, "config": config, "config_sha256": config_sha,
                  "metrics": metrics, "total_calls": meta["total_calls"],
                  "training_calls": meta["training_calls"], "eval_calls": meta["eval_calls"],
                  "unused_calls": meta["unused_calls"], "outdir": str(outdir.relative_to(ROOT))}
    except Exception as exc:
        result = {"status": "failed", "run_id": run_id, "kind": kind, "entry": entry,
                  "seed": seed, "slot": slot, "config": config, "config_sha256": config_sha,
                  "error": str(exc), "outdir": str(outdir.relative_to(ROOT))}
    manifest["runs"][run_id] = result
    _atomic_json(_manifest_path(), manifest)
    return result


def _prepare_manifest(kind: str, planned: list[tuple[str, str, dict, int | None, int | None]],
                      eval_sha: str, representativeness: dict, mask_source: dict) -> dict:
    manifest = _load_manifest(eval_sha)
    manifest["protocol"] = "approved Amendment A7"
    manifest["eval_split_file"] = "data/splits/val.csv"
    manifest["eval_split_sha256"] = eval_sha
    manifest["mask_source"] = mask_source
    manifest["representativeness"] = representativeness
    manifest["python"] = platform.python_version()
    manifest["runs"].setdefault("planned", {})
    for run_id, run_kind, config, seed, slot in planned:
        cfg, config_sha = _cfg_and_sha(config)
        manifest["runs"].setdefault(run_id, {"status": "planned", "run_id": run_id,
                                              "kind": run_kind, "entry": cfg.entry,
                                              "seed": seed, "slot": slot, "config": config,
                                              "config_sha256": config_sha})
    _atomic_json(_manifest_path(), manifest)
    return manifest


def run_experiments(kind: str) -> dict:
    if kind not in ("pilot", "tune"):
        raise ValueError(kind)
    eval_sha = _split_hash("val")
    c, checker = _catalogue_and_checker()
    rows, contexts, masks, source = load_or_compute_val_masks(checker)
    represent = representativeness_report(rows, contexts, masks, checker)
    if represent["n_feasible_first100"] != EXPECTED_FIRST100_FEASIBLE:
        raise RuntimeError("A7 first-100 feasibility gate failed; no runs started")
    planned = []
    if kind == "pilot":
        for entry in ENTRIES:
            for seed in PILOT_SEEDS:
                cfg = pilot_config(entry, seed)
                planned.append((_config_id("pilot", entry, seed=seed), "pilot", cfg, seed, None))
    else:
        for entry in ENTRIES:
            for slot, cfg in enumerate(tuning_configs(entry), 1):
                planned.append((_config_id("tune", entry, slot=slot), "tune", cfg, TUNING_SEED, slot))
    manifest = _prepare_manifest(kind, planned, eval_sha, represent, source)
    failures = []
    for run_id, run_kind, config, seed, slot in planned:
        entry = config["entry"]
        if run_kind == "pilot":
            outdir = RESULT_ROOT / "pilot" / entry / f"seed{seed}"
        else:
            outdir = RESULT_ROOT / "tune" / entry / f"cfg{slot:02d}"
        result = _run_one(run_kind, entry, config, run_id, outdir, manifest,
                          masks, c["m"], eval_sha, seed=seed, slot=slot)
        if result["status"] != "complete":
            failures.append(run_id)
    if kind == "tune" and not failures:
        manifest["selection"] = select_all_entries(manifest)
        _atomic_json(_manifest_path(), manifest)
    if failures:
        raise RuntimeError(f"{kind} completed with failed runs: {failures}; inspect { _manifest_path() }")
    return manifest


def select_all_entries(manifest: dict) -> dict:
    selections = {}
    for entry in ENTRIES:
        rows = []
        for slot in range(1, 13):
            run = manifest["runs"].get(_config_id("tune", entry, slot=slot))
            if not run or run.get("status") != "complete":
                raise RuntimeError(f"missing completed tuning config {entry} slot {slot}")
            rows.append({"config_id": run["run_id"], "slot": slot, "metrics": run["metrics"],
                         "config": run["config"]})
        selections[entry] = select_entry(rows)
    return selections


def make_trigger(manifest: dict) -> dict:
    if "selection" not in manifest:
        manifest["selection"] = select_all_entries(manifest)
    pilots = []
    for entry in ENTRIES:
        for seed in PILOT_SEEDS:
            run = manifest["runs"].get(_config_id("pilot", entry, seed=seed))
            if not run or run.get("status") != "complete":
                raise RuntimeError(f"missing completed pilot {entry} seed {seed}")
            pilots.append(run)
    decision = trigger_decision(pilots, manifest["selection"]["f1_r1"])
    decision["eval_split_sha256"] = manifest["eval_split_sha256"]
    _atomic_json(RESULT_ROOT / "trigger.json", decision)
    _atomic_json(_manifest_path(), manifest)
    _atomic_csv(ROOT / "paper" / "tables" / "p12a_trigger.csv", [decision],
                ("run_rc", "selected_f1_config_id", "selected_f1_slot", "threshold",
                 "pilot_seeds", "entries_reaching_bar", "eval_split_sha256"))
    return decision


def _pilot_table_rows(manifest: dict) -> list[dict]:
    out = []
    for entry in ENTRIES:
        for seed in PILOT_SEEDS:
            run = manifest["runs"].get(_config_id("pilot", entry, seed=seed))
            if run and run.get("status") == "complete":
                out.append(_flat_run(run))
    return out


def _tune_table_rows(manifest: dict) -> list[dict]:
    out = []
    for entry in ENTRIES:
        selection = manifest.get("selection", {}).get(entry, {})
        for slot in range(1, 13):
            run = manifest["runs"].get(_config_id("tune", entry, slot=slot))
            if run and run.get("status") == "complete":
                row = _flat_run(run)
                row["selected"] = int(selection.get("selected_slot") == slot)
                out.append(row)
    return out


def _flat_run(run: dict) -> dict:
    m = run["metrics"]
    return {"run_id": run["run_id"], "entry": run["entry"], "seed": run["seed"],
            "slot": run.get("slot", ""), "status": run["status"],
            "raw_feasibility": m["raw_feasibility"], "raw_mean_gap_pct": m["raw_mean_gap_pct"],
            "repaired_feasibility": m["repaired_feasibility"],
            "offline_repaired_gap_pct": m["offline_repaired_gap_pct"],
            "repair_successes": m["repair_successes"], "repair_abstentions": m["repair_abstentions"],
            "n_feasible_contexts": m["n_feasible_contexts"],
            "n_infeasible_contexts": m["n_infeasible_contexts"],
            "mean_steps": m["mean_steps"], "mean_rollout_calls": m["mean_rollout_calls"],
            "training_calls": run.get("training_calls", ""), "eval_calls": run.get("eval_calls", ""),
            "unused_calls": run.get("unused_calls", ""),
            "total_calls": run.get("total_calls", ""),
            "config": json.dumps(run["config"], sort_keys=True, separators=(",", ":"))}


def write_tables(manifest: dict) -> None:
    tune_complete = all(manifest["runs"].get(_config_id("tune", e, slot=s), {}).get("status") == "complete"
                        for e in ENTRIES for s in range(1, 13))
    if tune_complete:
        manifest["selection"] = select_all_entries(manifest)
        _atomic_json(_manifest_path(), manifest)
    columns = ("run_id", "entry", "seed", "slot", "status", "raw_feasibility", "raw_mean_gap_pct",
               "repaired_feasibility", "offline_repaired_gap_pct", "repair_successes", "repair_abstentions",
               "n_feasible_contexts", "n_infeasible_contexts", "mean_steps", "mean_rollout_calls",
               "training_calls", "eval_calls", "unused_calls", "total_calls", "config")
    _atomic_csv(ROOT / "paper" / "tables" / "p12a_pilot_summary.csv", _pilot_table_rows(manifest), columns)
    tune_columns = columns + ("selected",)
    _atomic_csv(ROOT / "paper" / "tables" / "p12a_tune_summary.csv", _tune_table_rows(manifest), tune_columns)
    pilot_complete = all(manifest["runs"].get(_config_id("pilot", e, seed=s), {}).get("status") == "complete"
                         for e in ENTRIES for s in PILOT_SEEDS)
    if pilot_complete and tune_complete:
        make_trigger(manifest)


class _ToyAgent:
    """No-learning deterministic policy used only for the timing smoke/benchmark."""
    def __init__(self, entry):
        self.entry = entry

    def act(self, env):
        return self._action()

    def greedy_act(self, env):
        return self._action()

    def _action(self):
        if self.entry == "f0_r1":
            return 0
        if self.entry == "f1_r1":
            return "accept"
        return (0, 0)

    def observe(self, *args):
        pass

    def update(self):
        return None

    def checkpoint_state(self):
        return {"toy": True}


def _bench_worker(entry: str, outdir: Path, smoke: bool) -> dict:
    config = benchmark_config(entry, smoke=smoke)
    cfg = RunConfig.from_dict(config)
    c, _ = _catalogue_and_checker()
    kc = CountingChecker(Checker(c))
    agent = _ToyAgent(entry)
    start = time.perf_counter()
    summary = run(cfg, agent, kc, outdir)
    elapsed = time.perf_counter() - start
    return {"entry": entry, "budget": cfg.budget, "eval_contexts": cfg.eval_contexts,
            "training_calls": summary["training_calls"], "eval_calls": summary["eval_calls"],
            "total_calls": summary["total_calls"], "wall_seconds": elapsed,
            "calls_per_second": summary["total_calls"] / elapsed if elapsed else None,
            "estimated_seconds_for_66000_calls": (66000 * elapsed / summary["total_calls"]
                                                   if summary["total_calls"] else None)}


def run_bench(smoke: bool = False) -> dict:
    eval_sha = _split_hash("val")
    results = []
    for entry in ENTRIES:
        outdir = RESULT_ROOT / "bench_runs" / ("smoke_" if smoke else "") / entry
        _clean_run_dir(outdir)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            env[key] = "1"
        cmd = [sys.executable, "-m", "ub_rl.experiment_runner", "_bench-worker", entry,
               "--outdir", str(outdir), "--smoke" if smoke else "--full"]
        proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
        if proc.returncode:
            raise RuntimeError(f"bench worker {entry} failed: {(proc.stderr or proc.stdout)[-4000:]}")
        result_path = outdir / "bench_result.json"
        if not result_path.is_file():
            raise RuntimeError(f"bench worker {entry} omitted {result_path}")
        results.append(json.loads(result_path.read_text(encoding="utf-8")))
    record = {"status": "complete", "kind": "bench_smoke" if smoke else "bench",
              "eval_split_file": "data/splits/val.csv", "eval_split_sha256": eval_sha,
              "checkpoint": "budget", "budget_includes_eval": False, "results": results}
    _atomic_json(RESULT_ROOT / ("bench_smoke.json" if smoke else "bench.json"), record)
    return record


def _cli_worker(argv) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("kind", choices=("_bench-worker",))
    p.add_argument("entry", choices=ENTRIES)
    p.add_argument("--outdir", required=True)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--smoke", action="store_true")
    mode.add_argument("--full", action="store_true")
    args = p.parse_args(argv)
    result = _bench_worker(args.entry, Path(args.outdir), smoke=args.smoke)
    _atomic_json(Path(args.outdir) / "bench_result.json", result)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "_bench-worker":
        _cli_worker(argv)
        return
    p = argparse.ArgumentParser(description="P12a A7 pilots and V-only tuning driver")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("pilot", help="run 3 default-config pilot seeds per entry")
    sub.add_parser("tune", help="run 12 V-only tuning configurations per entry")
    sub.add_parser("trigger", help="evaluate and record the A7 D6 R-C trigger")
    sub.add_parser("tables", help="rebuild P12a summary tables from validated result artifacts")
    bench = sub.add_parser("bench", help="run three short toy throughput checks")
    bench.add_argument("--smoke", action="store_true", help="use 20 training calls and val:2")
    args = p.parse_args(argv)
    if args.command in ("pilot", "tune"):
        manifest = run_experiments(args.command)
        print(f"{args.command} complete: {len([r for r in manifest['runs'].values() if r.get('kind') == args.command and r.get('status') == 'complete'])} runs")
    elif args.command == "trigger":
        val_sha = _split_hash("val")
        manifest = _load_manifest(val_sha)
        print(json.dumps(make_trigger(manifest), indent=2, sort_keys=True))
    elif args.command == "tables":
        val_sha = _split_hash("val")
        manifest = _load_manifest(val_sha)
        write_tables(manifest)
        print("P12a summary tables written")
    else:
        record = run_bench(smoke=args.smoke)
        print(json.dumps(record, indent=2, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "_bench-worker":
        _cli_worker(sys.argv[1:])
    else:
        main()
