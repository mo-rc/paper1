"""The Blue Book comparison script (scripts/compare_bluebook.py) with synthetic and public inputs."""
import csv
import importlib.util
from pathlib import Path

import pytest

from ub_rl.checker import Checker

SPEC = importlib.util.spec_from_file_location("compare_bluebook", Path(__file__).resolve().parents[1] / "scripts" / "compare_bluebook.py")
cb = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cb)


def _row(**k):
    base = dict(section="", quantity="", value="", unit="", ss_mm="", c_mm="", Lcr_m="", C1="", kc="", source="", notes="")
    base.update({a: str(b) for a, b in k.items()})
    return base


def _rows(C, scale):
    K = Checker(C)
    i = C.names.index("457x191x74")
    ok, rows = [], []
    rows.append(_row(section="457x191x74", quantity="Mc_Rd", value=K.Mc[i] * scale))
    rows.append(_row(section="457x191x74", quantity="Vc_Rd", value=K.Vpl[i] * scale))
    rows.append(_row(section="457x191x74", quantity="F_Rd", value=K.F_Rd[i] * scale, ss_mm=100, c_mm=0))
    Mb = K.ltb_resistance([i], 6.0, C1=1.13)[2][0]
    rows.append(_row(section="457x191x74", quantity="Mb_Rd", value=Mb * scale, Lcr_m=6, C1=1.13))
    return rows


def test_values_within_tolerance_pass(C):
    res = cb.compare(_rows(C, 1.002), C, tol=0.01)
    assert len(res) == 4 and all(r["status"] == "PASS" for r in res)


def test_values_outside_tolerance_fail_both_directions(C):
    for scale in (1.03, 0.97):
        res = cb.compare(_rows(C, scale), C, tol=0.01)
        assert all(r["status"] == "FAIL" for r in res)


def test_empty_values_are_skipped_and_unknown_inputs_reported(C):
    rows = [_row(section="457x191x74", quantity="Mc_Rd"), _row(section="no_such", quantity="Mc_Rd", value=1),
            _row(section="457x191x74", quantity="Vb_Rd", value=1), _row(section="457x191x74", quantity="F_Rd", value=1)]
    res = cb.compare(rows, C)
    assert [r["status"] for r in res] == ["SKIP", "SKIP", "SKIP"]


def test_public_template_rows(C):
    path = Path(__file__).resolve().parents[1] / "data" / "gate2" / "bluebook_values.csv"
    rows = list(csv.DictReader(open(path, newline="")))
    res = cb.compare(rows, C, tol=0.01)
    status = {(r["section"], r["quantity"]): r["status"] for r in res}
    assert status[("406x140x39", "Vc_Rd")] == "PASS" and status[("406x140x39", "Vb_Rd")] == "PASS"
    assert status[("762x267x134", "Vc_Rd")] == "PASS"
    # known open item (docs/verification_record.md): the SCI note quotes the cap for this section
    assert status[("762x267x134", "Vb_Rd")] == "FAIL"
