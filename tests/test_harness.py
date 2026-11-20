"""P11 harness (docs/p11_plan.md section 2): configuration-driven runs, seeds, the training-context
stream from train.csv, the hard call-budget stop read from kc.sections (never the agent's
arithmetic), checkpoints at the first update boundary where training calls >= the threshold
(possibly mid-episode), evaluation/verification/repair calls kept separate with the
budget_includes_eval and eval_contexts fields, logs and meta.

Toy agents only (no learning, no torch networks): toy runs are smoke tests of a few hundred calls,
are not results, tune nothing and touch no test file - the eval contexts of these tests are drawn
from train.csv (the registered training distribution), never from V or any test file. The three
committed configs/ JSONs are validated for shape only; nothing runs them."""
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from ub_rl import baselines, envs, harness, splits
from ub_rl.baselines import CountingChecker
from ub_rl.checker import Checker

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def kc(C):
    return CountingChecker(Checker(C))


def _ctx_sig(ctx):
    return (ctx.span, ctx.width, ctx.dead, ctx.live, ctx.restraint_ratio,
            ctx.deflection_rule, ctx.depth_cap)


def _train_ctxs(n):
    return splits.load_split("train", root=ROOT / "data" / "splits")[1][:n]


# ------------------------------------------------------------------ toy agents (no learning)
class _Toy:
    """The agent contract of harness.py, with a dummy state for the checkpoint round-trip."""

    def __init__(self, seen=None):
        self.seen = seen  # records a ctx signature per act() call
        self.state = {"x": [1, 2, 3]}

    def observe(self, obs, action, reward, done, info):
        pass

    def update(self):
        return None

    def checkpoint_state(self):
        return dict(self.state)

    def load_state(self, state):
        self.state = dict(state)


class ToyF0(_Toy):
    def act(self, env):
        if self.seen is not None:
            self.seen.append(_ctx_sig(env.ctx))
        return 0

    def greedy_act(self, env):
        return 0


class ToyF1(_Toy):
    """One move up, then accept: 2 calls per episode (1 reset + 1 move; the accept costs no call),
    so a threshold can be crossed by the move, mid-episode."""

    def act(self, env):
        if self.seen is not None:
            self.seen.append(_ctx_sig(env.ctx))
        return "up" if env.steps == 0 else "accept"

    def greedy_act(self, env):
        return "accept"


class ToyF2(_Toy):
    def act(self, env):
        if self.seen is not None:
            self.seen.append(_ctx_sig(env.ctx))
        return (0, 0)

    def greedy_act(self, env):
        return (0, 0)


TOYS = {"f0_r1": ToyF0, "f1_r1": ToyF1, "f2_r3": ToyF2}


def _cfg(entry, budget, checkpoints, seed=3, includes_eval=False, eval_ctxs=None, **extra):
    d = {"entry": entry, "seed": seed, "budget": budget, "checkpoints": list(checkpoints),
         "budget_includes_eval": includes_eval, "eval_contexts": eval_ctxs,
         "network": {"hidden": [8, 8], "lr": 0.01}}
    d.update(extra)
    return harness.RunConfig.from_dict(d)


def _load_checkpoint(path):
    return torch.load(path, weights_only=False)


def _expected_repair(checker, ctx):
    """The repair the harness must do for greedy output 0: 0 calls if section 0 is feasible, else
    the scan 1..n-1 until the first feasible section (or -1 and n-1 calls when none is feasible)."""
    e = checker.evaluate_context(ctx)
    if e["feasible"][0]:
        return 0
    for i in range(1, len(checker)):
        if e["feasible"][i]:
            return i
    return len(checker) - 1


# ------------------------------------------------------------------ config loading and validation
def test_committed_configs_load_and_are_provisional():
    """The three configs/ JSONs parse, validate and are marked provisional (working defaults; the
    registered values are tuned in P12a and frozen at P12b). They evaluate V at each checkpoint
    with the evaluation calls kept out of the training budget (the 200k-run convention)."""
    for entry in ("f0_r1", "f1_r1", "f2_r3"):
        cfg = harness.load_config(ROOT / "configs" / f"{entry}.json")
        assert cfg.entry == entry and cfg.provisional is True
        assert cfg.eval_repair is True
        assert cfg.budget == 200000 and cfg.checkpoints == (10000, 50000, 200000)
        assert cfg.budget_includes_eval is False and cfg.eval_contexts == "val"
    f1 = harness.load_config(ROOT / "configs" / "f1_r1.json")
    assert f1.extra["f1"]["n"] == 5 and f1.extra["f1"]["gamma"] == 1.0
    f2 = harness.load_config(ROOT / "configs" / "f2_r3.json")
    assert f2.extra["f2"]["beta"] in (25, 50, 100)
    assert f2.extra["f2"]["batch_size"] == 64 and f2.extra["f2"]["logz_lr"] == 0.001


