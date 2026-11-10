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

The project proposal (one journal paper: Eurocode-verified environment, pre-registered benchmark, seven-parameter contexts including restraint and LTB, algorithm tournament, welded-section Stage 2) is in `docs/proposal.md`. The dated amendment A1 at the end of `docs/spec.md` records the matching changes to the pre-registration. Both await supervisor acceptance. The dated amendment A2 at the end of `docs/spec.md` fixes the seven-parameter sampling ranges, the depth caps (none, 700, 800, 900 mm) and the frozen train/validation/test splits (T1–T5, v1.2 sub-study) with their SHA-256; these values are recorded before any run and await supervisor confirmation (none is claimed here).

## Splits and context audit (P6)

Context ranges and splits: `docs/spec.md`, Amendment A2. Files and hashes: `data/splits/`. Audit (needs the workbook in `data/raw/`):

```
python scripts/context_audit.py            # writes splits, tables, docs/context_audit.md, results/audit/
python scripts/context_audit.py --check    # regenerates in a temporary folder and compares with the committed files
```
