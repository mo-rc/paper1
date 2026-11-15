"""P8: Stage 1 baselines II - the categorical-native GA (uniform crossover, random-section mutation; budgets 20
and |C|; seeds 0-9; tuning 12 configurations on V with the Amendment A5 default rule) and the supervised MLP
variant (i) (2,197 enumeration labels, 91-way softmax, end-to-end verify + repair). Plan docs/p8_plan.md;
acceptance line: every baseline reports feasibility, gap and calls on T1 to T5. Skips without the workbook;
samples the split files so the suite stays fast (the full run is scripts/run_baselines2.py)."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from ub_rl import baselines, baselines2, mlp_baseline
from ub_rl import splits as S
from ub_rl.checker import Checker
from ub_rl.runstore import load_results

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ROOT / "data" / "splits"
FILES = ["val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "reference"]
N_SAMPLE = 10  # first N contexts per file
SNAPSHOT = ROOT / "paper" / "tables" / "baselines2_run_output.txt"
CFG0 = baselines2.GAConfig(0, 4, 1, 2, 0.1, 0.5, 0)          # k=1, no elitism
CFG_K2 = baselines2.GAConfig(9, 4, 2, 2, 0.1, 1.0, 1)        # k=2, elitism: exercises both paths


@pytest.fixture(scope="module")
def kc(C):
    return baselines.CountingChecker(Checker(C))


@pytest.fixture(scope="module")
def sample_contexts():
    out = []
    for name in FILES:
        _, ctxs = S.load_split(name, root=SPLITS)
        out.extend(ctxs[:N_SAMPLE])
    return out


@pytest.fixture(scope="module")
def train_labels(kc):
    """The first 20 train contexts with a feasible enumeration optimum, as (context, optimum) pairs."""
    rows, ctxs = S.load_split("train", root=SPLITS)
    labels = []
    for _, ctx in zip(rows, ctxs):
        if len(labels) == 20:
            break
        ref = baselines.enumerate(kc, ctx)
        if ref.index >= 0:
            labels.append((ctx, ref.index))
    assert len(labels) == 20
    return labels


def _recheck(kc, ctx, res):
    if res.index < 0:
        return True
    return bool(kc.evaluate_context(ctx, [res.index])["feasible"][0]) == (res.status == "feasible")


# ---------------------------------------------------------------- the GA
def test_ga_config_draw_is_stable_distinct_and_in_grid():
    a = baselines2.draw_ga_configs()
    b = baselines2.draw_ga_configs()
    assert [asdict_x(c) for c in a] == [asdict_x(c) for c in b]  # fixed seed, fixed grid -> stable
    assert len({c.id for c in a}) == 12 and len({(c.p, c.k, c.t, c.m, c.c, c.e) for c in a}) == 12
    grid = set(baselines2.ga_config_grid())
    assert all((c.p, c.k, c.t, c.m, c.c, c.e) in grid for c in a)


def asdict_x(c):
    return (c.id, c.p, c.k, c.t, c.m, c.c, c.e)


def test_ga_deterministic_per_seed(kc):
    ctx = S.load_split("val", root=SPLITS)[1][0]
    for cfg in (CFG0, CFG_K2):
        a = baselines2.ga(kc, ctx, 20, 5, "ctx", cfg)
        b = baselines2.ga(kc, ctx, 20, 5, "ctx", cfg)
        assert (a.status, a.index, a.calls) == (b.status, b.index, b.calls)


def test_ga_budget_exact_distinct_and_counted(C, sample_contexts):
    """Exactly `budget` distinct evaluations per run, read from the counter; the duplicate rule (a section
    already evaluated costs 0 and the slot is redrawn from unseen sections) is enforced by recording the
    evaluated sections: none repeats and no evaluation is wasted."""
    seen = []

    class Rec(baselines.CountingChecker):
        def evaluate_context(self, ctx, idx=None):
            seen.append([int(i) for i in np.atleast_1d(idx)])
            return super().evaluate_context(ctx, idx)

    rec = Rec(Checker(C))
    for k, ctx in enumerate(sample_contexts):
        for budget in baselines2.GA_BUDGETS:
            for cfg in (CFG0, CFG_K2):
                seen.clear()
                before = rec.sections
                res = baselines2.ga(rec, ctx, budget, 1, f"c{k}", cfg)
                flat = [i for part in seen for i in part]
                assert len(flat) == len(set(flat)) == budget  # distinct, exactly the budget
                assert res.calls == budget == rec.sections - before  # the counter is the source of truth


def test_ga_outputs_feasible_rechecked_and_not_lighter_than_optimum(kc, sample_contexts):
    for k, ctx in enumerate(sample_contexts):
        ref = baselines.enumerate(kc, ctx)
        for budget in baselines2.GA_BUDGETS:
            for seed in (0, 1, 2):
                res = baselines2.ga(kc, ctx, budget, seed, f"c{k}", CFG0)
                assert _recheck(kc, ctx, res)
                if res.index >= 0:
                    assert ref.index >= 0  # no feasible section can exist if enumeration abstains
                    assert kc.mass[res.index] >= kc.mass[ref.index]  # never lighter than the optimum


def test_ga_budget_full_equals_enumeration(kc, sample_contexts):
    """Budget |C| evaluates every section (distinct redraw), so it equals the enumeration optimum for every
    seed and configuration - a cost data point, not a GA-quality result (recorded in the run summary)."""
    for k, ctx in enumerate(sample_contexts):
        ref = baselines.enumerate(kc, ctx)
        for seed in (0, 1, 2):
            for cfg in (CFG0, CFG_K2):
                res = baselines2.ga(kc, ctx, len(kc), seed, f"c{k}", cfg)
                assert (res.status, res.index) == (ref.status, ref.index)


def test_select_config_tuning_rule():
    """Amendment A5: the first drawn configuration is the default; a replacement needs >= 0.5 percentage
    points of mean-gap improvement with feasibility not lower, in draw order."""
    scores = [(1.0, 0.9), (0.6, 0.9), (1.5, 1.0), (0.45, 0.9)]
    assert baselines2.select_config(scores) == 3  # 0.6 and 1.5 do not clear 0.5; 0.45 does
    assert baselines2.select_config([(1.0, 0.9), (0.55, 0.9)]) == 0  # 0.45 pp improvement: not enough
    assert baselines2.select_config([(1.0, 0.9), (0.5, 0.9)]) == 1   # 0.5 pp: exactly the margin
    assert baselines2.select_config([(1.0, 0.9), (0.4, 0.8)]) == 0   # gap better, feasibility lower: no
    assert baselines2.select_config([(float("inf"), 0.0), (5.0, 0.5)]) == 1  # default outputs nothing
    assert baselines2.select_config([(0.3, 0.7)]) == 0              # the default is always the first drawn


# ---------------------------------------------------------------- the MLP
def test_mlp_labels_costings_arithmetic():
    assert mlp_baseline.N_LABELS == 2197
    assert mlp_baseline.N_LABELS * 91 == 199927  # the full-enumeration costing of spec section 9


def test_mlp_features_shape_and_onehots(sample_contexts):
    ctx = sample_contexts[0]
    x = mlp_baseline.context_features(ctx)
    assert len(x) == 12 == mlp_baseline.N_INPUTS
    assert sum(x[5:8]) == 1 and sum(x[8:12]) == 1  # exactly one rule and one cap category
    assert x[5 + mlp_baseline.DEFLECTION_RULE_INDEX[ctx.deflection_rule]] == 1
    assert x[8 + mlp_baseline.DEPTH_CAP_INDEX[ctx.depth_cap]] == 1


def test_mlp_train_deterministic_per_seed(train_labels):
    cfg = mlp_baseline.MLPConfig(0, (8,), 1e-3, 3, 4)
    m1, mean1, std1 = mlp_baseline.train_mlp(train_labels, cfg, 0, 91)
    m2, mean2, std2 = mlp_baseline.train_mlp(train_labels, cfg, 0, 91)
    assert np.array_equal(mean1, mean2) and np.array_equal(std1, std2)
    for ctx, _ in train_labels[:5]:
        assert mlp_baseline.predict(m1, mean1, std1, ctx) == mlp_baseline.predict(m2, mean2, std2, ctx)


def test_mlp_end_to_end_outputs_feasible_or_abstain(kc, train_labels, sample_contexts):
    """Spec section 9 end-to-end: argmax output -> verify (1 call) -> step up in mass order until feasible
    (1 counted call per step) -> abstain at the end of C."""
    cfg = mlp_baseline.MLPConfig(0, (8,), 1e-3, 3, 4)
    model, mean, std = mlp_baseline.train_mlp(train_labels, cfg, 0, 91)
    for ctx in sample_contexts:
        pred = mlp_baseline.predict(model, mean, std, ctx)
        assert 0 <= pred < 91
        before = kc.sections
        res = mlp_baseline.evaluate_mlp(kc, ctx, pred)
        assert res.calls == kc.sections - before  # measured, not the method's arithmetic
        if res.index >= 0:
            assert res.status == "feasible" and res.calls >= 1
            assert bool(kc.evaluate_context(ctx, [res.index])["feasible"][0])
        else:
            assert res.status == "abstain" and res.calls == 91 - pred  # stepped through the rest of C


# ---------------------------------------------------------------- the run script, end to end
def test_run_baselines2_smoke(tmp_path, raw_path):
    """Run the real script on a small limit: acceptance assertions inside the script (incl. GA budget |C| ==
    enumeration), files and metas written, the tuning rule recorded, and --out skips the committed snapshot."""
    out = tmp_path / "b2"
    script = ROOT / "scripts" / "run_baselines2.py"
    snap_before = SNAPSHOT.stat().st_mtime_ns if SNAPSHOT.exists() else None
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, str(script), str(raw_path), "--limit", "3", "--out", str(out)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "GA tuning:" in proc.stdout and "wrote results" in proc.stdout

    summary = json.loads((out / "run_summary.json").read_text(encoding="ascii"))
    assert summary["working_tree_dirty"] in (True, False)
    assert summary["ga"]["tuning_rule"] == baselines2.TUNING_RULE
    assert "utilisation overrun" in summary["ga"]["fitness_note"]
    assert "cost data point" in summary["ga"]["budget_C_note"]
    assert summary["mlp"]["labels"]["n_labels"] <= 3 and summary["mlp"]["labels"]["n_skipped_no_feasible_ref"] >= 0
    assert summary["mlp"]["tuning_rule"] == baselines2.TUNING_RULE

    sel, sel_meta = (json.loads((out / "ga_tuning_selection.json").read_text(encoding="ascii")),
                     json.loads((out / "ga_tuning_selection.json_meta.json").read_text(encoding="ascii")))
    assert sel["rule"] == baselines2.TUNING_RULE and sel_meta["tuning_rule"] == baselines2.TUNING_RULE
    assert sel["selected_config"]["id"] in range(12)
    for fname in ["test_t1", "reference"]:
        ref_rows, _ = load_results(out / f"ref_{fname}.csv")
        ga_rows, ga_meta = load_results(out / f"ga_{fname}.csv")
        assert len(ga_rows) == len(ref_rows) * 10 * 2
        assert ga_meta["tuning_rule"] == baselines2.TUNING_RULE
        for r in ga_rows:  # GA budget |C| equals enumeration on every stored row
            if r["budget"] == "91":
                ref = next(x for x in ref_rows if x["id"] == r["id"])
                assert (r["status"], r["section_index"]) == (ref["status"], ref["section_index"])
        if fname != "reference":
            mlp_rows, mlp_meta = load_results(out / f"mlp_{fname}.csv")
            assert len(mlp_rows) == len(ref_rows) * 10
            assert mlp_meta["seeds"] == list(range(10))
    # --out skips the committed snapshot (tests must never touch the committed file)
    assert (SNAPSHOT.stat().st_mtime_ns if SNAPSHOT.exists() else None) == snap_before
    assert time.perf_counter() - t0 < 600


def test_baselines2_summary_script_reads_the_store(tmp_path, raw_path):
    out = tmp_path / "b2"
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_baselines2.py"), str(raw_path),
                          "--limit", "3", "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert run.returncode == 0, run.stdout + run.stderr
    summ = subprocess.run([sys.executable, str(ROOT / "scripts" / "baselines2_summary.py"), str(out)],
                          capture_output=True, text=True, cwd=ROOT)
    assert summ.returncode == 0, summ.stderr
    lines = summ.stdout.splitlines()
    assert len(lines) == 5 * 3 + 2  # per set: ga budgets 20 and 91 + the MLP; reference has the GA only (A5)
    assert all("ga        budget  91" not in ln or "mean gap   0.000%" in ln for ln in lines)
    (out / "ref_test_t1.csv_meta.json").unlink()
    bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "baselines2_summary.py"), str(out)],
                         capture_output=True, text=True, cwd=ROOT)
    assert bad.returncode != 0 and "without its meta file" in bad.stderr