def test_config_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        _cfg("dqn", 100, [50])  # unknown entry
    with pytest.raises(ValueError):
        _cfg("f0_r1", 100, [50, 30])  # not increasing
    with pytest.raises(ValueError):
        _cfg("f0_r1", 100, [150])  # exceeds the budget
    with pytest.raises(ValueError):
        _cfg("f0_r1", 100, [50], network={"hidden": [], "lr": 0.1})  # empty hidden
    with pytest.raises(ValueError):
        _cfg("f1_r1", 100, [50], f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6,
                                     "beta_anneal_steps": 100, "batch_size": 0,
                                     "replay_size": 100, "target_sync": 10})
    with pytest.raises(ValueError):
        _cfg("f2_r3", 100, [50], f2={"beta": 12.5})  # not one of R3_BETAS
    with pytest.raises(ValueError):
        _cfg("f2_r3", 100, [50], f2={"beta": 50, "batch_size": 0})  # batch must be positive
    with pytest.raises(ValueError):
        _cfg("f2_r3", 100, [50], f2={"beta": 50, "batch_size": 8, "logz_lr": 0.0})  # lr > 0
    with pytest.raises(ValueError):
        _cfg("f0_r1", 100, [50], eval_ctxs="val:0")  # a named subset must be non-empty
    with pytest.raises(ValueError):
        _cfg("f0_r1", 100, [50], eval_ctxs="test_t1")  # only val subsets are named


@pytest.mark.parametrize("value", [0, 1, "false", "true", None, [], {}])
def test_eval_repair_requires_a_boolean(value):
    with pytest.raises(ValueError, match="eval_repair must be a boolean"):
        _cfg("f0_r1", 10, [], eval_repair=value)


def test_eval_contexts_val_count_uses_first_rows_in_file_order():
    cfg = _cfg("f0_r1", 10, [], eval_ctxs="val:7")
    resolved = harness._resolve_eval_contexts(cfg)
    _, all_val = splits.load_split("val", root=ROOT / "data" / "splits")
    assert [_ctx_sig(c) for c in resolved] == [_ctx_sig(c) for c in all_val[:7]]


# ------------------------------------------------------------------ context stream and budget
def test_same_seed_same_context_sequence(tmp_path, kc):
    seen1, seen2 = [], []
    cfg = _cfg("f0_r1", budget=12, checkpoints=(), seed=3)
    harness.run(cfg, ToyF0(seen1), kc, tmp_path / "a")
    harness.run(cfg, ToyF0(seen2), kc, tmp_path / "b")
    assert len(seen1) == 12 and seen1 == seen2
    # with replacement: the stream is a sequence of independent uniform draws over 20,000 contexts
    # (a repeat is near-certain only at much larger n, so none is asserted here)
    rows, ctxs = splits.load_split("train", root=ROOT / "data" / "splits")
    assert len(ctxs) == 20000
    train_sigs = {_ctx_sig(c) for c in ctxs}
    assert set(seen1) <= train_sigs  # every training context comes from train.csv


def test_hard_stop_reads_the_counter_and_stops_exactly_at_the_budget(tmp_path, kc):
    cfg = _cfg("f0_r1", budget=30, checkpoints=())
    start = kc.sections
    summary = harness.run(cfg, ToyF0(), kc, tmp_path)
    assert summary["training_calls"] == 30
    assert kc.sections - start == 30  # one call per F0 episode, no eval: the counter is the truth
    assert summary["n_episodes"] == 30


