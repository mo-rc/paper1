"""P11: the configuration-driven training harness (docs/p11_plan.md section 2).

  python -m ub_rl.harness configs/f1_r1.json [--seed N] [--outdir DIR]

Responsibilities: load and validate the run config; seed everything (stdlib, numpy, and torch when
present, pinned to one thread); stream training contexts uniformly with replacement from
data/splits/train.csv (the registered training distribution) by the run seed's RNG; run episodes
against a P10 env; call the agent's update() after every transition (the update boundary); stop
training exactly when the budget is reached, read from the CountingChecker's cumulative
kc.sections - never the agent's arithmetic; fire checkpoints at the first update boundary where
training calls >= each threshold (possibly mid-episode), recording the actual call count; evaluate
the greedy policy at each checkpoint on the contexts `eval_contexts` names - the rollout is the
verification, so `verification_calls` stays 0 for the record and the per-design deployed cost is
rollout calls (F0/F2: 1; F1: 1 + new visits) plus repair calls, with F1's N* also reporting steps
(plan decision 3d) - with the evaluation and repair calls baselined separately and added to the
budget only when `budget_includes_eval` is true (plan section 2; the A5 evaluation-budget problem
for F1 stays an open item for Amendment A7 - the harness implements the two fields and resolves
nothing); write a JSONL log, checkpoint artifacts and a P7-convention meta (status "complete",
commit, SHA-256s).

Agent contract (implemented by P11 steps 3-5; the toy agents of tests/test_harness.py follow it):
  act(env)                       -> training action for the env's current state (sampled policy,
                                    epsilon-greedy; the agent reads env.obs() itself)
  observe(obs, action, reward, done, info) -> receive the transition just taken
  update()                       -> dict | None: one learning update per boundary; agents discard an
                                    incomplete episode when the next episode starts (budget truncation)
  greedy_act(env)                -> deterministic greedy action, used only for checkpoint evaluation
  checkpoint_state()             -> dict; load_state(d) restores it

Agents must never use env.calls or info["calls"] during training: the call budget is the harness's,
read from the CountingChecker's kc.sections, and the agent's own arithmetic is not consulted.

No checker, physics, objective, split or hash is changed here. Run metadata follows the P7
convention (runstore) in spirit: status "complete", commit, SHA-256 of the environment and checker
files and of the config; the runstore CSV API is for baseline results and is not reused.
"""
import argparse
import json
import math
import random
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch

from . import splits
from .baselines import CountingChecker
from .checker import Checker
from .envs import F0Env, F1Env, F2Env, N_MAX
from .reward_checks import R3_BETAS
from .splits import sha256_file

ENTRIES = ("f0_r1", "f1_r1", "f2_r3")
AGENTS = {}  # entry -> agent factory; ub_rl.agents registers itself (P11 steps 3-5)
ROOT = Path(__file__).resolve().parent.parent.parent  # the repository root
TRAIN_SPLIT = "train"  # the registered training distribution; no other split is ever read here


def register_agent(entry, factory):
    """The agent modules call this at import time (steps 3-5); main() resolves the config entry."""
    if entry not in ENTRIES:
        raise ValueError(f"unknown entry {entry!r}, expected one of {ENTRIES}")
    AGENTS[entry] = factory


