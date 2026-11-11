"""P9 script smoke tests: a --limit sample run must write the runstore results with complete metas,
the saturation table with V as the headline line, and a gate record naming every reward family. The
hardcoded P7 snapshot in the script must equal the committed P7 run summary. Skips without the
workbook (conftest) and without the P7 results directory (results/ is not committed).
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import landscape_diagnostics as LD  # noqa: E402

from ub_rl import runstore as RS  # noqa: E402


@pytest.fixture(scope="module")
def sample_run(tmp_path_factory, raw_path):
    out = tmp_path_factory.mktemp("p9_sample")
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "landscape_diagnostics.py"), raw_path,
         "--limit", "2", "--out", str(out)],
        capture_output=True, text=True, cwd=str(ROOT))
    assert r.returncode == 0, r.stderr[-2000:]
    return out


def test_sample_run_writes_all_outputs(sample_run):
    for name in ["p9_landscape.csv", "p9_horizon.csv", "p9_governing.csv", "p9_alternatives.csv",
                 "p9_saturation.csv", "p9_rewards.csv"]:
        assert (sample_run / "paper" / "tables" / name).exists()
    assert (sample_run / "docs" / "gate3_record.md").exists()
    assert (sample_run / "p9_summary.json").exists()
    assert (sample_run / "p9_summary.json_meta.json").exists()
    assert (sample_run / "p9_contexts_val.csv").exists()
    assert (sample_run / "p9_contexts_val.csv_meta.json").exists()


def test_saturation_csv_headline_line_is_val(sample_run):
    with open(sample_run / "paper" / "tables" / "p9_saturation.csv", newline="", encoding="ascii") as f:
        rows = list(csv.DictReader(f))
    assert rows and rows[0]["set"] == "val"
    assert {r["set"] for r in rows} == {"val", "train", "t1", "t2", "t3-E1", "t4-A", "t5", "s12-val", "ref"}
    for r in rows:
        # the exact count is over the feasible contexts, so the share is at most 1
        assert int(r["heuristic_exact"]) <= int(r["n_feasible"])
        assert float(r["exact_share"]) <= 1.0 + 1e-9
        assert int(r["ordered_scan_exact"]) == 1  # exact by definition on every context


def test_record_has_saturation_headline_and_family_rows(sample_run):
    text = (sample_run / "docs" / "gate3_record.md").read_text(encoding="ascii")
    pos = text.index("## Saturation (headline line: V)")
    section = text[pos:text.index("## ", pos + 4)]
    assert section.index("| val |") < section.index("| train |")
    for family in ("R1", "R2", "R3", "R-C", "R-D", "R3-b100"):
        assert family in text


def test_runstore_metas_are_complete_and_validate(sample_run):
    rows, meta = RS.load_results(sample_run / "p9_contexts_val.csv")
    assert meta["status"] == "complete" and meta["n_contexts"] == 2
    assert len(rows) == 2
    assert meta["method"] == "p9_landscape"
    summary_meta = json.loads((sample_run / "p9_summary.json_meta.json").read_text(encoding="ascii"))
    assert summary_meta["status"] == "complete" and summary_meta["n_contexts"] == 18
    summary = json.loads((sample_run / "p9_summary.json").read_text(encoding="ascii"))
    assert summary["limit"] == 2 and summary["p7_snapshot_ok"] is False


def test_horizon_table_flags_never_change_the_horizon(sample_run):
    assert LD.HORIZON_F1 == 12  # the spec horizon; the script only reports, it never changes it
    with open(sample_run / "paper" / "tables" / "p9_horizon.csv", newline="", encoding="ascii") as f:
        rows = list(csv.DictReader(f))
    assert "gt12" in rows[0] and "flag" in rows[0] and "share_gt12" in rows[0]
    for r in rows:
        assert int(r["gt12"]) == 0 or r["flag"].startswith("APPROVAL NEEDED")


@pytest.mark.skipif(not (ROOT / "results" / "baselines1" / "run_summary.json").exists(),
                    reason="P7 results directory not present (results/ is not committed)")
def test_p7_snapshot_matches_the_committed_summary():
    d = json.loads((ROOT / "results" / "baselines1" / "run_summary.json").read_text(encoding="ascii"))
    for f in d["files"]:
        expected = (f["n_feasible"], round(f["mean_calls"]["heuristic"], 3))
        assert LD.EXPECTED_P7[f["file"]] == expected, f["file"]