# ------------------------------------------------------------------ checkpoints
def test_checkpoints_fire_at_the_thresholds(tmp_path, kc):
    cfg = _cfg("f0_r1", budget=40, checkpoints=[10, 25, 40])
    harness.run(cfg, ToyF0(), kc, tmp_path)
    for th in (10, 25, 40):
        state = _load_checkpoint(tmp_path / f"checkpoint_{th}.pt")
        assert state["threshold"] == th and state["training_calls"] == th  # the actual call count
        assert state["agent"] == {"x": [1, 2, 3]}
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["status"] == "complete"
    assert [c["training_calls"] for c in meta["checkpoints"]] == [10, 25, 40]
    assert meta["checker_sha256"] and meta["environment_sha256"] and meta["config_sha256"]
    assert meta["harness_sha256"] and meta["train_split_sha256"]
    assert meta["catalogue_workbook_sha256"]
    assert meta["agents_sha256"]  # agents.py exists since P11 step 3
    assert meta["replay_sha256"]  # replay.py exists since P11 step 4


def test_checkpoint_at_the_final_f1_reset_call(tmp_path, kc):
    """An F1 reset costs 1 call; with budget 41 and threshold 41, episode 21's reset reaches the
    budget before any update boundary. The checkpoint fires anyway (checked after the reset and
    once more at the end of the run), so the end-of-run assert cannot trip."""
    cfg = _cfg("f1_r1", budget=41, checkpoints=[41],
               f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                   "batch_size": 8, "replay_size": 100, "target_sync": 10})
    summary = harness.run(cfg, ToyF1(), kc, tmp_path)
    assert summary["training_calls"] == 41
    assert _load_checkpoint(tmp_path / "checkpoint_41.pt")["training_calls"] == 41
    lines = [json.loads(l) for l in (tmp_path / "run.jsonl").read_text().splitlines()]
    assert lines[-2]["event"] == "truncated"  # the last reset hit the budget before any step
    assert lines[-1]["event"] == "summary"


def test_checkpoint_mid_episode_f1_at_the_first_update_boundary(tmp_path, kc):
    """ToyF1 costs 2 calls per episode; with the threshold at 26 the 13th episode's reset reaches 25
    (below it) and the move reaches 26: the checkpoint fires at the update boundary after the move,
    before the accept ends the episode - the checkpoint line precedes the episode-13 line."""
    cfg = _cfg("f1_r1", budget=40, checkpoints=[26],
               f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                   "batch_size": 8, "replay_size": 100, "target_sync": 10})
    harness.run(cfg, ToyF1(), kc, tmp_path)
    state = _load_checkpoint(tmp_path / "checkpoint_26.pt")
    assert state["training_calls"] == 26  # the first boundary past the threshold, mid-episode
    lines = [json.loads(l) for l in (tmp_path / "run.jsonl").read_text().splitlines()]
    i_cp = next(i for i, l in enumerate(lines) if l["event"] == "checkpoint")
    i_ep = next(i for i, l in enumerate(lines) if l["event"] == "episode" and l["episode"] == 13)
    assert i_cp < i_ep  # mid-episode: the checkpoint was taken before the episode ended
    assert lines[-1]["event"] == "summary" and lines[-1]["training_calls"] == 40


# ------------------------------------------------------------------ evaluation calls
def test_eval_calls_kept_separate_when_budget_excludes_eval(tmp_path, kc, C):
    """budget_includes_eval=false: the 12 training calls stop exactly at the budget; the 8-context
    evaluation (1 rollout call per context - which is the verification - plus repair) is measured
    from the same counter but kept out of the training budget."""
    ctxs = _train_ctxs(8)
    cfg = _cfg("f0_r1", budget=12, checkpoints=[6], eval_ctxs=ctxs)
    fresh = CountingChecker(Checker(C))
    start = kc.sections
    summary = harness.run(cfg, ToyF0(), kc, tmp_path)
    expected_repair = sum(_expected_repair(fresh, c) for c in ctxs)
    assert summary["training_calls"] == 12
    assert summary["eval_calls"] == 8
    assert summary["verification_calls"] == 0  # the sample call is the verification
    assert summary["repair_calls"] == expected_repair
    assert kc.sections - start == 12 + 8 + expected_repair  # one counter, separate columns
    rows = (tmp_path / "eval_6.csv").read_text().splitlines()[1:]
    assert len(rows) == 8
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["training_calls"] == 12 and meta["eval_calls"] == 8
    assert meta["verification_calls"] == 0 and meta["repair_calls"] == expected_repair


