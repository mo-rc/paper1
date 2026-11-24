# P14 plan — Stage 2 welded-section checker (plan only)

Status: **PLAN ONLY.** A4 is **DRAFT** until recorded as a dated amendment in `docs/spec.md`; the spec governs until then. This plan authorizes no implementation and no Stage 2 result. **READ** — `docs/a4_proposal.md:3`; `docs/spec.md:3,256`; `docs/patch_plan.md:45-47`.

## Scope and gate

- **P14a:** plate geometry/grid, section properties, yield strength, classification with Class 4 rejected, bending and deflection. Return partial-check outcomes only; this is not a feasibility decision. **READ** — `docs/a4_proposal.md:10,18-19`; `docs/spec.md:53-54,64-73,79-80`.
- **P14b:** shear, shear buckling, web bearing and LTB. Do not start each check until its required value/rule is recorded with clause number in `docs/verification_record.md`. **READ** — `docs/a4_proposal.md:20,65-66`; `docs/patch_plan.md:45`.
- New module(s) only. Do not change the Stage 1 checker/tests, frozen splits or hashes. Later acceptance requires the full suite to preserve the Stage 1 result and pass new tests. **READ** — `docs/a4_proposal.md:9`; `docs/spec.md:261,331-345`; `docs/patch_plan.md:45`.

## P14a Step 1 specification

- Grid: integer dimensions in millimetres, using A4 bounds/increments and predicates `h>=b`, `h>2tf`, `b>tw`, and `10*h < 31*b`; count is 710,325. **READ** — `docs/a4_proposal.md:10,23`; `docs/spec.md:256`.
- Yield strength: use the maximum of `tf` and `tw`, with the thickness bands in the spec. **READ** — `docs/spec.md:53-54,79-80`.
- Classification: classify flange outstand and web; a design is Class 4 if either requires it, and P14a rejects Class 4. **READ** — `docs/spec.md:64,78-80`; `docs/a4_proposal.md:19`.
- Compute section properties using the A4 equations; do not duplicate those equations here. **READ** — `docs/a4_proposal.md:18`.
- Welded-section mass per metre is section area multiplied by a steel density whose value and source are recorded. Do not choose a density until its value and authoritative source are recorded in `docs/verification_record.md`. Then include self-weight in ULS demand: `g = mass_per_m × 9.80665 / 1000 kN/m`; `w_Ed = w_superimposed + 1.35 × g`. **READ** — `docs/spec.md:30-37,48`; `src/ub_rl/checker.py:84-88,152-155`; **ASSUMPTION** — mass from area times density pending source/value record.
- Bending: check demand against applicable section resistance for supported classes; deflection: compare the specified calculated deflection with the configured limit. P14a reports these partial outcomes only. **READ** — `docs/spec.md:65,73-74,79`; `docs/a4_proposal.md:21`.
- Status contract: each partial result has `complete=False`, `feasible=None`, and a `passes_p14a_checks` mapping of P14a check names to outcomes. Include `depth_ok = (depth_cap is None or h <= depth_cap)` as a separate partial outcome; it is context-specific depth compliance, not section-geometry validity. Neither `depth_ok` nor self-weight may cause P14a to report full structural feasibility. P14b fields remain unavailable, never treated as passes. `lightest_feasible_context()` and every feasibility-search API raise `NotImplementedError` until P14b is complete. Grid enumeration to count 710,325 is permitted but is not a per-context feasibility result. **ASSUMPTION** — explicit status/API guard prevents partial checks being mistaken for full verification. **READ** — `src/ub_rl/checker.py:146,265,299-317`; `src/ub_rl/context.py:21-29,45-48`.

P14a is built in two parts: P14a-1 (no steel density needed: grid, section properties, resistances, classification, depth_ok, guards, cache) and P14a-2 (after the density is recorded: mass, self-weight, demand, bending and deflection utilisations); shear resistance is P14b.

## P14a-2 specification

- **PROVISIONAL project convention:** `rho = 7850 kg/m³`, sourced to `docs/engineering_concepts.md:95` and recorded provisionally in `docs/verification_record.md`. The authoritative standard, edition and clause remain unconfirmed. **READ** — `docs/engineering_concepts.md:95`; `docs/verification_record.md`.
- Given a recorded density `rho` in kg/m³, convert section area `A` in mm² as `mass_per_m = A * rho / 1,000,000` kg/m; the factor converts mm² to m². **ASSUMPTION** — dimensional conversion; **READ** — area formula `docs/a4_proposal.md:18`; mass objective `docs/spec.md:48`.
- Use `g = mass_per_m * 9.80665 / 1000` kN/m and `w_Ed = w_superimposed + 1.35*g`; ULS bending demand is `M_Ed = w_Ed*L²/8` kN·m. **READ** — `docs/spec.md:30-37`; `src/ub_rl/checker.py:146-160`.
- Deflection rules: `var360` and `var200` use variable load `Q_k` only, so do not depend on self-weight; `tot250` uses total characteristic `G_k + g + Q_k`, so it depends on self-weight. Preserve each rule's registered limit and calculate deflection using the applicable load and `I_y`. **READ** — `docs/spec.md:73-76,199`; `src/ub_rl/context.py:13-18`; `src/ub_rl/checker.py:164-171,299-306`.
- API: replace unavailable `u_bending` and `u_deflection` with computed utilisations; add mass-per-metre and P14a-2 self-weight/load/demand/deflection values. Shear, shear buckling, bending-shear interaction, web bearing and LTB fields stay unavailable for P14b. Keep `complete=False` and `feasible=None` until P14b. **READ** — `src/ub_rl/welded_checker.py:41-54,96-113`; `docs/p14_plan.md:8,19`.
- Tests: include a hand-calculated area-to-mass, self-weight and bending-demand case using only the density recorded in the verification record; test one case for each of `var360`, `var200`, and `tot250`, including that only `tot250` changes when self-weight is included. **ASSUMPTION** — focused test design; **READ** — `docs/spec.md:36-37,73-74`; `src/ub_rl/checker.py:152-169`; `src/ub_rl/context.py:13-18`.
- The provisional entry exists in the verification record; the clause must be confirmed before P15 and before any Stage 2 claim, and any required dated A4 amendment/authorization must be made. Once those gates are satisfied, the smallest separately reviewable authorization is P14a-2 mass, self-weight, ULS bending demand and three deflection rules only; P14b remains gated. **ASSUMPTION** — proposed authorization boundary; **READ** — `docs/a4_proposal.md:3,20,65-66`; `docs/p14_plan.md:3,8`.

