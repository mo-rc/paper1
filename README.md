# Generative and AI-Driven Design of Steel Beams

Reinforcement learning for safe, automated selection of standard UK Universal Beams.

Specification: `docs/spec.md`. Engineering concepts, formulas and code names for readers new to structural engineering: `docs/engineering_concepts.md`.

## Checker

```
pip install -e .[test]
python scripts/build_catalogue.py      # needs data/raw/<workbook>
python scripts/reference_case.py
pytest
```

Parser: `src/ub_rl/catalogue.py`. Checker: `src/ub_rl/checker.py`. Open assumptions are parameters in `src/ub_rl/config.py`. Clause status: `docs/verification_record.md`.


## Research proposal

The project proposal (one journal paper: Eurocode-verified environment, pre-registered benchmark, seven-parameter contexts including restraint and LTB, algorithm tournament, welded-section Stage 2) is in `docs/proposal.md`. The dated amendment A1 at the end of `docs/spec.md` records the matching changes to the pre-registration. Both await supervisor acceptance.
