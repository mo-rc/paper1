#!/usr/bin/env python
"""Read-only diagnostic summaries for saved P12a pilot and tuning artifacts.

Writes only results/p12a/diag/p12a_diagnostics.csv and summary.txt. Training section
indices are recovered from logged R1/R3 rewards where the reward identifies one
feasible section; infeasible rewards do not encode the selected index.
"""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from ub_rl.agents import F0Agent, F2Agent
from ub_rl.baselines import CountingChecker, heuristic, trial_index
from ub_rl.catalogue import parse_workbook
from ub_rl.checker import Checker
from ub_rl.envs import r1_log_return, r3_log_return
from ub_rl.harness import RunConfig, make_env
from ub_rl.reward_checks import R3_BETAS
from ub_rl.splits import load_split
import torch


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "p12a"
OUTPUT_DIR = RESULTS / "diag"
OUTPUT_CSV = OUTPUT_DIR / "p12a_diagnostics.csv"
OUTPUT_SUMMARY = OUTPUT_DIR / "summary.txt"
RUN_TABLE_CSV = OUTPUT_DIR / "p12a_45_run_cost_table.csv"
CONSTANT_REWARD_CSV = OUTPUT_DIR / "best_constant_rewards.csv"
SENSITIVITY_CSV = OUTPUT_DIR / "policy_sensitivity.csv"
HEURISTIC_CALLS_ALL_VAL = 14.193
WORKBOOK = ROOT / "data" / "raw" / "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
TRAIN_CSV = ROOT / "data" / "splits"
LAST_INDEX = 90  # cached full validation mask has 91 mass-ordered catalogue sections
ACTION_KEYS = {"action", "actions", "selected_section", "section_index", "output"}


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path):
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def read_eval(path: Path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def metric_signature(run: dict) -> str:
    # Compare every scalar metric; per-context offline rows are evidence, not summary metrics.
    scalar = {k: v for k, v in run["metrics"].items()
              if k != "offline_rows" and isinstance(v, (str, int, float, bool, type(None)))}
    return json.dumps(scalar, sort_keys=True, separators=(",", ":"))


def output_summary(rows, mask):
    outputs = [int(row["output"]) for row in rows]
    counts = Counter(outputs)
    mode_count = max(counts.values())
    # Lowest index is a deterministic tie-break for this diagnostic.
    mode = min(i for i, n in counts.items() if n == mode_count)
    repair_counts_feasible, repair_counts_no_feasible = [], []
    feasible_costs, no_feasible_costs, all_costs = [], [], []
    feasible_abstentions = no_feasible_abstentions = 0
    for row in rows:
        val_i, out_i = int(row["index"]), int(row["output"])
        if not 0 <= val_i < mask.shape[0] or not 0 <= out_i < mask.shape[1]:
            raise ValueError(f"eval row index/output outside saved mask: {val_i}/{out_i}")
        has_feasible = bool(mask[val_i].any())
        if mask[val_i, out_i]:
            n_calls = 0
            repaired = out_i
        else:
            n_calls = mask.shape[1] - 1 - out_i
            repaired = -1
            for j in range(out_i + 1, mask.shape[1]):
                if mask[val_i, j]:
                    n_calls = j - out_i
                    repaired = j
                    break
        base_calls = int(row["calls"])
        all_costs.append(base_calls + n_calls)
        if has_feasible:
            repair_counts_feasible.append(n_calls)
            feasible_costs.append(base_calls + n_calls)
            feasible_abstentions += int(repaired < 0)
        else:
            repair_counts_no_feasible.append(n_calls)
            no_feasible_costs.append(base_calls + n_calls)
            no_feasible_abstentions += 1
    all_repair_counts = repair_counts_feasible + repair_counts_no_feasible
    mean_repair_feasible = (float(np.mean(repair_counts_feasible))
                            if repair_counts_feasible else float("nan"))
    mean_repair_no_feasible = (float(np.mean(repair_counts_no_feasible))
                               if repair_counts_no_feasible else float("nan"))
    mean_repair_all = float(np.mean(all_repair_counts)) if all_repair_counts else float("nan")
    return {
        "eval_n": len(rows),
        "distinct_outputs": len(counts),
        "modal_output_index": mode,
        "modal_output_share": mode_count / len(outputs) if outputs else float("nan"),
        "modal_is_last_section": mode == LAST_INDEX,
        "n_feasible_contexts": len(repair_counts_feasible),
        "n_no_feasible_contexts": len(repair_counts_no_feasible),
        "mean_offline_repair_calls_feasible": mean_repair_feasible,
        "mean_walk_calls_no_feasible": mean_repair_no_feasible,
        "mean_offline_repair_calls_all": mean_repair_all,
        "mean_base_calls_feasible": float(np.mean([int(r["calls"]) for r in rows
                                                       if mask[int(r["index"])].any()])),
        "mean_base_calls_no_feasible": float(np.mean([int(r["calls"]) for r in rows
                                                          if not mask[int(r["index"])].any()])),
        "mean_cost_feasible": float(np.mean(feasible_costs)) if feasible_costs else float("nan"),
        "mean_cost_no_feasible": float(np.mean(no_feasible_costs)) if no_feasible_costs else float("nan"),
        "mean_cost_all": float(np.mean(all_costs)) if all_costs else float("nan"),
        "repair_abstentions_feasible": feasible_abstentions,
        "repair_abstentions_no_feasible": no_feasible_abstentions,
        "repair_abstentions_all": feasible_abstentions + no_feasible_abstentions,
    }


def decode_training_index(entry, reward, context, beta, kc):
    """Decode a selected index only when the logged reward identifies a feasible mass."""
    t = trial_index(kc, context)
    trial_mass = float(kc.mass[t])
    max_mass = float(kc.mass[-1])
    if entry == "f0_r1":
        no_index_reward = r1_log_return(max_mass, trial_mass, max_mass, False, 0)
        candidates = [i for i, mass in enumerate(kc.mass)
                      if math.isclose(r1_log_return(mass, trial_mass, max_mass, True, 0),
                                      reward, rel_tol=1e-10, abs_tol=1e-9)]
    else:
        no_index_reward = r3_log_return(max_mass, trial_mass, max_mass, False, beta)
        candidates = [i for i, mass in enumerate(kc.mass)
                      if math.isclose(r3_log_return(mass, trial_mass, max_mass, True, beta),
                                      reward, rel_tol=1e-10, abs_tol=1e-9)]
    if math.isclose(no_index_reward, reward, rel_tol=1e-10, abs_tol=1e-9):
        return None, "infeasible_reward_does_not_encode_index"
    if len(candidates) == 1:
        return candidates[0], "decoded_from_reward"
    if len(candidates) > 1:
        return None, "multiple_reward_matches"
    return None, "no_reward_match"


def first_episode_event(events):
    for event in events:
        if event.get("event") == "episode":
            return event
    return {}


def mean_heuristic_calls(kc, contexts):
    calls = [heuristic(kc, ctx).calls for ctx in contexts]
    return float(np.mean(calls))


def constant_reward_table(kc, train_contexts):
    """Exact mean R1/R3 return for every fixed section over the training pool."""
    trial_masses = np.empty(len(train_contexts), dtype=np.float64)
    feasibility = np.empty((len(train_contexts), len(kc)), dtype=bool)
    for row_i, ctx in enumerate(train_contexts):
        trial_masses[row_i] = kc.mass[trial_index(kc, ctx)]
        feasibility[row_i] = np.asarray(kc.evaluate_context(ctx)["feasible"], dtype=bool)
    max_mass = float(kc.mass[-1])
    rows = []
    for section_i, mass in enumerate(kc.mass):
        r1 = [r1_log_return(mass, trial_masses[j], max_mass,
                             bool(feasibility[j, section_i]), 0)
              for j in range(len(train_contexts))]
        r3 = {beta: [r3_log_return(mass, trial_masses[j], max_mass,
                                   bool(feasibility[j, section_i]), beta)
                     for j in range(len(train_contexts))]
              for beta in R3_BETAS}
        rows.append({"section_index": section_i, "mass_kg_m": float(mass),
                     "mean_R1_reward": float(np.mean(r1)),
                     **{f"mean_R3_beta{beta}_reward": float(np.mean(vals))
                        for beta, vals in r3.items()}})
    return rows


def model_sensitivity(agent, entry, observations):
    x = torch.as_tensor(observations, dtype=torch.float32)
    with torch.no_grad():
        if entry == "f0_r1":
            logits = agent.policy(x)
        else:
            series_logits, variant_logits, _ = agent.net(x)
            log_series = torch.log_softmax(series_logits, dim=-1)
            logits = torch.full((len(x), agent.n_sections), float("-inf"))
            for k, series in enumerate(agent.series):
                idx = torch.as_tensor(agent.variants[series], dtype=torch.long)
                log_variant = torch.log_softmax(variant_logits.index_select(1, idx), dim=-1)
                logits[:, idx] = log_series[:, k:k + 1] + log_variant
        probabilities = (torch.softmax(logits, dim=-1) if entry == "f0_r1"
                         else torch.exp(logits))
        logp = torch.where(probabilities > 0, torch.log(probabilities), torch.zeros_like(probabilities))
        entropy = -(probabilities * logp).sum(dim=-1)
        per_action_std = logits.std(dim=0, unbiased=False)
        greedy = torch.argmax(logits, dim=-1).cpu().numpy()
    return {
        "logit_std_across_V_mean_over_actions": float(per_action_std.mean()),
        "logit_std_across_V_min_action": float(per_action_std.min()),
        "logit_std_across_V_max_action": float(per_action_std.max()),
        "mean_entropy_nats": float(entropy.mean()),
        "greedy_mode_index": Counter(greedy.tolist()).most_common(1)[0][0],
    }


def sensitivity_rows(manifest, output_rows, kc, val_contexts):
    """Checkpoint and same-seed fresh-network forward passes only; no optimizer updates."""
    wanted = ("pilot/f0_r1/seed0", "pilot/f2_r3/seed0", "pilot/f2_r3/seed1")
    feature_names = ("span_scaled", "width_scaled", "dead_scaled", "live_scaled",
                     "restraint_ratio", "depth_cap_scaled", "rule_tot250",
                     "rule_var200", "rule_var360")
    rows, missing = [], []
    observation_env = make_env("f0_r1", kc)
    obs = np.asarray([observation_env._context_obs(ctx) for ctx in val_contexts], dtype=np.float32)
    feature_sd = obs.std(axis=0)
    zero_features = [feature_names[i] for i, sd in enumerate(feature_sd) if sd <= 1e-12]
    eval_modes = {r["run_id"]: r["modal_output_index"] for r in output_rows}
    for run_id in wanted:
        run = manifest["runs"].get(run_id)
        if not run:
            missing.append(f"manifest run {run_id}")
            continue
        checkpoint = ROOT / run["outdir"] / f"checkpoint_{run['config']['checkpoints'][-1]}.pt"
        if not checkpoint.exists():
            missing.append(str(checkpoint.relative_to(ROOT)))
            continue
        cfg = RunConfig.from_dict(run["config"])
        env = make_env(run["entry"], kc)
        factory = F0Agent if run["entry"] == "f0_r1" else F2Agent
        fresh = factory(cfg, env)
        fresh_model = fresh.policy if run["entry"] == "f0_r1" else fresh.net
        fresh_model.eval()
        trained = factory(cfg, env)
        state = torch.load(checkpoint, map_location="cpu", weights_only=False)
        trained.load_state(state["agent"])
        trained_model = trained.policy if run["entry"] == "f0_r1" else trained.net
        trained_model.eval()
        observed_mode = eval_modes.get(run_id)
        for label, agent in (("fresh_same_seed", fresh), ("trained_checkpoint", trained)):
            metrics = model_sensitivity(agent, run["entry"], obs)
            rows.append({"run_id": run_id, "entry": run["entry"], "seed": run["seed"],
                         "state": label, "n_validation_contexts": len(obs),
                         "logit_std_across_V_mean_over_actions": metrics["logit_std_across_V_mean_over_actions"],
                         "logit_std_across_V_min_action": metrics["logit_std_across_V_min_action"],
                         "logit_std_across_V_max_action": metrics["logit_std_across_V_max_action"],
                         "mean_entropy_nats": metrics["mean_entropy_nats"],
                         "greedy_mode_index": metrics["greedy_mode_index"],
                         "observed_eval_mode_index": observed_mode,
                         "greedy_mode_matches_observed": metrics["greedy_mode_index"] == observed_mode,
                         "zero_variance_observation_features": ";".join(zero_features) or "none"})
    return rows, missing, zero_features


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = read_json(RESULTS / "manifest.json")
    masks = np.load(RESULTS / "cache" / "val_feasibility.npz")["masks"]
    if masks.shape != (1000, 91):
        raise ValueError(f"unexpected saved validation mask shape {masks.shape}")

    runs = sorted((r for r in manifest["runs"].values()
                   if r.get("kind") in ("pilot", "tune") and r.get("status") == "complete"),
                  key=lambda r: r["run_id"])
    if len(runs) != 45:
        raise ValueError(f"expected 45 complete P12a runs, found {len(runs)}")

    # Output/evaluation summary for each run.
    output_rows = []
    eval_rows_by_run = {}
    event_cache = {}
    meta_cache = {}
    for run in runs:
        outdir = ROOT / run["outdir"]
        meta = read_json(outdir / "run_meta.json")
        event_cache[run["run_id"]] = read_jsonl(outdir / "run.jsonl")
        meta_cache[run["run_id"]] = meta
        threshold = int(meta["checkpoints"][-1]["threshold"])
        eval_path = outdir / f"eval_{threshold}.csv"
        rows = read_eval(eval_path)
        eval_rows_by_run[run["run_id"]] = rows
        stats = output_summary(rows, masks)
        eval_set = "V-first-100" if run["entry"] == "f1_r1" else "V-1000"
        repair_status = "upper_bound" if run["entry"] == "f1_r1" else "exact"
        output_rows.append({
            "record_type": "eval_run", "run_id": run["run_id"], "entry": run["entry"],
            "eval_set": eval_set, "repair_call_status": repair_status,
            "seed": run["config"].get("seed", ""), "window": "", "window_episodes": "",
            "distinct_outputs": stats["distinct_outputs"],
            "modal_output_index": stats["modal_output_index"],
            "modal_output_share": stats["modal_output_share"],
            "modal_is_last_section": stats["modal_is_last_section"],
            "mean_training_reward": "", "mean_selected_section_index": "",
            "decoded_index_episodes": "", "undecodable_index_episodes": "",
            "n_feasible_contexts": stats["n_feasible_contexts"],
            "n_no_feasible_contexts": stats["n_no_feasible_contexts"],
            "mean_offline_repair_calls_feasible": stats["mean_offline_repair_calls_feasible"],
            "mean_walk_calls_no_feasible": stats["mean_walk_calls_no_feasible"],
            "mean_offline_repair_calls_all": stats["mean_offline_repair_calls_all"],
            "mean_base_calls_feasible": stats["mean_base_calls_feasible"],
            "mean_base_calls_no_feasible": stats["mean_base_calls_no_feasible"],
            "mean_cost_feasible": stats["mean_cost_feasible"],
            "mean_cost_no_feasible": stats["mean_cost_no_feasible"],
            "mean_cost_all": stats["mean_cost_all"],
            "repair_abstentions_feasible": stats["repair_abstentions_feasible"],
            "repair_abstentions_no_feasible": stats["repair_abstentions_no_feasible"],
            "repair_abstentions_all": stats["repair_abstentions_all"],
            "config_sha256": meta["config_sha256"],
            "raw_feasibility": 100.0 * float(run["metrics"]["raw_feasibility"]),
            "offline_repaired_gap_pct": run["metrics"]["offline_repaired_gap_pct"],
        })

    # Reconstruct only the reward-to-mass mapping needed for logged F0/F2 training rows.
    _, train_contexts = load_split("train", root=TRAIN_CSV)
    cat = parse_workbook(WORKBOOK)[0].mass_ordered(False)
    kc = CountingChecker(Checker(cat))
    _, val_contexts = load_split("val", root=TRAIN_CSV)
    heuristic_first100 = mean_heuristic_calls(kc, val_contexts[:100])
    decode_cache = {}
    training_rows = []
    for run in runs:
        if run["kind"] != "pilot" or run["entry"] not in ("f0_r1", "f2_r3"):
            continue
        run_id = run["run_id"]
        meta = meta_cache[run_id]
        budget = int(meta["training_calls"])
        events = [e for e in event_cache[run_id] if e.get("event") == "episode"]
        windows = [[] for _ in range(10)]
        for event in events:
            call = int(event["training_calls"])
            wi = min(9, max(0, ((call - 1) * 10) // budget))
            windows[wi].append(event)
        beta = int(run["config"].get("f2", {}).get("beta", 50))
        for wi, items in enumerate(windows):
            rewards, indices, undecodable = [], [], 0
            for event in items:
                rewards.append(float(event["reward"]))
                key = (run["entry"], beta, int(event["ctx_index"]), float(event["reward"]))
                if key not in decode_cache:
                    index, status = decode_training_index(
                        run["entry"], float(event["reward"]),
                        train_contexts[int(event["ctx_index"])], beta, kc)
                    decode_cache[key] = (index, status)
                index, _status = decode_cache[key]
                if index is None:
                    undecodable += 1
                else:
                    indices.append(index)
            training_rows.append({
                "record_type": "training_window", "run_id": run_id,
                "entry": run["entry"], "seed": run["config"].get("seed", ""),
                "window": wi + 1, "window_episodes": len(items),
                "distinct_outputs": "", "modal_output_index": "",
                "modal_output_share": "", "modal_is_last_section": "",
                "mean_training_reward": float(np.mean(rewards)) if rewards else "",
                "mean_selected_section_index": float(np.mean(indices)) if indices else "",
                "decoded_index_episodes": len(indices),
                "undecodable_index_episodes": undecodable,
                "eval_set": "", "repair_call_status": "",
                "n_feasible_contexts": "", "n_no_feasible_contexts": "",
                "mean_offline_repair_calls_feasible": "",
                "mean_walk_calls_no_feasible": "",
                "mean_offline_repair_calls_all": "",
                "mean_base_calls_feasible": "", "mean_base_calls_no_feasible": "",
                "mean_cost_feasible": "", "mean_cost_no_feasible": "",
                "mean_cost_all": "", "repair_abstentions_feasible": "",
                "repair_abstentions_no_feasible": "", "repair_abstentions_all": "",
                "raw_feasibility": "",
                "offline_repaired_gap_pct": "",
            })

    # Group runs with exactly identical scalar metric summaries.
    groups = defaultdict(list)
    for run in runs:
        groups[metric_signature(run)].append(run)
    duplicate_groups = [group for group in groups.values() if len(group) > 1]
    duplicate_groups.sort(key=lambda g: g[0]["run_id"])
    duplicate_id = {}
    for number, group in enumerate(duplicate_groups, 1):
        for run in group:
            duplicate_id[run["run_id"]] = f"metric_group_{number:02d}"
    for row in output_rows:
        rid = row["run_id"]
        first = first_episode_event(event_cache[rid])
        row.update({
            "identical_metric_group": duplicate_id.get(rid, ""),
            "first_action_logged": bool(ACTION_KEYS.intersection(first)),
            "first_episode_ctx_index": first.get("ctx_index", ""),
            "first_episode_reward": first.get("reward", ""),
        })

    fields = ("record_type", "run_id", "entry", "eval_set", "repair_call_status",
              "seed", "window", "window_episodes",
              "distinct_outputs", "modal_output_index", "modal_output_share",
              "modal_is_last_section", "mean_training_reward",
              "mean_selected_section_index", "decoded_index_episodes",
              "undecodable_index_episodes", "n_feasible_contexts", "n_no_feasible_contexts",
              "mean_offline_repair_calls_feasible", "mean_walk_calls_no_feasible",
              "mean_offline_repair_calls_all", "mean_base_calls_feasible",
              "mean_base_calls_no_feasible", "mean_cost_feasible", "mean_cost_no_feasible",
              "mean_cost_all", "repair_abstentions_feasible",
              "repair_abstentions_no_feasible", "repair_abstentions_all",
              "raw_feasibility", "offline_repaired_gap_pct", "identical_metric_group",
              "config_sha256", "first_action_logged", "first_episode_ctx_index",
              "first_episode_reward")
    for row in training_rows:
        row.update({"identical_metric_group": "", "first_action_logged": "",
                    "config_sha256": "",
                    "first_episode_ctx_index": "", "first_episode_reward": ""})
    with OUTPUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output_rows + training_rows)

    # F0/F2: baseline is P9's all-V mean. F1: compute the same heuristic on V's first 100 rows.
    run_table = []
    for run, row in zip(runs, output_rows):
        label = (f"seed{run['seed']}" if run["kind"] == "pilot"
                 else f"slot{int(run['slot']):02d}")
        gap = row["offline_repaired_gap_pct"]
        heuristic_mean = heuristic_first100 if run["entry"] == "f1_r1" else HEURISTIC_CALLS_ALL_VAL
        whole_set_cost = row["mean_cost_all"]
        flagged = whole_set_cost < heuristic_mean and gap is not None and gap <= 0.5
        run_table.append({
            "entry": run["entry"],
            "eval_set": "V-first-100" if run["entry"] == "f1_r1" else "V-1000",
            "slot_or_seed": label,
            "raw_feasibility_pct": row["raw_feasibility"],
            "offline_repaired_gap_pct": gap,
            "mean_repair_calls_feasible": row["mean_offline_repair_calls_feasible"],
            "mean_walk_calls_no_feasible": row["mean_walk_calls_no_feasible"],
            "repair_abstentions_feasible": row["repair_abstentions_feasible"],
            "repair_abstentions_all": row["repair_abstentions_all"],
            "mean_cost_feasible": row["mean_cost_feasible"],
            "mean_cost_all": whole_set_cost,
            "repair_call_status": row["repair_call_status"],
            "matching_heuristic_mean_calls": heuristic_mean,
            "flag_vs_matching_heuristic": flagged,
        })
    run_table_fields = ("entry", "eval_set", "slot_or_seed", "raw_feasibility_pct",
                        "offline_repaired_gap_pct", "mean_repair_calls_feasible",
                        "mean_walk_calls_no_feasible", "repair_abstentions_feasible",
                        "repair_abstentions_all", "mean_cost_feasible", "mean_cost_all",
                        "repair_call_status", "matching_heuristic_mean_calls",
                        "flag_vs_matching_heuristic")
    with RUN_TABLE_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=run_table_fields)
        writer.writeheader()
        writer.writerows(run_table)

    constants = constant_reward_table(kc, train_contexts)
    with CONSTANT_REWARD_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=tuple(constants[0]))
        writer.writeheader()
        writer.writerows(constants)
    sens_rows, missing_checkpoints, zero_features = sensitivity_rows(
        manifest, output_rows, kc, val_contexts)
    with SENSITIVITY_CSV.open("w", newline="") as f:
        if sens_rows:
            writer = csv.DictWriter(f, fieldnames=tuple(sens_rows[0]))
            writer.writeheader()
            writer.writerows(sens_rows)
        else:
            f.write("no sensitivity rows\n")

    r1_best = max(constants, key=lambda r: (r["mean_R1_reward"], -r["section_index"]))
    r3_best = {beta: max(constants, key=lambda r: (r[f"mean_R3_beta{beta}_reward"],
                                                    -r["section_index"]))
               for beta in R3_BETAS}
    observed_modes = {rid: next(r["modal_output_index"] for r in output_rows if r["run_id"] == rid)
                      for rid in ("pilot/f0_r1/seed0", "pilot/f2_r3/seed0", "pilot/f2_r3/seed1")}

    lines = [
        "P12a saved-artifact diagnostics (no training; saved checkpoints used for forward passes only)",
        f"Runs summarized: {len(runs)}; eval mask shape {masks.shape[0]} x {masks.shape[1]}.",
        "Evaluation sets: F0/F2 = V-1000; F1 = V-first-100. Modal-output ties choose the lowest index; last section index is 90.",
        f"Modal output was the last catalogue section in {sum(bool(r['modal_is_last_section']) for r in output_rows)}/{len(output_rows)} runs.",
        "Cost = greedy rollout/evaluation calls + offline mass-order repair walk calls. F1 repair calls and its resulting costs are upper bounds because F1 harness repair skips already visited sections, which eval CSV does not record.",
        f"14.193 heuristic calls is over all 1,000 V contexts: the verification record gives n=1000, n_feasible=796, and the generation code divides by len(rows). F1 first-100 heuristic mean computed by running the existing heuristic on the first 100 val.csv contexts: {heuristic_first100:.3f} calls.",
        f"Repair abstentions are reported separately for feasible-context and whole-set denominators. No-feasible walk-only mean range: {min(r['mean_walk_calls_no_feasible'] for r in output_rows):.3f} to {max(r['mean_walk_calls_no_feasible'] for r in output_rows):.3f}.",
        f"Flag condition uses whole-set mean cost vs matching heuristic and repaired gap <=0.5 pp; flagged: {sum(bool(r['flag_vs_matching_heuristic']) for r in run_table)}.",
        f"Files: {OUTPUT_CSV.relative_to(ROOT)}, {RUN_TABLE_CSV.relative_to(ROOT)}, {CONSTANT_REWARD_CSV.relative_to(ROOT)}, {SENSITIVITY_CSV.relative_to(ROOT)}.",
        "Best gap pair per entry is min repaired gap (tie: lower feasible-context mean cost); lowest-cost pair is also shown:",
    ]
    for entry in ("f0_r1", "f1_r1", "f2_r3"):
        candidates = [r for r in run_table if r["entry"] == entry]
        valid = [r for r in candidates if r["offline_repaired_gap_pct"] is not None]
        best_gap = min(valid, key=lambda r: (r["offline_repaired_gap_pct"],
                                             r["mean_cost_feasible"]))
        best_c = min(valid, key=lambda r: (r["mean_cost_feasible"],
                                           r["offline_repaired_gap_pct"]))
        lines.append(f"{entry}: best-gap (feasible_cost={best_gap['mean_cost_feasible']:.3f}, "
                     f"gap={best_gap['offline_repaired_gap_pct']:.4f}%, {best_gap['slot_or_seed']}); "
                     f"lowest-cost (feasible_cost={best_c['mean_cost_feasible']:.3f}, "
                     f"gap={best_c['offline_repaired_gap_pct']:.4f}%, {best_c['slot_or_seed']}).")
    lines += ["", "Best constant section over the 20,000 training contexts (mean environment reward):",
              f"R1 argmax section {r1_best['section_index']}, mean={r1_best['mean_R1_reward']:.8f}; "
              f"observed F0 pilot seed0 mode={observed_modes['pilot/f0_r1/seed0']}."]
    for beta in R3_BETAS:
        best = r3_best[beta]
        lines.append(f"R3 beta={beta} argmax section {best['section_index']}, "
                     f"mean={best[f'mean_R3_beta{beta}_reward']:.8f}; "
                     f"observed F2 modes seed0/seed1={observed_modes['pilot/f2_r3/seed0']}/"
                     f"{observed_modes['pilot/f2_r3/seed1']}.")
    lines += ["", "Checkpoint/fresh-network sensitivity (V, forward passes only):",
              f"Zero-variance V observation features: {', '.join(zero_features) if zero_features else 'none'}."]
    for row in sens_rows:
        lines.append(f"{row['run_id']} {row['state']}: mean action-logit SD across V="
                     f"{row['logit_std_across_V_mean_over_actions']:.8f} "
                     f"(range {row['logit_std_across_V_min_action']:.8f}–{row['logit_std_across_V_max_action']:.8f}); "
                     f"mean entropy={row['mean_entropy_nats']:.6f} nats; greedy mode="
                     f"{row['greedy_mode_index']} vs observed={row['observed_eval_mode_index']}.")
    if missing_checkpoints:
        lines.append("Missing sensitivity inputs: " + "; ".join(missing_checkpoints))
    lines += [
        "Training selected indices are decoded from R1/R3 reward only when a unique feasible-mass reward matches.",
        "Infeasible R1/R3 rewards do not encode which section was selected; window index means cover only uniquely decoded feasible-reward episodes.",
        "run.jsonl does not record training actions; the CSV includes first episode context/reward, and groups exact-identical scalar metric summaries.",
        "",
        "F0/F2 pilot window trend (calls split into 10 equal-width intervals; first and last mean reward):",
    ]
    for run_id in sorted({r["run_id"] for r in training_rows}):
        rows = [r for r in training_rows if r["run_id"] == run_id]
        first, last = rows[0], rows[-1]
        lines.append(f"{run_id}: {first['mean_training_reward']:.6f} -> {last['mean_training_reward']:.6f}; "
                     f"decoded index mean {first['mean_selected_section_index']:.2f} "
                     f"(n={first['decoded_index_episodes']}) -> "
                     f"{last['mean_selected_section_index']:.2f} (n={last['decoded_index_episodes']}).")
    lines += ["", "Runs with identical scalar metrics:"]
    if not duplicate_groups:
        lines.append("None.")
    for number, group in enumerate(duplicate_groups, 1):
        seed_values = {r["config"].get("seed") for r in group}
        details = []
        first_contexts, first_rewards = [], []
        for run in group:
            rid = run["run_id"]
            row = next(x for x in output_rows if x["run_id"] == rid)
            first_contexts.append(row["first_episode_ctx_index"])
            first_rewards.append(row["first_episode_reward"])
            details.append(f"{rid}[distinct={row['distinct_outputs']}, mode={row['modal_output_index']}, "
                           f"share={row['modal_output_share']:.3f}]")
        context_diff = len(set(first_contexts)) > 1
        reward_diff = len(set(first_rewards)) > 1
        lines.append(f"- metric_group_{number:02d}: " + "; ".join(details))
        lines.append(f"  first_episode_ctx_index differs={context_diff}; first_episode_reward differs={reward_diff}; "
                     f"config seed fields={sorted(seed_values)}; seed reaches ContextStream: YES (harness.py seeds its RNG).")
        lines.append("  First logged actions: unavailable; run.jsonl episode records contain no action/output field.")
    lines.append("Full 45-run table:")
    lines.append("| Entry | Set | Slot/seed | Raw feas. % | Repaired gap % | Feasible mean cost | No-feasible walk | Repair abstentions feasible/all | Whole-set mean cost | Heuristic mean | F1 repair term | Flag |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|:---:|")
    for row in run_table:
        gap = "NA" if row["offline_repaired_gap_pct"] is None else f"{row['offline_repaired_gap_pct']:.4f}"
        lines.append(f"| {row['entry']} | {row['eval_set']} | {row['slot_or_seed']} | "
                     f"{row['raw_feasibility_pct']:.2f} | {gap} | {row['mean_cost_feasible']:.3f} | "
                     f"{row['mean_walk_calls_no_feasible']:.3f} | "
                     f"{row['repair_abstentions_feasible']}/{row['repair_abstentions_all']} | "
                     f"{row['mean_cost_all']:.3f} | {row['matching_heuristic_mean_calls']:.3f} | "
                     f"{row['repair_call_status']} | "
                     f"{'YES' if row['flag_vs_matching_heuristic'] else 'no'} |")
    OUTPUT_SUMMARY.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
