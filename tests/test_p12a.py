"""Focused P12a driver, A7 accounting, selection, and subprocess reproducibility tests."""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

from ub_rl import p12a
from ub_rl.checker import Checker
from ub_rl.harness import RunConfig, ROOT


def _metrics(raw, raw_gap, repaired, repaired_gap):
    return {"raw_feasibility": raw, "raw_mean_gap_pct": raw_gap,
            "repaired_feasibility": repaired, "offline_repaired_gap_pct": repaired_gap}


@pytest.mark.parametrize("entry", p12a.ENTRIES)
def test_tuning_grid_is_stable_unique_and_default_is_slot_one(entry):
    first = p12a.tuning_configs(entry)
    second = p12a.tuning_configs(entry)
    assert first == second and len(first) == 12
    keys = [p12a._grid_key(cfg, entry) for cfg in first]
    assert len(set(keys)) == 12
    default = p12a._load_default(entry)
    assert keys[0] == p12a._grid_key(default, entry)
    assert all(cfg["seed"] == 0 and cfg["budget"] == 3000 for cfg in first)
    assert all(cfg["budget_includes_eval"] is True and cfg["eval_repair"] is False for cfg in first)
    assert all(cfg["checkpoints"] == ([1600] if entry == "f1_r1" else [2000]) for cfg in first)
    assert all(cfg["eval_contexts"] == ("val:100" if entry == "f1_r1" else "val") for cfg in first)
    if entry == "f1_r1":
        assert all(cfg["f1"]["beta_anneal_steps"] == 3000 for cfg in first)


@pytest.mark.parametrize("entry", p12a.ENTRIES)
def test_pilot_config_budget_seed_and_eval_protocol(entry):
    cfg = p12a.pilot_config(entry, 2)
    parsed = RunConfig.from_dict(cfg)
    assert parsed.seed == 2 and parsed.budget == 10000 and parsed.checkpoints == (10000,)
    assert parsed.budget_includes_eval is False and parsed.eval_repair is False
    assert parsed.eval_contexts == ("val:100" if entry == "f1_r1" else "val")


@pytest.mark.parametrize("entry", p12a.ENTRIES)
def test_bench_config_has_explicit_final_eval_budget(entry):
    cfg = p12a.benchmark_config(entry, smoke=True)
    parsed = RunConfig.from_dict(cfg)
    assert parsed.budget == 20 and parsed.checkpoints == (20,)
    assert parsed.budget_includes_eval is False and parsed.eval_repair is False
    assert parsed.eval_contexts == "val:2"


def test_offline_repair_uses_full_mask_and_reports_abstentions():
    masks = np.asarray([
        [False, False, True, True, False, False],
        [False, True, True, True, True, False],
        [False, False, False, False, False, False],
        [True, False, False, False, False, False],
    ], dtype=bool)
    masses = np.asarray([10.0, 12.0, 20.0, 25.0, 30.0, 40.0])
    rows = [
        {"index": 0, "output": 0, "feasible": 0, "repaired": 0, "repair_calls": 0,
         "steps": 0, "calls": 1},
        {"index": 1, "output": 4, "feasible": 1, "repaired": 4, "repair_calls": 0,
         "steps": 0, "calls": 1},
        {"index": 2, "output": 0, "feasible": 0, "repaired": 0, "repair_calls": 0,
         "steps": 0, "calls": 1},
        {"index": 3, "output": 5, "feasible": 0, "repaired": 5, "repair_calls": 0,
         "steps": 0, "calls": 1},
    ]
    metrics = p12a.offline_metrics(rows, masks, masses)
    assert metrics["n_feasible_contexts"] == 3 and metrics["n_infeasible_contexts"] == 1
    assert metrics["raw_feasibility"] == pytest.approx(1 / 3)
    assert metrics["repaired_feasibility"] == pytest.approx(2 / 3)
    assert metrics["repair_successes"] == 2 and metrics["repair_abstentions"] == 1
    assert metrics["offline_repaired_gap_pct"] == pytest.approx((0 + 150) / 2)


