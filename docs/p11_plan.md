# P11 plan: agents and training harness (plan only, uncommitted)

P11 builds the three Stage 1 agents of Amendment A5 and the configuration-driven training harness on the P10 environments. Plan only: no code, no runs, nothing committed. No change to the checker, physics, objective, splits or their hashes.

## 0. Framework

- **PyTorch** (torch 2.5.1+cpu in conda `rl_env`, no CUDA; numpy 2.3.5) — VERIFIED by import in `rl_env` this session.
- Agents are small MLPs (at most a few 10k parameters); CPU training is adequate and matches the single-thread convention of spec section 10.
- Determinism: fixed `torch.manual_seed`, `torch.set_num_threads(1)`, numpy `default_rng(seed)`; agents must reproduce their result for the same seed (P11 acceptance).

## 1. Agents (exactly the A5 three)

Spec sources: spec section 9 and A5 (READ: `docs/spec.md` lines 110-136, 361-393). Environments: `src/ub_rl/envs.py` (READ).

**F0-R1 — REINFORCE with a learned baseline** (contextual bandit).
- Policy: MLP over the 9-dim scaled context (env `_context_obs`; shape asserted in `tests/test_envs.py:198`, VERIFIED) → softmax over the 91 catalogue sections; baseline: learned value head over the same context.
- Update: REINFORCE on the R1 log-return with the learned baseline subtracted; the env returns the full R1 return per sampled section (`F0Env.step`, one checker call per sample). One epoch per context batch; no replay.
- Greedy output = arg max probability (spec section 9, F0). Sampled output is reported separately at P13; the bandit is one step, so both exist.

**F1-R1 — Dueling Double DQN, prioritized replay, n-step returns** (refinement MDP).
- Dueling network: shared trunk over the F1 observation, value stream V and advantage stream A; Q = V + (A − mean A).
- Double DQN: online net picks the arg max action for the target; a target net (hard-synced every N updates, N a config value) provides the value. Five actions: up, down, deeper, shallower, accept.
- Prioritized replay: proportional to |TD-error|, config α, importance-sampling β annealed to 1; n-step returns (config n, default 5) built from the env's (obs, action, reward, done) tuples. Terminal-sparse R1 with discount γ = 1.0 (decision: the episode return is the terminal R1 return; γ = 1.0 makes the n-step and Monte-Carlo targets consistent). Exploration ε-greedy, config value.
- Greedy policy = arg max Q rollout: follow the greedy action each step until accept or the 13-step horizon (Amendment A3). The rollout's step count is the F1 per-design cost (decision 3d).

