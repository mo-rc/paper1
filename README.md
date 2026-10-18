# Generative and AI-Driven Design of Steel Beams

Reinforcement learning for safe, automated selection of standard UK Universal Beams.

Specification: `docs/spec.md`.

## Checker

```
pip install -e .[test]
python scripts/build_catalogue.py      # needs data/raw/<workbook>
python scripts/reference_case.py
pytest
```

Parser: `src/ub_rl/catalogue.py`. Checker: `src/ub_rl/checker.py`. Open assumptions are parameters in `src/ub_rl/config.py`. Clause status: `docs/verification_record.md`.
