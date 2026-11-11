# Gate 3 record - P9 landscape and saturation diagnostics

Provenance: `scripts/landscape_diagnostics.py`, commit e3c74630a0819040da49974dbdafadd57903d3dc, clean; environment `src/ub_rl/checker.py` sha256 3b6ab914e350726f...; catalogue workbook sha256 190e17b694bdb27a...; split manifest `data/splits/SHA256SUMS` sha256 51050584ac1d1488...; catalogue C (91 sections); 34841 contexts (full run); heuristic call accounting measured by the checker wrapper. Generated deterministically; `--check` reproduces this record byte for byte.

## Saturation (headline line: V)

Heuristic iteration against the enumeration optimum, per set. The ordered scan is exact by definition - its first feasible section in mass order is the lightest feasible section - and P7 verified enumeration = ordered scan on every context; its mean call count below is read from the enumeration mask. Heuristic outputs are rechecked; false abstentions are counted.

| set | n | n_feasible | heuristic exact | exact share | false abstain | infeasible outputs | feasibility share | heuristic calls (mean) | scan calls (mean) | rule met |
|---|---|---|---|---|---|---|---|---|---|---|
| val | 1000 | 796 | 796 | 1.0000 | 0 | 0 | 1.0000 | 14.193 | 64.24 | 1 |
| train | 20000 | 16723 | 16723 | 1.0000 | 0 | 0 | 1.0000 | 13.553 | 63.24 | 1 |
| t1 | 2000 | 1635 | 1635 | 1.0000 | 0 | 0 | 1.0000 | 13.740 | 63.56 | 1 |
| t2 | 500 | 388 | 388 | 1.0000 | 0 | 0 | 1.0000 | 15.302 | 66.77 | 1 |
| t3-E1 | 500 | 194 | 194 | 1.0000 | 0 | 0 | 1.0000 | 21.910 | 82.54 | 1 |
| t3-E2 | 500 | 304 | 304 | 1.0000 | 0 | 0 | 1.0000 | 17.070 | 74.70 | 1 |
| t3-E3 | 500 | 111 | 111 | 1.0000 | 0 | 0 | 1.0000 | 18.706 | 88.50 | 1 |
| t4-A | 1000 | 934 | 934 | 1.0000 | 0 | 0 | 1.0000 | 10.530 | 60.10 | 1 |
| t4-B | 500 | 470 | 470 | 1.0000 | 0 | 0 | 1.0000 | 8.590 | 58.52 | 1 |
| t5 | 3837 | 3102 | 3102 | 1.0000 | 0 | 0 | 1.0000 | 13.863 | 63.91 | 1 |
| s12-val | 500 | 500 | 500 | 1.0000 | 0 | 0 | 1.0000 | 2.236 | 53.03 | 1 |
| s12-t1 | 2000 | 2000 | 2000 | 1.0000 | 0 | 0 | 1.0000 | 2.279 | 53.08 | 1 |
| s12-t2 | 500 | 500 | 500 | 1.0000 | 0 | 0 | 1.0000 | 2.044 | 52.89 | 1 |
| s12-E1 | 500 | 500 | 500 | 1.0000 | 0 | 0 | 1.0000 | 2.566 | 64.60 | 1 |
| s12-E2 | 500 | 500 | 500 | 1.0000 | 0 | 0 | 1.0000 | 2.880 | 60.51 | 1 |
| s12-E3 | 500 | 500 | 500 | 1.0000 | 0 | 0 | 1.0000 | 2.908 | 72.69 | 1 |
| ref | 4 | 4 | 4 | 1.0000 | 0 | 0 | 1.0000 | 8.750 | 45.75 | 1 |

Saturation rule (spec section 12): heuristic iteration or the classifier at exact match >= 0.99 and feasibility 1.0 on V. Reading used here: the exact share is over the feasible contexts (abstentions excluded, false abstentions counted against it), and feasibility is the share of heuristic outputs that are feasible (rechecked; an abstention is not an output). On V: exact share 1.0000, false abstain 0, infeasible outputs 0 -> the rule is MET on V.

## Monotonicity counter

c1: a lighter section is feasible while a heavier one below it is not (any pair; c1_edges is the adjacent-edge count). c2: an infeasible section strictly between the optimum and the heuristic's trial section (the patch plan's phrasing). c2_block: the same between the optimum and the first feasible section at or above the trial - exactly the stretch the downward walk must pass, so c2_block = 0 means the walk reaches the optimum structurally.

