# Paper readiness checklist

What a reviewer of a safety-critical, learning-based design paper will look for, where it is in this repository, and its state on 2026-10-24. Statuses are facts about files, not claims about results; no RL result exists.

| Reviewer expectation | Where | State |
|---|---|---|
| Question fixed before results (RL tested, not assumed better) | `docs/spec.md`, section 11 (claims and success criteria), amendments A1, A2 | done; later changes only by dated amendment |
| Checker verified independently | `docs/verification_record.md`, `docs/gate2_signoff.md`, second implementation, 14 hand-checked cases | done (Gate 2 accepted) |
| Honest limits of the Blue Book comparison | `docs/verification_record.md` | done |
| Fixed, hashed test data; test files untouched during tuning | `data/splits/SHA256SUMS`, spec section 8 and A2 | files and hashes done; freezing at Gate 4 (P12) |
| Distribution-shift tests: interpolation, held-out block, extrapolation, unseen restraint value, unseen combinations, lattice | T1 to T5 in A2 | done |
| Infeasible cases reported, not hidden | `data/splits/abstention_contexts.csv`, `paper/tables/audit_sets.csv` | done |
| Strong conventional baselines, including cheap ones | spec section 9; P7, P8 | planned |
| Check whether the problem leaves room for learning (saturation) | spec section 12; P9 | planned |
| Cost counted in checker calls, training and tuning included, break-even N* | spec section 10; P7, P13 | planned |
| Analysis written before results exist | P12 (analysis pipeline tested on synthetic data) | planned |
| Seeds, confidence intervals, multiple-comparison control | spec section 11; P13 | planned |
| Negative result reported as a result | spec section 11 and the saturation rule | rule recorded |
| Every number traceable to a file | spec section 12 (Gate 5): `results/` and `paper/tables/` only; `*_meta.json` with commit and environment hash | rule recorded; split and audit files follow it |
| Reproducible from the repository | `python scripts/context_audit.py --check`; later one script per result | audit done |
| Data licence | Blue Book workbooks are never committed; `data/README.md` | done; the release plan (P23) must state how readers obtain them |
| Limitations stated | spec section 13 | done |
