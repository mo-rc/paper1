"""Amendment A2: context box, splits, abstention list. Split tests need no workbook; checker tests skip without it."""
import csv
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from ub_rl import splits as S
from ub_rl.checker import Checker
from ub_rl.context import Context

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ROOT / "data" / "splits"
FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]


@pytest.fixture(scope="module")
def gen():
    return S.generate_all()


def rd(name):
    with open(SPLITS / f"{name}.csv", newline="", encoding="ascii") as f:
        return list(csv.DictReader(f))


def test_generation_is_deterministic(gen):
    again = S.generate_all()
    assert again == gen


def test_committed_files_equal_regenerated_and_use_lf(gen):
    for name in FILES:
        raw = (SPLITS / f"{name}.csv").read_bytes()
        assert b"\r" not in raw
        assert rd(name) == [{k: str(v) for k, v in r.items()} for r in gen[name]]


def test_manifest_hashes_match_files():
    lines = (SPLITS / "SHA256SUMS").read_text().strip().splitlines()
    assert len(lines) == len(FILES) + 2
    for line in lines:
        h, name = line.split("  ")
        assert S.sha256_file(SPLITS / name) == h


def test_sizes(gen):
    sizes = {k: len(v) for k, v in gen.items()}
    assert sizes == {"train": 20000, "val": 1000, "test_t1": 2000, "test_t2": 500, "test_t3": 2000, "test_t4": 1000, "test_t5": 3520, "v12_substudy": 4500, "reference": 4}
    c = Counter(r["set"] for r in gen["test_t3"])
    assert c == {"t3-E1": 500, "t3-E2": 500, "t3-E3": 500, "t3-E4": 500}


def test_every_row_is_a_valid_context(gen):
    for rows in gen.values():
        for r in rows:
            ctx = S.row_to_context(r)
            assert isinstance(ctx, Context)
            assert ctx.factored_udl()[0] == pytest.approx(float(r["w_factored"]), abs=1e-3)


def test_no_duplicate_contexts_across_files(gen):
    keys = [tuple(r[k] for k in S.COLUMNS[2:9]) for rows in gen.values() for r in rows]
    assert len(keys) == len(set(keys))


def _cell(r):
    return (float(r["restraint_ratio"]), r["deflection_rule"], S.cap_from_str(r["depth_cap"]))


def test_training_validation_t1_inside_box_outside_hole_and_trained_cells(gen):
    held, _ = S.held_out_cells()
    for name in ("train", "val", "test_t1"):
        for r in gen[name]:
            L, B, d, l, w = (float(r[k]) for k in ("span", "width", "dead", "live", "w_factored"))
            assert S.SPAN[0] <= L <= S.SPAN[1] and S.WIDTH[0] <= B <= S.WIDTH[1]
            assert S.DEAD[0] <= d <= S.DEAD[1] and S.LIVE[0] <= l <= S.LIVE[1] and S.W_BOX[0] <= w <= S.W_BOX[1]
            assert not S.in_hole(L, w)
            assert _cell(r) not in held and float(r["restraint_ratio"]) in S.RESTRAINT_TRAIN


def test_t2_is_the_hole_and_otherwise_in_distribution(gen):
    held, _ = S.held_out_cells()
    for r in gen["test_t2"]:
        L, w = float(r["span"]), float(r["w_factored"])
        assert S.in_hole(L, w) and S.W_BOX[0] <= w <= S.W_BOX[1] and _cell(r) not in held


def test_t3_sets_shift_exactly_what_they_say(gen):
    rows = {k: [r for r in gen["test_t3"] if r["set"] == k] for k in ("t3-E1", "t3-E2", "t3-E3", "t3-E4")}
    held, _ = S.held_out_cells()
    for r in rows["t3-E1"] + rows["t3-E3"]:
        assert 15.0 < float(r["span"]) <= 18.0
    for r in rows["t3-E2"] + rows["t3-E3"]:
        assert 100.0 < float(r["w_factored"]) <= 130.0
    for r in rows["t3-E1"] + rows["t3-E4"]:
        assert S.W_BOX[0] <= float(r["w_factored"]) <= S.W_BOX[1]
    for r in rows["t3-E2"] + rows["t3-E4"]:
        assert S.SPAN[0] <= float(r["span"]) <= S.SPAN[1]
    for r in rows["t3-E1"] + rows["t3-E2"] + rows["t3-E3"]:
        assert float(r["restraint_ratio"]) in S.RESTRAINT_TRAIN and _cell(r) not in held
    for r in rows["t3-E4"]:
        assert float(r["restraint_ratio"]) == S.RESTRAINT_HELD_OUT and not S.in_hole(float(r["span"]), float(r["w_factored"]))
    # E2 and E3 genuinely leave the training load ranges in at least one raw parameter in most contexts
    out = [any(not (lo <= float(r[k]) <= hi) for k, (lo, hi) in (("width", S.WIDTH), ("dead", S.DEAD), ("live", S.LIVE)))
           for r in rows["t3-E2"]]
    assert np.mean(out) > 0.5


def test_t5_lattice_is_exact_and_deterministic(gen):
    held, _ = S.held_out_cells()
    rows = gen["test_t5"]
    pts = {(float(r["span"]), float(r["width"]), float(r["dead"]), float(r["live"])) for r in rows}
    for L, B, d, l in pts:
        assert L in S.LATTICE["span"] and B in S.LATTICE["width"] and d in S.LATTICE["dead"] and l in S.LATTICE["live"]
    for r in rows:
        w = float(r["w_factored"])
        assert S.W_BOX[0] <= w <= S.W_BOX[1] and not S.in_hole(float(r["span"]), w) and _cell(r) not in held
        assert float(r["restraint_ratio"]) in S.RESTRAINT_TRAIN
    assert len(rows) == len(pts) * 40  # every lattice point in all 40 trained cells
    assert S.generate_all()["test_t5"] == rows