| set | n_feasible | distinct optima | c1 | c1_edges | c2 | c2_block |
|---|---|---|---|---|---|---|
| train | 16723 | 32 | 14300 | 42257 | 0 | 0 |
| val | 796 | 31 | 676 | 2010 | 0 | 0 |
| t1 | 1635 | 31 | 1418 | 4176 | 0 | 0 |
| t2 | 388 | 20 | 347 | 1012 | 0 | 0 |
| t3-E1 | 194 | 22 | 160 | 252 | 0 | 0 |
| t3-E2 | 304 | 29 | 261 | 573 | 0 | 0 |
| t3-E3 | 111 | 19 | 64 | 93 | 0 | 0 |
| t4-A | 934 | 30 | 792 | 2439 | 0 | 0 |
| t4-B | 470 | 22 | 409 | 1216 | 0 | 0 |
| t5 | 3102 | 34 | 2663 | 7905 | 0 | 0 |
| s12-val | 500 | 15 | 271 | 290 | 0 | 0 |
| s12-t1 | 2000 | 16 | 1022 | 1118 | 0 | 0 |
| s12-t2 | 500 | 3 | 331 | 379 | 0 | 0 |
| s12-E1 | 500 | 11 | 436 | 547 | 0 | 0 |
| s12-E2 | 500 | 18 | 281 | 302 | 0 | 0 |
| s12-E3 | 500 | 11 | 142 | 179 | 0 | 0 |
| ref | 4 | 4 | 0 | 0 | 0 | 0 |

Monotonicity fails in 23573 contexts (c1); c2_block = 0. The P7 zero gap forces c2_block = 0 in every feasible context (the stretch from the optimum to the walk start has no infeasible section, so the downward walk reaches the optimum); non-monotone dips above the trial cannot be reached by the walk. These counts are the recorded explanation.

## F1 horizon check (spec section 9, horizon 12)

Fewest F1 actions from the trial section to the optimum on the actual action graph (mass step up/down, lightest section of the next strictly deeper or shallower series; accept terminates and is not counted; a no-op past either end costs a step but never shortens a path, so it is not an edge). Gate 3 verifies the optimum lies within 12 steps of the trial section on every split.

| set | n_feasible | max steps | share needing more than 12 |
|---|---|---|---|
| train | 16723 | 11 | 0.0000 |
| val | 796 | 10 | 0.0000 |
| t1 | 1635 | 11 | 0.0000 |
| t2 | 388 | 10 | 0.0000 |
| t3-E1 | 194 | 13 | 0.0206 |
| t3-E2 | 304 | 13 | 0.0033 |
| t3-E3 | 111 | 13 | 0.1081 |
| t4-A | 934 | 11 | 0.0000 |
| t4-B | 470 | 8 | 0.0000 |
| t5 | 3102 | 11 | 0.0000 |
| s12-val | 500 | 3 | 0.0000 |
| s12-t1 | 2000 | 3 | 0.0000 |
| s12-t2 | 500 | 3 | 0.0000 |
| s12-E1 | 500 | 5 | 0.0000 |
| s12-E2 | 500 | 5 | 0.0000 |
| s12-E3 | 500 | 5 | 0.0000 |
| ref | 4 | 6 | 0.0000 |

**APPROVAL NEEDED - the F1 horizon of 12 is NOT confirmed.** The sets below need more than 12 steps; the horizon was not changed, per instruction:

- t3-E1: 4 of 194 feasible contexts need more than 12 steps

- t3-E2: 1 of 304 feasible contexts need more than 12 steps

- t3-E3: 12 of 111 feasible contexts need more than 12 steps

## Governing check at the optimum