def test_a7_d5_selection_respects_feasibility_gap_and_incumbent_fallback():
    rows = [{"slot": 1, "config_id": "cfg01", "metrics": _metrics(.90, 5.0, 1.0, 5.0)}]
    rows += [{"slot": i, "config_id": f"cfg{i:02d}",
              "metrics": _metrics(.95 if i in (2, 3) else .90, 4.0,
                                  .90 if i == 2 else 1.0,
                                  4.0 if i in (2, 3) else 5.0)} for i in range(2, 13)]
    choice = p12a.select_entry(rows)
    assert choice["selected_slot"] == 3
    assert choice["passing_slots"] == [3]

    no_pass = [{"slot": 1, "config_id": "cfg01", "metrics": _metrics(.9, 5, 1, 5)}]
    no_pass += [{"slot": i, "config_id": f"cfg{i:02d}", "metrics": _metrics(.8, 4, 1, 4)}
                for i in range(2, 13)]
    assert p12a.select_entry(no_pass)["selected_slot"] == 1


def test_a7_d6_trigger_requires_all_three_seeds_for_every_entry():
    pilots = []
    for entry in p12a.ENTRIES:
        for seed in p12a.PILOT_SEEDS:
            value = .99 if entry == "f0_r1" else .8
            pilots.append({"entry": entry, "seed": seed,
                           "metrics": {"raw_feasibility": value}})
    selected = {"selected_config_id": "tune/f1_r1/cfg07", "selected_slot": 7}
    decision = p12a.trigger_decision(pilots, selected)
    assert decision["run_rc"] is False
    assert decision["entries_reaching_bar"]["f0_r1"] is True
    pilots[0]["metrics"]["raw_feasibility"] = .98
    decision = p12a.trigger_decision(pilots, selected)
    assert decision["run_rc"] is True
    assert decision["selected_f1_slot"] == 7
    with pytest.raises(ValueError, match="all pilot seeds"):
        p12a.trigger_decision(pilots[:-1], selected)


def test_validation_split_hash_matches_registered_manifest():
    expected = {}
    for line in (ROOT / "data" / "splits" / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    assert p12a._split_hash("val") == expected["val.csv"]


def test_preflight_enumerates_full_masks_and_confirms_a7_first100_count(C):
    checker = Checker(C)
    rows, contexts, masks, source = p12a.load_or_compute_val_masks(checker)
    report = p12a.representativeness_report(rows, contexts, masks, checker)
    assert masks.shape == (1000, 91)
    assert report["n_feasible_first100"] == 71
    assert report["n_feasible_val"] == 796
    assert source["split_sha256"] == p12a._split_hash("val")


def test_fresh_process_harness_runs_reproduce_f1_outputs_and_logs(tmp_path):
    """Two separate harness interpreters must produce identical training and greedy eval traces."""
    cfg = p12a._load_default("f1_r1")
    cfg.update({"seed": 19, "budget": 16, "checkpoints": [8], "budget_includes_eval": False,
                "eval_repair": False, "eval_contexts": "val:100"})
    cfg["f1"].update({"n": 1, "epsilon": 0.2, "batch_size": 4,
                      "replay_size": 32, "beta_anneal_steps": 16, "target_sync": 3})
    cfg_path = tmp_path / "f1.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[key] = "1"
    outputs = []
    for name in ("first", "second"):
        outdir = tmp_path / name
        proc = subprocess.run([sys.executable, "-m", "ub_rl.harness", str(cfg_path),
                               "--outdir", str(outdir)], cwd=ROOT, env=env,
                              capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        outputs.append(((outdir / "eval_8.csv").read_bytes(),
                        (outdir / "run.jsonl").read_bytes()))
        if name == "first":
            parsed, config_sha = p12a._cfg_and_sha(cfg)
            eval_sha = p12a._split_hash("val")
            meta, rows = p12a._validate_complete(outdir, parsed, config_sha, eval_sha)
            assert meta["eval_split_sha256"] == eval_sha and len(rows) == 100
            p12a._atomic_json(outdir / "p12a_artifacts.json",
                              p12a._artifact_seal(outdir, parsed, config_sha, eval_sha))
            p12a._validate_seal(outdir, parsed, config_sha, eval_sha)
    assert outputs[0] == outputs[1]