**F2-R3 — conditional GFlowNet, trajectory balance, hierarchical series-then-variant policy** (constructive MDP).
- Two choices in order: series k, then variant j within the series — exactly the tree of `F2Env.series` / `F2Env.variants`; the shared mapping lives in the env, the agent reads it.
- Policy: MLP over the 9-dim context → logits for the series head and for one masked variant head (masked to the chosen series' variants). Conditional on context through the same trunk.
- Trajectory balance: a learned log Z(context) head; loss = (log Z + log P_F(series) + log P_F(variant|series) − log R(x))² with R3 log-rewards computed by the env (float64 log-space, `R3_BETAS` from `reward_checks.py`). Trained on-policy (sampled trajectories), decision: no replay.
- Beta: one of (25, 50, 100) per config; the V-selected value is fixed in P12a. Greedy output = `F2Env.greedy(p_series, p_variant)` — exact arg max of the joint probability over C, with the P11 tie-break (decision 3e).

No DQN, plain Double DQN, PPO or SAC anywhere (A5).

## 2. Harness

Module `src/ub_rl/harness.py`, run as `python -m ub_rl.harness configs/<entry>.json` (no new scripts/ file; runnable module keeps P11 to `src/ub_rl/` + tests).

- **Configuration-driven**: one JSON per entry (`configs/f0_r1.json`, `f1_r1.json`, `f2_r3.json`; the directory exists, empty except `.gitkeep` — VERIFIED by `ls` and `git ls-files`). Fields: entry, seed, call budget, checkpoint call counts, network sizes, learning rates, F1 (n, ε, replay size, α, β-anneal, target-sync N), F2 beta, `budget_includes_eval`, `eval_contexts`. Values in the committed configs are **working defaults, marked provisional** — the registered values are tuned in P12a and frozen at P12b.
- **Budget**: the hard stop reads the CountingChecker's cumulative `kc.sections` after every checker call (`src/ub_rl/baselines.py:43-61`, VERIFIED) — never the agent's arithmetic. The counter is never reset for the run. Training contexts follow the rule below.
- **Training contexts**: drawn uniformly **with replacement** from `data/splits/train.csv` (the registered training distribution) by the run seed's RNG; no test file is read by any training or evaluation path in P11.
- **Checkpoints at 10,000 / 50,000 / 200,000 training calls** (spec section 9): model state, optimizer, replay buffer, config, seed, the actual call count. Taken at the **first update boundary where training calls ≥ threshold** (the harness checks the counter after each update, so a checkpoint may fall mid-episode); the actual `kc.sections` value is recorded in the log and meta. The budget hard stop stays exact: training ends when the counter reaches the budget.
- **Evaluation calls — two config fields**: `eval_contexts` names a subset of V evaluated at checkpoints (e.g. "all" = the 1,000 V contexts, or a named smaller subset); `budget_includes_eval` says whether those calls count inside the run's call budget (true for tuning/pilot configs, false for the 200,000-call runs). The harness baselines with `env.reset_calls()` before and after and records `eval_calls` (and F1 `eval_steps`) in the log and meta, all read from the same never-reset `kc.sections`. The rollout is the verification: `verification_calls` stays 0 for the record. **Per-design deployed cost = rollout calls (F0/F2: 1; F1: 1 + new visits) plus repair calls; F1 N\* also reports steps (decision 3d).** Repair (step up in mass order until feasible, abstaining at -1) applies to infeasible evaluation outputs only, is counted, and is never part of the training budget.
- **Open item — A5 evaluation budget for F1 (record, do not resolve)**: A5 fixes 3,000 checker calls per tuning configuration and 10,000 per pilot, "counting every call including the verification of the 1,000 V contexts (about 2,000 calls of learning)". That arithmetic assumes one call per context (F0/F2); an F1 greedy-rollout evaluation of all 1,000 V contexts costs roughly 10,000+ calls (up to 14 per context; P7 measured mean heuristic calls 14.19 on V, `docs/verification_record.md`, READ), so the A5 rule is **unsatisfiable for F1 as written**. Recorded here as an open item for a dated **Amendment A7 before P12a**. P11 resolves nothing: the harness only implements the two config fields above, and no spec text is edited.
- **Logs and metadata**: per-run JSONL log (calls, episodes, loss, eval metrics per checkpoint); result rows and `*_meta.json` through the P7 `runstore` convention (status "complete", commit, SHA-256 of `checker.py`, `envs.py` and the config file).

## 3. Decisions carried from P10 (decide, assume, one-line reason)

a. **F1 observation: add steps-taken** — `steps / 13` appended to the observation (observation becomes 9 context + 5 section + 7 utilisation + 1 = 22 dims; the 7 utilisation columns of `checker.py:184` are VERIFIED). Reason: the spec's observation list has no time feature and the value of a state depends on the remaining horizon. Recorded as a clarification of the spec observation list, not a change of it.
b. **Step cost: keep R1 terminal-only** — `r1_log_return` subtracts `STEP_COST_R1 * steps` at acceptance exactly as P10 built it (`envs.py:50-60`). Reason: with γ = 1 the sum of per-move 0.001 costs equals the terminal deduction, so the episode returns are identical and the env is unchanged.
c. **Utilisation entries: fixed clip/scale** — u_scaled = clip(u, 0, 2) / 2. Reason: keeps the feasibility boundary 1.0 at a fixed linear position (0.5) with no distortion around it, and caps extreme infeasibility at 2× capacity; 2 is an engineering bound, never a data statistic.
d. **F1 cost for N\*** — spec section 10 and A5 are primary: measured mean step count plus repair calls; checker calls reported alongside (visits are cached, so calls ≤ steps + 1; deployed cost = 1 + new visits + repair calls). Reason: A5 fixed the N* rule for F1; the harness logs both.
e. **F2 greedy tie-break: lowest mass index** — change `F2Env.greedy` to maximize (joint probability, −mass index), so exact ties go to the lightest section; add one test with exact ties. Reason: the strict `>` keeps the first max in series-then-variant iteration order, which is not the mass order.

## 4. Tests (fast, no real training)

`tests/test_agents.py`, `tests/test_harness.py` — all on a **toy context set**: 32 contexts drawn uniformly with replacement from `train.csv` (the registered training distribution, hash-pinned by `test_splits.py`) by the run seed's RNG, tiny networks (2×8 hidden units), budget a few hundred calls (≈300). These are smoke tests of a few hundred calls: they are **not results, tune nothing, touch no test file**, and satisfy the patch-plan P11 acceptance line ("trains on a toy context set and reproduces its result for the same seed"). No conflict with the no-training rule: spec section 12 forbids RL training before Gates 1–3 are accepted, and Gate 3 was accepted 2026-11-14 (`docs/patch_plan.md` P9 status, READ); the Gate 4 freeze (P12b) gates the real runs (P12b/P13), not the toy smoke tests. Flagged as requested: no conflict found.

- Per-agent determinism: same seed and toy set → identical greedy outputs and identical call sequence on a second run.
- Context-stream determinism: the same run seed draws the same context sequence from `train.csv`.
- The call counter stops exactly at the budget (`training_calls == budget`).
- Checkpoints fire at the right call counts (test uses scaled thresholds, e.g. 100/150/200 with budget 200); with an F1 episode that crosses a threshold mid-episode, the checkpoint is taken at the next update boundary with its actual call count recorded in the log and meta.
- Greedy output of each agent is a valid section index (0 ≤ i < 91; F2 inside the chosen series).
- F2 greedy is the exact arg max over C, ties → lowest mass index.
- F1 steps-taken feature: 22-dim observation, steps/13 correct.
- Reward/env plumbing unchanged: agents consume env rewards only; no agent code touches the checker directly.

## 5. Files

New only: `src/ub_rl/agents.py` (three agents, torch), `src/ub_rl/replay.py` (prioritized replay + n-step for F1), `src/ub_rl/harness.py` (config-driven runs, budgets, checkpoints, logs, metadata), `tests/test_agents.py`, `tests/test_harness.py`, and the three JSON files in `configs/`. Modified only: `src/ub_rl/envs.py` (3a steps feature, 3e tie-break) and its tests.

**P11 does not do**: no pilots, no tuning, no full runs, no evaluation on V or any test file, no results (those are P12a, P12b, P13), and no resolution of the A5-evaluation-budget open item for F1 (that is Amendment A7, before P12a).

## 6. Assumptions and review risks

Assumptions: torch is the framework (CPU, deterministic mode); F1 γ = 1.0, n = 5, ε and network sizes as provisional config defaults; F2 trained on-policy, beta = 50 as the provisional default; toy runs draw from `train.csv` with replacement; checkpoint evaluation reads V only in real runs; env edits are limited to 3a and 3e.

Review risks: (1) CPU float determinism of torch must be enforced by the determinism test itself; (2) the masked variant head must stay in lockstep with `F2Env.series/variants` or the joint probability silently mis-indexes; (3) n-step + prioritized replay is the fiddliest agent — transitions must be stored with their n-step returns built before priorities are updated; (4) budget accounting across F1's 1-call reset, 0-call revisits, mid-episode checkpoints and checkpoint evals is the subtlest harness bug — hence the exact-stop and mid-episode-checkpoint tests; (5) provisional config defaults must not become de facto tuning (P12a does the registered 12-configuration tuning; P11 states this in each config); (6) the A7 open item above must be amended before P12a — until then no F1 tuning or pilot config can be frozen.