def test_eval_calls_count_inside_the_budget_when_budget_includes_eval(tmp_path, kc, C):
    """budget_includes_eval=true (the tuning/pilot convention): the evaluation calls consume the
    budget; a threshold the evaluation overshoots is recorded as skipped, and training stops."""
    ctxs = _train_ctxs(8)
    cfg = _cfg("f0_r1", budget=20, checkpoints=[6, 10], includes_eval=True,
               eval_ctxs=ctxs, eval_repair=False)
    start = kc.sections
    summary = harness.run(cfg, ToyF0(), kc, tmp_path)
    assert summary["training_calls"] == 12
    assert summary["eval_calls"] == 8 and summary["repair_calls"] == 0
    assert summary["training_calls"] + summary["eval_calls"] == cfg.budget
    assert summary["total_calls"] == kc.sections - start == cfg.budget
    assert summary["unused_calls"] == 0
    assert summary["eval_calls"] == 8 and summary["verification_calls"] == 0
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["checkpoints"] == [{"threshold": 6, "training_calls": 6},
                                   {"threshold": 10, "training_calls": "skipped"}]
    assert meta["unused_calls"] == 0
    assert (tmp_path / "checkpoint_6.pt").exists() and not (tmp_path / "checkpoint_10.pt").exists()


def test_budget_includes_eval_stops_after_final_f1_evaluation_and_records_unused_calls(
        tmp_path, kc):
    """The final evaluation can consume less than its reserved budget; training ends there."""
    ctx = _train_ctxs(1)[0]
    cfg = _cfg("f1_r1", budget=20, checkpoints=[16], includes_eval=True,
               eval_ctxs=[ctx], eval_repair=False,
               f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6,
                   "beta_anneal_steps": 100, "batch_size": 8,
                   "replay_size": 100, "target_sync": 10})
    seen = []
    start = kc.sections
    summary = harness.run(cfg, ToyF1(seen), kc, tmp_path)
    rows = [json.loads(line) for line in (tmp_path / "run.jsonl").read_text().splitlines()]
    eval_pos = next(i for i, row in enumerate(rows) if row["event"] == "eval")
    assert rows[eval_pos + 1]["event"] == "truncated"
    assert rows[-1]["event"] == "summary"
    assert len(seen) == 15  # eval fires after the 8th episode's move; no accept action follows
    assert summary["training_calls"] == 16
    assert summary["eval_calls"] == 1
    assert summary["unused_calls"] == 3
    assert summary["total_calls"] == 17 == kc.sections - start
    meta = json.loads((tmp_path / "run_meta.json").read_text())
    assert meta["unused_calls"] == 3
    assert (tmp_path / "checkpoint_16.pt").exists() and (tmp_path / "eval_16.csv").exists()


def test_budget_includes_eval_final_f1_checkpoint_at_reset_stops_before_action(tmp_path, kc):
    ctx = _train_ctxs(1)[0]
    cfg = _cfg("f1_r1", budget=20, checkpoints=[1], includes_eval=True,
               eval_ctxs=[ctx], eval_repair=False,
               f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6,
                   "beta_anneal_steps": 100, "batch_size": 8,
                   "replay_size": 100, "target_sync": 10})
    seen = []
    summary = harness.run(cfg, ToyF1(seen), kc, tmp_path)
    assert seen == []  # reset reached the threshold; final evaluation precedes the first action
    assert summary["training_calls"] == 1 and summary["eval_calls"] == 1
    assert summary["unused_calls"] == 18
    assert (tmp_path / "checkpoint_1.pt").exists() and (tmp_path / "eval_1.csv").exists()


@pytest.mark.parametrize("entry", ["f0_r1", "f2_r3"])
def test_budget_includes_eval_final_checkpoint_at_exact_threshold_with_batch_128(
        tmp_path, kc, entry):
    ctxs = _train_ctxs(2)
    extra = {"f0": {"batch_size": 128}} if entry == "f0_r1" else {"f2": {"beta": 50, "batch_size": 128}}
    cfg = _cfg(entry, budget=100, checkpoints=[4], includes_eval=True,
               eval_ctxs=ctxs, eval_repair=False, **extra)
    summary = harness.run(cfg, TOYS[entry](), kc, tmp_path / entry)
    meta = json.loads((tmp_path / entry / "run_meta.json").read_text())
    assert meta["checkpoints"] == [{"threshold": 4, "training_calls": 4}]
    assert summary["training_calls"] == 4
    assert summary["eval_calls"] == 2
    assert summary["total_calls"] == 6
    assert summary["unused_calls"] == 94
    assert meta["unused_calls"] == 94


