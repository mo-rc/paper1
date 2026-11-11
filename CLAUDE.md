# Project rules
- Project: RL selection of UK Universal Beams. Negative result is valid.
- Never change: checker, physics, objective, fixed assumptions.
- No RL training before Gate 3 is accepted.
- Tell me before any heavy computation (more than ~5 min).
- Do not ask questions: decide, state the assumption, record it.
- Mark every claim with a file path and VERIFIED or READ.
- Explain each engineering term in one line. Short plain replies.
- Orientation: read docs/project_review.md and docs/patch_plan.md only.
- Verify with: python -m pytest -q (155 pass); YOu have already verified, no-need of re-verification
  python scripts/context_audit.py --check (22 files, none differing).
- conda env is rl_env for this project

-  Co-Authored-By: MuhammadShifa <muhammadshifa102@gmail.com>