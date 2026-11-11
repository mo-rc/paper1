# Generative and AI-Driven Design of Steel Beams

Reinforcement learning for safe, automated selection of standard UK Universal Beams.

Specification: `docs/spec.md`. Engineering concepts, formulas and code names for readers new to structural engineering: `docs/engineering_concepts.md`.

Step-by-step instructions for running the code and reading its output: `docs/how_to_run.md`.

## Checker

```
pip install -e .[test]
python scripts/build_catalogue.py      # needs data/raw/<workbook>
python scripts/reference_case.py
pytest
```

Parser: `src/ub_rl/catalogue.py`. Checker: `src/ub_rl/checker.py`. Open assumptions are parameters in `src/ub_rl/config.py`. Clause status: `docs/verification_record.md`.


## Research proposal

The project proposal (one journal paper: Eurocode-verified environment, pre-registered benchmark, seven-parameter contexts including restraint and LTB, algorithm tournament, welded-section Stage 2) is in `docs/proposal.md`. The dated amendment A1 at the end of `docs/spec.md` records the matching changes to the pre-registration. Both await supervisor acceptance. The dated amendment A2 at the end of `docs/spec.md` fixes the seven-parameter sampling ranges, the depth caps (none, 700, 800, 900 mm) and the frozen train/validation/test splits (T1–T5, v1.2 sub-study) with their SHA-256; these values were recorded before any run and are supervisor-approved (approval recorded 2026-11-10 in `docs/spec.md` A2).

## Splits and context audit (P6)

Context ranges and splits: `docs/spec.md`, Amendment A2. Files and hashes: `data/splits/`. Audit (needs the workbook in `data/raw/`):

```
python scripts/context_audit.py            # writes splits, tables, docs/context_audit.md, results/audit/
python scripts/context_audit.py --check    # regenerates in a temporary folder and compares with the committed files
```

## Stage 1 baselines (P7)

The four baselines of `docs/spec.md` section 9 — enumeration, ordered scan, heuristic iteration, random search (seeds 0-9, budgets 10/20/50/|C|) — with checker-call accounting and the result store of spec section 12 (`src/ub_rl/baselines.py`, `src/ub_rl/runstore.py`):

```
python scripts/run_baselines1.py            # all 34,841 split contexts, about 50 minutes, single-threaded
python scripts/run_baselines1.py --limit 200   # quick smoke run
```

Results go to `results/baselines1/` (git-ignored): one CSV per method and split file, each with a `*_meta.json` (commit, environment-file SHA-256, hardware). The run asserts enumeration == ordered scan on every context, rechecks every output design and rejects a result file without its meta file.