def test_repair_steps_up_in_mass_order_and_abstains_at_the_end(tmp_path, kc, C):
    """The end-to-end repair (spec section 9): an infeasible greedy output is verified (1 call) and
    stepped up in mass order until feasible, with each repair step a counted call."""
    ctx = _train_ctxs(1)[0]
    cfg = _cfg("f0_r1", budget=10, checkpoints=[5], eval_ctxs=[ctx], eval_repair=True)
    fresh = CountingChecker(Checker(C))
    expected = _expected_repair(fresh, ctx)
    summary = harness.run(cfg, ToyF0(), kc, tmp_path)
    assert summary["verification_calls"] == 0  # the sample call is the verification
    assert summary["repair_calls"] == expected
    row = (tmp_path / "eval_5.csv").read_text().splitlines()[1].split(",")
    assert row[0] == "0" and int(row[1]) == 0
    assert int(row[6]) == 1  # per-design calls before repair: one rollout call
    if expected:
        assert int(row[2]) == 0  # section 0 infeasible for this training context
        assert 0 <= int(row[3]) <= 90  # repaired up in mass order (or -1 at the end of C)
    else:
        assert int(row[2]) == 1 and int(row[3]) == 0


def test_f1_eval_uses_the_rollout_cache_and_needs_no_verification(tmp_path, kc, C):
    """F1 evaluation: the greedy rollout already observed the accepted section, so there is no
    separate verification call; the repair steps up in mass order through the episode's visited
    cache, so an already-evaluated section costs no call. F0/F2 keep verify-then-repair."""
    ctx = _train_ctxs(1)[0]

    class ToyF1Move(_Toy):
        def act(self, env):
            return "up" if env.steps == 0 else "accept"

        def greedy_act(self, env):
            return "up" if env.steps == 0 else "accept"

    cfg = _cfg("f1_r1", budget=12, checkpoints=[6], eval_ctxs=[ctx],
               f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                   "batch_size": 8, "replay_size": 100, "target_sync": 10})
    fresh = CountingChecker(Checker(C))
    trial = baselines.trial_index(fresh, ctx)
    out = min(trial + 1, len(fresh) - 1)
    fe = fresh.evaluate_context(ctx)["feasible"]
    above = fe[out + 1:]
    expected_repair = (0 if fe[out] else
                       (int(np.argmax(above)) + 1 if above.any() else len(fresh) - 1 - out))
    summary = harness.run(cfg, ToyF1Move(), kc, tmp_path)
    assert summary["verification_calls"] == 0  # the rollout observed the accepted section
    assert summary["repair_calls"] == expected_repair
    assert summary["eval_calls"] == 2  # 1 reset call + 1 move
    header, row = (tmp_path / "eval_6.csv").read_text().splitlines()
    assert header == "index,output,feasible,repaired,repair_calls,steps,calls"
    cols = row.split(",")
    assert int(cols[1]) == out and int(cols[5]) == 1 and int(cols[6]) == 2


def _infeasible_eval_context(kc, entry):
    """Find a training context whose greedy toy output is infeasible for the given entry."""
    for ctx in _train_ctxs(100):
        output = baselines.trial_index(kc, ctx) if entry == "f1_r1" else 0
        if not kc.evaluate_context(ctx, [output])["feasible"][0]:
            return ctx
    raise AssertionError(f"no infeasible toy output found for {entry}")


