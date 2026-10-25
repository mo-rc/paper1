# How to run the project

Plain steps for running the code. Run every command from the top folder of the repository (the folder that contains `README.md`). Use `python3` instead of `python` if your system needs it.

## 1. One-time setup

1. Copy the three Blue Book Excel workbooks into `data/raw/`. They are licensed, so git ignores them and they are never committed.
2. Install the packages:

```
pip install -e ".[test]"
```

## 2. The three commands you will use most

| Command | What it does | Good result |
|---|---|---|
| `python -m pytest -q` | Runs all automatic tests of the checker, the parser and the splits. About 15 seconds. | `154 passed` (with the workbooks present) |
| `python scripts/reference_case.py` | Designs one beam for the reference floor (9 m span) and prints the checks. | first line ends `lightest feasible = 457x191x74` |
| `python scripts/context_audit.py --check` | Rebuilds every split file and audit table in a temporary folder and compares them with the committed files. A few minutes. | `differing or missing: none` |

If `pytest` reports many `skipped`, the workbooks are not in `data/raw/`.

## 3. Reading the reference-case output

Each line is one beam section. `bend 0.998` means the bending check uses 99.8 % of the beam's capacity. A number at or below 1.000 passes; above 1.000 fails. `feasible=True` means every check passes. The lightest beam that is feasible is the optimum, here 457x191x74 (a 457 mm deep, 191 mm wide beam of 74 kg per metre). `C` is the main catalogue of 91 sections; `C+` is a larger 107-section catalogue used only as a sensitivity check.

## 4. What the folders hold

| Folder or file | Content |
|---|---|
| `src/ub_rl/checker.py` | The beam calculator: for a beam and a floor, which checks pass. Verified and finished. |
| `src/ub_rl/context.py` | One floor situation (span, width, loads, restraint, deflection rule, depth cap). |
| `src/ub_rl/splits.py` | Generates the lists of floor situations used for training and testing. |
| `data/splits/` | Those lists as CSV files, with `SHA256SUMS` (fingerprints). A changed file shows up as a changed fingerprint. |
| `data/splits/abstention_contexts.csv` | Floors for which no standard beam works (kept in the lists, never removed). |
| `paper/tables/audit_*.csv` | Audit tables; the numbers in the paper will come from files like these. |
| `docs/context_audit.md` | Short readable summary of the audit. |
| `docs/spec.md` | The fixed study plan (the pre-registration), with dated amendments A1 and A2. |
| `docs/patch_plan.md` | The list of work steps (patches) and what comes next. |
| `results/` | Output of runs. Git ignores it; each result file has a `*_meta.json` recording the code version. |

## 5. Things to know

- `python scripts/context_audit.py` without `--check` rewrites the split files and tables. With unchanged code the content is identical, so git shows no change. Use `--check` when you only want to verify.
- If `--check` says `differing`, do not edit anything. Send me the printed file names. A common cause on Windows is git converting line endings; run `git config core.autocrlf false` and check out the files again.
- No reinforcement learning has been run yet. The plan (`docs/patch_plan.md`) forbids it until Gate 3 is accepted.
