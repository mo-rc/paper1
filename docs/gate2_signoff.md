# Gate 2 sign-off record (P5)

Signed form: `docs/review_request_signed.md` (returned 23 October 2026). Supervising engineer: Dr. Mudasir Hussain. An earlier, superseded return is kept in `docs/archive/`.

## Result

| Item | Outcome |
|---|---|
| Assumptions 1 to 12 | All agreed by the supervising engineer |
| Missing or wrong checks | None reported (N/A) |
| Form | Signed and dated 23 October 2026 |

## Who did what

- **Assumptions (12):** reviewed and agreed by the supervising engineer.
- **Hand recomputation of the cases:** done by Muhammad Shifa by calculator (all 14 cases, 234 values; largest difference 0.28 %, within the 0.5 % tolerance), recorded in `data/gate2/handcheck_values.csv` and the hand-check workbook. The supervising engineer did not recompute each case independently; his sign-off rests on the assumptions and on the recorded hand check. The per-case table in the review request was not returned.
- **Resistances:** agree with the SCI Blue Book tables for all 107 sections (`docs/verification_record.md`).

## Note on assumption 4 (deflection)

Span/360 on variable load is the criterion chosen for this study (a conservative screening limit); total-load limits (L/250, L/200) are optional project-specific criteria. The paper describes them in those terms and does not present them as universal UK Eurocode limits.

## What the acceptance covers and does not cover

Covers: the program's checks as specified by the 12 assumptions (simply supported, UDL, S355 UB, EC3 with UK NA), verified against Blue Book values and by an arithmetic hand check on 14 cases.
Does not cover: the checks listed as outside scope in `docs/review_request.md` (axial force, torsion, openings, point loads, connections, fire, vibration, composite action) and loads on the top flange.

## Status

**Gate 2 accepted, 23 October 2026.**