@pytest.mark.parametrize("entry", ["f0_r1", "f1_r1", "f2_r3"])
def test_eval_repair_disabled_keeps_infeasible_output_and_counts_only_rollout(
        tmp_path, kc, entry, monkeypatch):
    ctx = _infeasible_eval_context(kc, entry)
    if entry == "f1_r1":
        calls = []
        original_land = envs.F1Env._land

        def tracked_land(env, i):
            calls.append(i)
            return original_land(env, i)

        monkeypatch.setattr(envs.F1Env, "_land", tracked_land)
    else:
        calls = None
    extra = {"f1": {"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6,
                     "beta_anneal_steps": 100, "batch_size": 8,
                     "replay_size": 100, "target_sync": 10}} if entry == "f1_r1" else {}
    if entry == "f2_r3":
        extra = {"f2": {"beta": 50}}
    cfg = _cfg(entry, budget=1, checkpoints=[1], eval_ctxs=[ctx], eval_repair=False, **extra)
    start = kc.sections
    summary = harness.run(cfg, TOYS[entry](), kc, tmp_path / entry)
    header, line = (tmp_path / entry / "eval_1.csv").read_text().splitlines()
    row = dict(zip(header.split(","), line.split(",")))
    assert int(row["feasible"]) == 0
    assert row["repaired"] == row["output"]
    assert int(row["repair_calls"]) == summary["repair_calls"] == 0
    assert summary["total_calls"] == summary["training_calls"] + summary["eval_calls"]
    assert kc.sections - start == summary["training_calls"] + summary["eval_calls"]
    if calls is not None:
        # One _land() at each env reset verifies the trial section; there is no extra repair _land().
        assert len(calls) == 2


def test_f0_and_f2_per_design_calls_are_one_before_repair(tmp_path, kc, C):
    """The deployed per-design cost (plan section 2, decision 3d): F0 and F2 sample one section per
    context, so the eval CSV `calls` column is 1 before repair, and the feasibility column comes
    from the rollout's own checker call (no extra verification)."""
    ctx = _train_ctxs(1)[0]
    fresh = CountingChecker(Checker(C))
    fe = fresh.evaluate_context(ctx)["feasible"]
    for entry, toy, fld in (("f0_r1", ToyF0, {}), ("f2_r3", ToyF2, {"f2": {"beta": 50}})):
        cfg = _cfg(entry, budget=10, checkpoints=[5], eval_ctxs=[ctx], **fld)
        summary = harness.run(cfg, toy(), kc, tmp_path / entry)
        assert summary["verification_calls"] == 0
        row = (tmp_path / entry / "eval_5.csv").read_text().splitlines()[1].split(",")
        assert int(row[6]) == 1  # one rollout call per design, before repair
        assert int(row[2]) == int(fe[0])  # both toy agents output section 0


@pytest.mark.parametrize("what", ["obs", "reward"])
def test_run_raises_on_non_finite_obs_or_reward(tmp_path, kc, monkeypatch, what):
    """A non-finite observation or reward stops the run (a poisoned-env hook triggers it): silent
    NaN learning is never allowed."""
    class PoisonedF0(envs.F0Env):
        def step(self, i):
            obs, r, done, info = super().step(i)
            if what == "obs":
                obs = obs.copy()
                obs[0] = np.nan
            else:
                r = float("nan")
            return obs, r, done, info

    monkeypatch.setattr(harness, "make_env", lambda entry, kc: PoisonedF0(kc))
    cfg = _cfg("f0_r1", budget=5, checkpoints=())
    with pytest.raises(RuntimeError, match="non-finite"):
        harness.run(cfg, ToyF0(), kc, tmp_path)


def test_f1_and_f2_toy_runs_stop_at_the_budget(tmp_path, kc):
    """The exact-stop and mid-episode checkpoint paths for the other two entries (toy agents, a few
    hundred calls at most; no learning)."""
    cfg1 = _cfg("f1_r1", budget=40, checkpoints=[10, 40],
                f1={"n": 5, "epsilon": 0.1, "gamma": 1.0, "alpha": 0.6, "beta_anneal_steps": 100,
                    "batch_size": 8, "replay_size": 100, "target_sync": 10})
    s1 = harness.run(cfg1, ToyF1(), kc, tmp_path / "f1")
    assert s1["training_calls"] == 40 and s1["n_episodes"] == 20
    cfg2 = _cfg("f2_r3", budget=25, checkpoints=[25], f2={"beta": 50})
    s2 = harness.run(cfg2, ToyF2(), kc, tmp_path / "f2")
    assert s2["training_calls"] == 25 and s2["n_episodes"] == 25
    assert _load_checkpoint(tmp_path / "f2" / "checkpoint_25.pt")["training_calls"] == 25