## New-module API and units

- **ASSUMPTION:** add `src/ub_rl/welded_sections.py` and, if useful, `src/ub_rl/welded_checker.py`; no existing source module is changed.
- Match checker style: `WeldedChecker(config=None)`; `evaluate_context(ctx, designs=None)` returns one dictionary containing NumPy arrays for the evaluated designs; `check(ctx, design)` returns one partial-result dictionary; `lightest_feasible_context(ctx)` raises `NotImplementedError` until P14b completion. **READ** — existing style: `src/ub_rl/checker.py:76-81,146-147,265-267,299-317`.
- Proposed helpers: `make_grid()` returns canonical integer `(h,b,tw,tf)` tuples; `section_properties(design)` returns P14a properties/classification; `evaluate_p14a(design, ctx)` returns the partial status, check outcomes and counters. **ASSUMPTION** — these names and dictionary contracts are new interfaces.
- Units: geometry/property lengths in mm; forces in N, stresses in N/mm², moments in N·mm; material S355. Convert context span/load at the API boundary consistently with the existing checker, whose context uses metres and kN/m internally. **READ** — `src/ub_rl/checker.py:1-4,146`; `docs/spec.md:30-37,51-56`.
- Invalid or off-grid geometry is returned as an invalid partial result, never rounded silently at the P14a API; callers must provide canonical grid designs. **ASSUMPTION** — P14a API validates rather than projects proposals. **READ** — `docs/a4_proposal.md:16-17`.
- Cache scope and counters: cache canonical design plus context per `WeldedChecker` instance. Report full checker calls, continuous structural evaluations, cache hits, and elapsed wall-clock separately; the approved counter policy remains as stated in A4. **READ** — `docs/a4_proposal.md:16-17`; **ASSUMPTION** — cache is instance-local.
- Engineering terms: *yield strength* is the stress limit used for resistance; *classification* describes plate slenderness; *utilisation* is demand/resistance; *partial result* means only P14a checks were run. **READ** — `docs/spec.md:53-54,60,64`; `docs/a4_proposal.md:18-19`.

## Focused tests and work order

1. Implement P14a in new module(s), with equations in docstrings citing `docs/spec.md` and `docs/a4_proposal.md` line references. Add tests for grid predicates/count, classification and Class 4 rejection, bending/deflection, partial status, units, invalid input and API guards. **STOP for review.** **READ** — `docs/spec.md:53-54,64-73,79-80`; `docs/a4_proposal.md:10,18-19`; `docs/patch_plan.md:45`.
2. After review, run focused P14a tests and full suite; verify the Stage 1 result is unchanged and new tests pass. **STOP for review.** Needs the project lead's test command. **READ** — `docs/patch_plan.md:45`.
3. For each P14b value/rule, read its Eurocode/UK National Annex source, record the clause and value in `docs/verification_record.md`, and seek review before coding that check. **STOP for review after each check's inputs.** **READ** — `docs/a4_proposal.md:20,65-66`; `docs/patch_plan.md:45`.
4. Implement P14b only after its records are reviewed; test shear, shear buckling, bearing/end-post and LTB boundaries. **STOP for review.** Requires separate P14b authorization. **READ** — `docs/patch_plan.md:45`.

P14a tests must include the 710,325 grid count; integer boundary cases `(610,200)` valid, `(620,200)` exactly 3.1 and rejected, `(630,200)` invalid; and grid ordering by mass then `(h,b,tw,tf)` ascending. Also test Class 4 rejection and cache behavior: first unique design/context costs one call, repeated evaluation costs zero additional calls. **READ** — `docs/a4_proposal.md:16,19,23`; **ASSUMPTION** — test details and expected ordering.

## Out of scope and open items

- Out of scope: P15 independent verification; P16 baselines/audit; P17 environments, agents, pilots/freeze; P18 training or any run. **READ** — `docs/patch_plan.md:47-53`.
- **TO READ FROM STANDARD:** P14b shear area/eta, shear-buckling criterion and parameters, web-bearing/end-post rule, LTB values and applicable route/factors. Do not invent values or claim verification. **READ** — `docs/a4_proposal.md:20,65-66`; `docs/patch_plan.md:45`.
- **ASSUMPTION:** the available files do not specify final constructor configuration fields, result serialization schema, or cache lifetime beyond one instance; use the contracts above pending review. **READ** — `src/ub_rl/checker.py:76-81,146,299-317`; `docs/a4_proposal.md:16-17`.