def test_v12_substudy_sets(gen):
    c = Counter(r["set"] for r in gen["v12_substudy"])
    assert c == {"s12-val": 500, "s12-t1": 2000, "s12-t2": 500, "s12-E1": 500, "s12-E2": 500, "s12-E3": 500}
    for r in gen["v12_substudy"]:
        L, w = float(r["span"]), float(r["w_factored"])
        assert float(r["width"]) == 6.0 and float(r["restraint_ratio"]) == 0.0 and r["deflection_rule"] == "var360"
        assert r["depth_cap"] == "none"
        # variable share fixed at the reference value (27 / 56.7675), up to rounding of dead and live
        q = 1.5 * float(r["live"]) * 6.0
        assert q / w == pytest.approx(27.0 / 56.7675, rel=2e-3)
        s = r["set"]
        assert S.in_hole(L, w) == (s == "s12-t2")
        if s in ("s12-E1", "s12-E3"):
            assert 15.0 < L <= 18.0
        else:
            assert 9.0 <= L <= 15.0
        if s in ("s12-E2", "s12-E3"):
            assert 100.0 < w <= 130.0
        else:
            assert 56.0 <= w <= 100.0


def test_restraint_never_in_excluded_interval(gen):
    for rows in gen.values():
        for r in rows:
            x = float(r["restraint_ratio"])
            assert x == 0.0 or 0.0 < x <= 0.5 or x == 1.0


def test_held_out_cells_and_t4(gen):
    held, attempt = S.held_out_cells()
    cells = S.all_cells()
    assert len(cells) == 48 and len(held) == S.N_HELD_OUT_CELLS and set(held) <= set(cells)
    assert (0.0, "var360", None) not in held
    train = [c for c in cells if c not in held]
    for i, j in ((0, 1), (0, 2), (1, 2)):  # only the triple is unseen
        assert {(c[i], c[j]) for c in train} == {(c[i], c[j]) for c in cells}
    assert all(_cell(r) in held for r in gen["test_t4"])
    assert all(_cell(r) not in held for r in gen["train"])
    assert {_cell(r) for r in gen["test_t4"]} == set(held)  # every held-out cell occurs in T4
    assert [(float(r["restraint_ratio"]), r["deflection_rule"], S.cap_from_str(r["depth_cap"])) for r in rd("heldout_cells")] == list(held)


def test_training_pool_covers_all_trained_cells(gen):
    held, _ = S.held_out_cells()
    assert {_cell(r) for r in gen["train"]} == set(S.all_cells()) - set(held)


def test_reference_rows(gen):
    ref = gen["reference"]
    assert [float(r["restraint_ratio"]) for r in ref] == list(S.RESTRAINT_TRAIN)
    assert all(r["w_factored"] == "56.7675" and r["deflection_rule"] == "var360" and r["depth_cap"] == "none" for r in ref)


def test_slice_flag(gen):
    for r in gen["train"][:2000]:
        assert int(r["slice_full_restraint"]) == int(float(r["restraint_ratio"]) == 0.0 and r["deflection_rule"] == "var360" and r["depth_cap"] == "none")


def test_load_split_returns_contexts():
    rows, ctxs = S.load_split("reference", root=SPLITS)
    assert len(rows) == len(ctxs) == 4 and ctxs[0] == Context(9.0, 6.0, 3.675, 3.0)


def test_audit_tables_consistent_with_abstention_list():
    ab = Counter(r["set"] for r in csv.DictReader(open(SPLITS / "abstention_contexts.csv", newline="")))
    with open(ROOT / "paper" / "tables" / "audit_sets.csv", newline="") as f:
        sets = {r["set"]: r for r in csv.DictReader(f)}
    for name, r in sets.items():
        assert int(r["n_abstain"]) == ab.get(name, 0) == int(r["abstain_code"]) + int(r["abstain_depth"])
        assert int(r["n"]) == int(r["n_feasible"]) + int(r["n_abstain"])
    with open(ROOT / "paper" / "tables" / "audit_rules.csv", newline="") as f:
        assert all(int(r["pass"]) for r in csv.DictReader(f))


# ---------------------------------------------------------------- need the workbook
def test_reference_optima_per_restraint(C):
    K = Checker(C)
    rows, ctxs = S.load_split("reference", root=SPLITS)
    got = [C.names[K.lightest_feasible_context(c)] for c in ctxs]
    assert got == ["457x191x74", "533x210x82", "610x229x101", "686x254x140"]


def test_abstention_list_matches_checker(C):
    K = Checker(C)
    ab = {r["id"]: r["status"] for r in csv.DictReader(open(SPLITS / "abstention_contexts.csv", newline=""))}
    for name, step in (("val", 1), ("test_t4", 1), ("test_t2", 1), ("test_t3", 2), ("train", 10)):
        rows, ctxs = S.load_split(name, root=SPLITS)
        for r, c in list(zip(rows, ctxs))[::step]:
            e = K.evaluate_context(c)
            exp = "feasible" if e["feasible"].any() else ("abstain_depth" if e["feasible_code"].any() else "abstain_code")
            assert ab.get(r["id"], "feasible") == exp


def test_abstention_is_never_removed_from_split_files(C):
    n_ab = sum(1 for _ in csv.DictReader(open(SPLITS / "abstention_contexts.csv", newline="")))
    n_all = sum(len(rd(f)) for f in FILES)
    assert n_all == 34524 and 0 < n_ab < n_all
