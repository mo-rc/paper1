"""The committed hand-check record (data/gate2/handcheck_values.csv): coverage, tolerance, and agreement of its program column with the checker."""
import csv
import os
import pytest
from dataclasses import replace

from ub_rl.checker import Checker
from ub_rl.config import CheckerConfig

D = os.path.join(os.path.dirname(__file__), "..", "data", "gate2")


def rows():
    with open(os.path.join(D, "handcheck_values.csv"), newline="") as f:
        return list(csv.DictReader(f))


def test_coverage_and_tolerance():
    r = rows()
    assert len(r) == 234 and len({x["case"] for x in r}) == 14
    entered = [x for x in r if x["entered"] != ""]
    assert len(entered) == 234  # every cell entered
    for x in entered:
        p, m = float(x["program"]), float(x["entered"])
        assert abs((m - p) / p) <= 0.005, x
        assert abs(float(x["diff_percent"]) - 100 * (m - p) / p) < 1e-3


def test_program_column_is_current_checker_output(full):
    """The highest utilisation recorded for each case equals what the checker gives now (needs the Blue Book properties workbook)."""
    C = full.mass_ordered(False)
    with open(os.path.join(D, "cases.csv"), newline="") as f:
        cases = {c["id"]: c for c in csv.DictReader(f)}
    for x in rows():
        if x["quantity"] != "Highest utilisation":
            continue
        c = cases[x["case"]]
        rho = float(c["restraint_ratio"])
        rho = 1 / 3 if abs(rho - 1 / 3) < 1e-3 else rho
        mode = "variable" if c["deflection"].startswith("variable") else "total"
        K = Checker(C, replace(CheckerConfig(), restraint_ratio=rho, deflection_load=mode, deflection_ratio=float(c["deflection"].split("L/")[1])))
        r = K.check(float(c["L_m"]), float(c["w_kNm"]), C.index_of(c["section"]))
        assert abs(r.max_utilisation - float(x["program"])) < 1e-9, x["case"]