# ------------------------------------------------------------------ configuration
@dataclass
class RunConfig:
    entry: str
    seed: int
    budget: int
    checkpoints: tuple
    budget_includes_eval: bool
    eval_contexts: object  # None | "val" | "val:N" | list of Context objects (in-memory use only)
    network: dict         # {"hidden": [...], "lr": ...}: working defaults, marked provisional
    extra: dict           # entry-specific fields: f1 {gamma, n, epsilon, ...} / f2 {beta}
    eval_repair: bool = True
    provisional: bool = True

    @staticmethod
    def from_dict(d):
        cfg = {**d}  # a copy: the harness never mutates the caller's config
        entry = cfg.get("entry")
        if entry not in ENTRIES:
            raise ValueError(f"config entry must be one of {ENTRIES}, got {entry!r}")
        seed = int(cfg.get("seed", 0))
        if seed < 0:
            raise ValueError(f"seed must be >= 0, got {seed}")
        budget = int(cfg["budget"])
        if budget <= 0:
            raise ValueError(f"budget must be > 0, got {budget}")
        cps = tuple(int(x) for x in cfg.get("checkpoints", ()))
        if cps:
            if not all(0 < a < b for a, b in zip(cps, cps[1:])):
                raise ValueError(f"checkpoints must be strictly increasing and positive, got {cps}")
            if cps[-1] > budget:
                raise ValueError(f"checkpoint {cps[-1]} exceeds the budget {budget}")
        if not isinstance(cfg.get("budget_includes_eval", False), bool):
            raise ValueError("budget_includes_eval must be a boolean")
        if not isinstance(cfg.get("eval_repair", True), bool):
            raise ValueError("eval_repair must be a boolean")
        net = cfg.get("network", {})
        hidden = [int(x) for x in net.get("hidden", ())]
        if not hidden or not all(h > 0 for h in hidden):
            raise ValueError(f"network.hidden must be positive ints, got {hidden}")
        if float(net.get("lr", 0.0)) <= 0:
            raise ValueError(f"network.lr must be > 0, got {net.get('lr')!r}")
        ev = cfg.get("eval_contexts")
        if not (ev is None or isinstance(ev, (list, str))):
            raise ValueError("eval_contexts must be null, 'val', 'val:<n>' or a list of Contexts")
        if isinstance(ev, str):
            if ev != "val" and not (ev.startswith("val:") and ev[4:].isdigit() and int(ev[4:]) > 0):
                raise ValueError(f"eval_contexts string must be 'val' or 'val:<n>', got {ev!r}")
        extra = {}
        if entry == "f0_r1":
            f0 = cfg.get("f0", {})
            bs = int(f0.get("batch_size", 64))
            if bs <= 0:
                raise ValueError(f"f0.batch_size must be a positive int, got {bs}")
            extra["f0"] = {"batch_size": bs,
                           "normalize_advantage": bool(f0.get("normalize_advantage", False))}
        if entry == "f1_r1":
            f1 = cfg.get("f1", {})
            for k in ("gamma", "epsilon", "alpha", "beta_anneal_steps"):
                if float(f1.get(k, 0)) < 0:
                    raise ValueError(f"f1.{k} must be >= 0, got {f1.get(k)!r}")
            if not 0.0 <= float(f1.get("epsilon", 0)) <= 1.0:
                raise ValueError(f"f1.epsilon must be in [0, 1], got {f1.get('epsilon')!r}")
            for k in ("n", "batch_size", "replay_size", "target_sync"):
                if int(f1.get(k, 0)) <= 0:
                    raise ValueError(f"f1.{k} must be a positive int, got {f1.get(k)!r}")
            extra["f1"] = f1
        if entry == "f2_r3":
            f2 = cfg.get("f2", {})
            beta = f2.get("beta")
            if beta not in R3_BETAS:
                raise ValueError(f"f2.beta must be one of {R3_BETAS}, got {beta!r}")
            bs = int(f2.get("batch_size", 64))
            if bs <= 0:
                raise ValueError(f"f2.batch_size must be a positive int, got {bs}")
            logz_lr = float(f2.get("logz_lr", float(cfg.get("network", {}).get("lr", 0.001))))
            if logz_lr <= 0:
                raise ValueError(f"f2.logz_lr must be > 0, got {logz_lr!r}")
            extra["f2"] = {"beta": beta, "batch_size": bs, "logz_lr": logz_lr}
        return RunConfig(entry=entry, seed=seed, budget=budget, checkpoints=cps,
                         budget_includes_eval=cfg.get("budget_includes_eval", False),
                         eval_contexts=ev, network=net, extra=extra,
                         eval_repair=cfg.get("eval_repair", True),
                         provisional=bool(cfg.get("provisional", True)))