Checker.check at each context's optimum with the context's config applied (the checker's own tie-break, not a reimplementation); counts of the governing utilisation per set.

| set | n_feasible | bending | shear | shear_buckling | bending_shear | web_bearing | deflection | ltb |
|---|---|---|---|---|---|---|---|---|
| train | 16723 | 3064 | 0 | 0 | 0 | 107 | 3306 | 10246 |
| val | 796 | 158 | 0 | 0 | 0 | 6 | 152 | 480 |
| t1 | 1635 | 327 | 0 | 0 | 0 | 5 | 329 | 974 |
| t2 | 388 | 58 | 0 | 0 | 0 | 9 | 79 | 242 |
| t3-E1 | 194 | 61 | 0 | 0 | 0 | 0 | 37 | 96 |
| t3-E2 | 304 | 52 | 0 | 0 | 0 | 36 | 30 | 186 |
| t3-E3 | 111 | 16 | 0 | 0 | 0 | 4 | 22 | 69 |
| t4-A | 934 | 110 | 0 | 0 | 0 | 5 | 107 | 712 |
| t4-B | 470 | 0 | 0 | 0 | 0 | 0 | 5 | 465 |
| t5 | 3102 | 585 | 0 | 0 | 0 | 25 | 592 | 1900 |
| s12-val | 500 | 479 | 0 | 0 | 0 | 21 | 0 | 0 |
| s12-t1 | 2000 | 1900 | 0 | 0 | 0 | 100 | 0 | 0 |
| s12-t2 | 500 | 392 | 0 | 0 | 0 | 108 | 0 | 0 |
| s12-E1 | 500 | 498 | 0 | 0 | 0 | 2 | 0 | 0 |
| s12-E2 | 500 | 269 | 0 | 0 | 0 | 231 | 0 | 0 |
| s12-E3 | 500 | 404 | 0 | 0 | 0 | 96 | 0 | 0 |
| ref | 4 | 1 | 0 | 0 | 0 | 0 | 0 | 3 |

## Alternatives (within 5 % of optimal mass; depth differing by >= 50 mm)

| set | n_feasible | mean within 5 % | with > 1 | mean depth >= 50 | any |
|---|---|---|---|---|---|
| train | 16723 | 1.43 | 5901 | 0.42 | 5808 |
| val | 796 | 1.43 | 276 | 0.42 | 274 |
| t1 | 1635 | 1.41 | 563 | 0.40 | 554 |
| t2 | 388 | 1.39 | 125 | 0.39 | 125 |
| t3-E1 | 194 | 1.35 | 54 | 0.30 | 47 |
| t3-E2 | 304 | 1.47 | 107 | 0.45 | 104 |
| t3-E3 | 111 | 1.34 | 30 | 0.26 | 28 |
| t4-A | 934 | 1.48 | 373 | 0.46 | 361 |
| t4-B | 470 | 1.55 | 200 | 0.55 | 200 |
| t5 | 3102 | 1.42 | 1083 | 0.41 | 1066 |
| s12-val | 500 | 1.60 | 247 | 0.59 | 247 |
| s12-t1 | 2000 | 1.65 | 1027 | 0.65 | 1027 |
| s12-t2 | 500 | 1.87 | 353 | 0.87 | 353 |
| s12-E1 | 500 | 2.01 | 347 | 1.01 | 347 |
| s12-E2 | 500 | 2.14 | 386 | 1.14 | 386 |
| s12-E3 | 500 | 1.62 | 285 | 0.60 | 285 |
| ref | 4 | 1.25 | 1 | 0.25 | 1 |

## Reward ordering on V (float64 log-space)

The assertion: for every validation context and every family, the smallest return over all feasible candidates exceeds the largest return over all infeasible candidates, in float64 log-space, with a margin at or above the analytic bound (R1/R2/R-C 0.988, R3 10, R-D 0.5). A candidate is a (section, calls 0..12) pair; contexts with no feasible or no infeasible candidate are vacuous and counted, not failed.

| key | family | beta | n | non-vacuous | vacuous | min margin | bound | violations | pass |
|---|---|---|---|---|---|---|---|---|---|
| R1 | R1 |  | 1000 | 796 | 204 | 0.988 | 0.988 | 0 | 1 |
| R2 | R2 |  | 1000 | 796 | 204 | 0.9879999999999995 | 0.988 | 0 | 1 |
| R3-b25 | R3 | 25 | 1000 | 796 | 204 | 10.0 | 10.0 | 0 | 1 |
| R3-b50 | R3 | 50 | 1000 | 796 | 204 | 10.0 | 10.0 | 0 | 1 |
| R3-b100 | R3 | 100 | 1000 | 796 | 204 | 10.0 | 10.0 | 0 | 1 |
| R-C | R-C |  | 1000 | 796 | 204 | 0.988 | 0.988 | 0 | 1 |
| R-D | R-D |  | 1000 | 796 | 204 | 0.5 | 0.5 | 0 | 1 |

The assertion holds: zero violations on every validation context and every family, margins at or above the analytic bounds.

## What the paper can claim

- The F1 horizon precondition is NOT confirmed; the paper must record the flagged sets and the amendment decision before training.

- Monotonicity fails in 23573 contexts; c2_block = 0 is the recorded explanation of why the P7 zero gap still holds.

- Saturation on V: the heuristic reaches exact match >= 0.99 with feasibility 1.0 on V (spec section 12), so the study reports that a learned policy has no quality headroom on V; RL still runs for sample efficiency, diversity and cost, and no quality-superiority claim is possible there.

- The reward-ordering property holds on every validation context for every family in float64 log-space, so the families separate feasible from infeasible candidates (Gate 3's reward asserts).

## Assumptions and readings

1. Saturation exact share is over feasible contexts; false abstentions count against it; feasibility is the share of rechecked heuristic outputs that are feasible.
2. The ordered scan is exact by definition and P7-verified; it is not re-run, its mean call count comes from the enumeration mask.
3. Mean heuristic calls are over all n contexts including abstentions (the P7 convention).
4. The horizon check counts actions on the actual F1 graph; accept terminates and is not counted; no-ops past the ends are not graph edges.
5. Catalogue C only (91 sections); C+ is a sensitivity and out of scope here.
6. On a full run the per-file feasible counts and mean heuristic calls must reproduce the P7 snapshot exactly (asserted by the script); sample runs skip the assertion and say so.
