# Data

`data/raw/` holds the unmodified Steel for Life Blue Book download and is not tracked (licence terms not checked).
Place the file locally and verify its SHA-256 against `docs/spec.md` section 4 before use.

`data/catalogue/` holds the machine-readable catalogue derived from it by `scripts/build_catalogue.py`. It is not tracked either, for the same licence reason.

The Gate 2 comparison also reads the two Blue Book resistance workbooks `UB-bending-S355-EC3UKNA-UK-10-20-2026.xlsx` and `UB-webbearingbuckling-S355-EC3UKNA-UK-10-20-2026.xlsx` from `data/raw/` (not tracked; SHA-256 in `docs/verification_record.md`). Run `python scripts/gate2_bluebook.py`.