def load_config(path, seed=None):
    """Load one JSON config file (the provisional entry configs of configs/)."""
    with open(path) as f:
        cfg = RunConfig.from_dict(json.load(f))
    if seed is not None:
        cfg.seed = int(seed)
    return cfg


def make_env(entry, kc):
    """The P10 environment for the entry (calls measured by the CountingChecker)."""
    return {"f0_r1": F0Env, "f1_r1": F1Env, "f2_r3": F2Env}[entry](kc)


def _seed_all(seed):
    """One place where seeds are set: stdlib, numpy, and torch (pinned to one thread). The context
    stream uses its own random.Random(seed), independent of these globals."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)


def _git_commit():
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, check=True)
        return out.stdout.decode().strip()
    except Exception:
        return None


# ------------------------------------------------------------------ the run loop
class ContextStream:
    """Uniform draws with replacement from data/splits/train.csv (the registered training
    distribution) by the run seed's RNG. Stdlib Random, independent of the NumPy version, as in the
    P7b per-context shuffles. No test file is ever read here."""

    def __init__(self, seed):
        self.rng = random.Random(seed)
        self.rows, self.contexts = splits.load_split(TRAIN_SPLIT, root=ROOT / "data" / "splits")

    def __next__(self):
        i = self.rng.randrange(len(self.contexts))
        return self.contexts[i], self.rows[i], i


def _output_of(cfg, env, last_action):
    """The section index the greedy rollout output (the end-to-end verification target)."""
    if cfg.entry == "f0_r1":
        return int(last_action)
    if cfg.entry == "f1_r1":
        return int(env.i)  # the accepted section
    k, j = last_action  # F2: series k, variant j
    return int(env.variants[env.series[k]][j])


def _resolve_eval_contexts(cfg):
    if cfg.eval_contexts is None:
        return []
    if isinstance(cfg.eval_contexts, list):  # in-memory use (tests, toy runs)
        return list(cfg.eval_contexts)
    name = cfg.eval_contexts
    n = None if name == "val" else int(name[4:])
    _, ctxs = splits.load_split("val", root=ROOT / "data" / "splits")
    return ctxs[:n]


def _evaluate(cfg, agent, eval_env, kc, outdir, th, log):
    """Greedy-policy evaluation on the configured contexts (plan section 2), on its own env so the
    training episode's state survives mid-episode checkpoints: the rollout calls are `eval_calls`.
    The rollout IS the verification (F0/F2: the sampled section's checker call; F1: the accepted
    section was observed during the rollout), so `verification_calls` is always 0 (kept for the
    record). Per-design deployed cost = rollout calls (F0/F2: 1; F1: 1 + new visits) plus repair
    calls; F1's N* also reports steps (plan decision 3d). An infeasible output steps up in mass
    order until feasible (`repair_calls`; F1 through the episode cache, so an already-evaluated
    section costs no call), abstaining at the end of C (-1). All counts come from the same
    never-reset kc.sections; none are training budget."""
    contexts = _resolve_eval_contexts(cfg)
    if not contexts:
        return None
    start = kc.sections
    rows, total_steps = [], 0
    beta = cfg.extra["f2"]["beta"] if cfg.entry == "f2_r3" else None
    for idx, ctx in enumerate(contexts):
        eval_env.reset(ctx)
        done, last, guard = eval_env.done, None, 0
        while not done:
            last = agent.greedy_act(eval_env)
            obs, r, done, info = (eval_env.step(*last, beta) if isinstance(last, tuple)
                                  else eval_env.step(last))
            guard += 1
            if guard > N_MAX + 2:
                raise RuntimeError("greedy rollout did not terminate (agent bug)")
        total_steps += int(info["steps"])
        output = _output_of(cfg, eval_env, last)
        steps, calls = int(info["steps"]), int(eval_env.calls)  # per-context, before repair
        if cfg.entry == "f1_r1":
            # the rollout already observed the accepted section: no separate verification call
            feasible, _ = eval_env.visited[eval_env.i]
            repaired, rc = output, 0
            if cfg.eval_repair and not feasible:  # repair through the episode cache
                for i in range(output + 1, len(kc)):
                    new = i not in eval_env.visited
                    eval_env._land(i)
                    rc += int(new)
                    if eval_env.visited[i][0]:
                        repaired = i
                        break
                else:
                    repaired = -1  # abstain at the end of C
        else:  # F0/F2: the greedy step's checker call IS the verification (one call per sample)
            feasible = bool(info["feasible"])
            repaired, rc = output, 0
            if cfg.eval_repair and not feasible:  # repair: one counted fresh call per section
                for i in range(output + 1, len(kc)):
                    e = kc.evaluate_context(ctx, [i])
                    rc += 1
                    if e["feasible"][0]:
                        repaired = i
                        break
                else:
                    repaired = -1  # abstain at the end of C
        rows.append({"index": idx, "output": output, "feasible": int(feasible),
                     "repaired": repaired, "repair_calls": rc, "steps": steps, "calls": calls})
    verification_calls = 0  # kept for the record: the F0/F2 sample call and the F1 rollout are the
    # verification (per-design cost = rollout calls + repair calls; F1 N* also reports steps, 3d)
    repair_calls = sum(r["repair_calls"] for r in rows)
    eval_calls = kc.sections - start - verification_calls - repair_calls
    path = outdir / f"eval_{th}.csv"
    with open(path, "w") as f:
        f.write("index,output,feasible,repaired,repair_calls,steps,calls\n")
        for r in rows:
            f.write(f"{r['index']},{r['output']},{r['feasible']},{r['repaired']},"
                    f"{r['repair_calls']},{r['steps']},{r['calls']}\n")
    log({"event": "eval", "threshold": th, "n_contexts": len(contexts), "eval_calls": eval_calls,
         "eval_steps": total_steps, "verification_calls": verification_calls,
         "repair_calls": repair_calls})
    return {"eval_calls": eval_calls, "verification_calls": verification_calls,
            "repair_calls": repair_calls}


def _checkpoint(cfg, agent, outdir, th, tc, log):
    """One checkpoint artifact at the first update boundary where training calls >= the threshold;
    the actual call count is recorded in the artifact, the log and the meta."""
    cfg_dict = asdict(cfg)
    if isinstance(cfg_dict["eval_contexts"], list):  # in-memory contexts are not serialised
        cfg_dict["eval_contexts"] = None
    state = {"entry": cfg.entry, "seed": cfg.seed, "threshold": th, "training_calls": tc,
             "config": cfg_dict, "agent": agent.checkpoint_state()}
    torch.save(state, outdir / f"checkpoint_{th}.pt")
    log({"event": "checkpoint", "threshold": th, "training_calls": tc})


def _check_finite(obs, reward):
    """A non-finite observation or reward is never allowed to train silently: the run stops."""
    if not np.all(np.isfinite(np.asarray(obs, dtype=np.float64))):
        raise RuntimeError("non-finite observation produced by the environment")
    if not math.isfinite(float(reward)):
        raise RuntimeError("non-finite reward produced by the environment")


def run(cfg, agent, kc, outdir):
    """One configuration-driven training run. The hard stop reads kc.sections (the CountingChecker's
    cumulative counter, never reset, never the agent's arithmetic): training ends exactly when the
    training calls reach the budget; evaluation, verification and repair calls are subtracted from
    the counter for the training-budget check unless budget_includes_eval is true."""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    _seed_all(cfg.seed)
    env = make_env(cfg.entry, kc)
    eval_env = make_env(cfg.entry, kc)  # a separate env: checkpoint evaluation must not clobber
    # the training episode's state (the checkpoints may fire mid-episode); the same kc keeps one
    # never-reset call counter for both.
    stream = ContextStream(cfg.seed)
    log_path = outdir / "run.jsonl"

    def log(record):
        with open(log_path, "a") as f:
            f.write(json.dumps(record) + "\n")

    run_start = kc.sections
    eval_total = verify_total = repair_total = 0
    thresholds = list(cfg.checkpoints)
    final_threshold = thresholds[-1] if thresholds else None
    final_checkpoint_evaluated = False
    fired = []  # (threshold, actual training calls at the boundary) or (threshold, "skipped")
    n_episodes = 0

    def non_training():
        return 0 if cfg.budget_includes_eval else eval_total + verify_total + repair_total

    def training_calls():
        return kc.sections - run_start - non_training()

    def fire_checkpoints():
        """Check the thresholds at this boundary (after a reset, after an update, once at the end):
        a threshold reached by an F1 reset - or by the run's final call - still fires, and the
        end-of-run assert can never trip. At most one checkpoint fires per boundary call; a
        threshold its evaluation overshoots (only when the budget includes eval) is skipped."""
        nonlocal eval_total, verify_total, repair_total, final_checkpoint_evaluated
        tc = training_calls()
        if thresholds and tc >= thresholds[0]:
            th = thresholds.pop(0)
            _checkpoint(cfg, agent, outdir, th, tc, log)
            fired.append((th, tc))
            ev = _evaluate(cfg, agent, eval_env, kc, outdir, th, log)
            if ev:
                eval_total += ev["eval_calls"]
                verify_total += ev["verification_calls"]
                repair_total += ev["repair_calls"]
            if cfg.budget_includes_eval and th == final_threshold:
                final_checkpoint_evaluated = True
        while thresholds and training_calls() >= thresholds[0]:
            skipped = thresholds.pop(0)
            log({"event": "checkpoint_skipped", "threshold": skipped,
                 "training_calls": training_calls()})
            fired.append((skipped, "skipped"))

    beta = cfg.extra["f2"]["beta"] if cfg.entry == "f2_r3" else None  # F2Env.step needs it
    while training_calls() < cfg.budget and not final_checkpoint_evaluated:
        ctx, row, ctx_index = next(stream)
        n_episodes += 1
        env.reset(ctx)
        fire_checkpoints()  # an F1 reset costs 1 call and can reach a threshold before any update
        _check_finite(env.obs(), 0.0)
        done, steps, reward = env.done, 0, 0.0
        while not done and training_calls() < cfg.budget and not final_checkpoint_evaluated:
            action = agent.act(env)
            obs, reward, done, info = (env.step(*action, beta) if isinstance(action, tuple)
                                       else env.step(action))
            _check_finite(obs, reward)
            steps = int(info["steps"])
            agent.observe(obs, action, reward, done, info)
            agent.update()
            fire_checkpoints()  # the update boundary: a checkpoint may fire mid-episode
        if done:
            log({"event": "episode", "episode": n_episodes, "ctx_index": ctx_index,
                 "training_calls": training_calls(), "steps": steps, "reward": reward})
        else:
            log({"event": "truncated", "episode": n_episodes, "ctx_index": ctx_index,
                 "training_calls": training_calls()})
    fire_checkpoints()  # the run's final call may have reached the last threshold
    assert not thresholds, "training ended with unfired checkpoint thresholds"
    actual_training_calls = kc.sections - run_start - eval_total - verify_total - repair_total
    unused_calls = (cfg.budget - actual_training_calls - eval_total - verify_total - repair_total
                    if cfg.budget_includes_eval else 0)
    assert unused_calls >= 0, f"run exceeded its total call budget by {-unused_calls} calls"
    summary = {"event": "summary", "entry": cfg.entry, "seed": cfg.seed, "budget": cfg.budget,
               "training_calls": actual_training_calls, "eval_calls": eval_total,
               "verification_calls": verify_total, "repair_calls": repair_total,
               "unused_calls": unused_calls,
               "n_episodes": n_episodes, "total_calls": kc.sections - run_start}
    log(summary)
    _write_meta(cfg, outdir, fired, summary, n_episodes)
    return summary


def _write_meta(cfg, outdir, fired, summary, n_episodes):
    """The P7-convention meta (status "complete", commit, SHA-256s); written only when the run
    finished. The runstore CSV API is for baseline results and is not reused here."""
    here = Path(__file__).parent
    env_file = here / "envs.py"
    checker_file = here / "checker.py"
    cfg_dict = asdict(cfg)
    if isinstance(cfg_dict["eval_contexts"], list):
        cfg_dict["eval_contexts"] = None
    meta = {"status": "complete", "entry": cfg.entry, "seed": cfg.seed,
            "commit": _git_commit(),
            "environment_file": "src/ub_rl/envs.py", "environment_sha256": sha256_file(env_file),
            "checker_file": "src/ub_rl/checker.py", "checker_sha256": sha256_file(checker_file),
            "harness_file": "src/ub_rl/harness.py", "harness_sha256": sha256_file(Path(__file__)),
            "agents_sha256": sha256_file(here / "agents.py") if (here / "agents.py").exists() else None,
            "replay_sha256": sha256_file(here / "replay.py") if (here / "replay.py").exists() else None,
            "train_split_sha256": sha256_file(ROOT / "data" / "splits" / "train.csv"),
            "catalogue_workbook_sha256": sha256_file(
                ROOT / "data" / "raw" / "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"),
            "config_sha256": _sha256_text(json.dumps(cfg_dict, sort_keys=True)),
            "budget": cfg.budget, "budget_includes_eval": cfg.budget_includes_eval,
            "eval_repair": cfg.eval_repair,
            "eval_contexts": cfg_dict["eval_contexts"],
            "training_calls": summary["training_calls"], "eval_calls": summary["eval_calls"],
            "verification_calls": summary["verification_calls"],
            "repair_calls": summary["repair_calls"],
            "unused_calls": summary["unused_calls"],
            "total_calls": summary["total_calls"], "n_episodes": n_episodes,
            "checkpoints": [{"threshold": th, "training_calls": tc} for th, tc in fired]}
    if isinstance(cfg.eval_contexts, str) and cfg.eval_contexts.startswith("val"):
        val_file = ROOT / "data" / "splits" / "val.csv"
        meta["eval_split_file"] = "data/splits/val.csv"
        meta["eval_split_sha256"] = sha256_file(val_file)
    with open(outdir / "run_meta.json", "w") as f:
        json.dump(meta, f, indent=2, sort_keys=True)


def _sha256_text(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def main(argv=None):
    p = argparse.ArgumentParser(description="P11 training harness (plan section 2)")
    p.add_argument("config", help="path to the entry JSON config (configs/f0_r1.json, ...)")
    p.add_argument("--seed", type=int, default=None, help="override the config seed")
    p.add_argument("--outdir", default=None, help="output directory (default: results/p11/<entry>/seed<seed>)")
    p.add_argument("--allow-no-eval", action="store_true",
                   help="run without checkpoint evaluation (toy/debug runs only); the committed "
                        "configs evaluate V at each checkpoint and need no flag")
    args = p.parse_args(argv)
    cfg = load_config(args.config, seed=args.seed)
    if cfg.eval_contexts is None and not args.allow_no_eval:
        sys.exit("eval_contexts is not set in this config; pass --allow-no-eval to run without "
                 "checkpoint evaluation (toy/debug runs only)")
    try:
        from . import agents  # imports the canonical harness module and registers the entries
    except ImportError:
        sys.exit("src/ub_rl/agents.py is not implemented yet (P11 steps 3-5)")
    # Under ``python -m ub_rl.harness``, agents.py imports ``ub_rl.harness`` by package name while
    # this entry point is running as ``__main__``. Copy its registrations into this CLI module.
    if hasattr(agents, "harness"):
        AGENTS.update(agents.harness.AGENTS)
    if cfg.entry not in AGENTS:
        sys.exit(f"no agent registered for entry {cfg.entry!r}")
    from .catalogue import parse_workbook
    workbook = ROOT / "data" / "raw" / "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx"
    catalogue = parse_workbook(workbook)[0].mass_ordered(False)  # C, mass order (spec section 9)
    kc = CountingChecker(Checker(catalogue))
    outdir = Path(args.outdir) if args.outdir else ROOT / "results" / "p11" / cfg.entry / f"seed{cfg.seed}"
    agent = AGENTS[cfg.entry](cfg, make_env(cfg.entry, kc))
    run(cfg, agent, kc, outdir)


if __name__ == "__main__":
    main()
