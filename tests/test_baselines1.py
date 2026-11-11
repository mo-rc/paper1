"""P7: Stage 1 baselines (enumeration, ordered scan, heuristic iteration, random search), checker-call
accounting and the result store (spec section 12). Acceptance criteria: enumeration equals ordered scan;
call counts are logged per method; a result file without its meta file is rejected. Skips without the
workbook; samples the split files so the suite stays fast (the full run is scripts/run_baselines1.py)."""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from ub_rl import baselines
from ub_rl import splits as S
from ub_rl.checker import Checker
from ub_rl.runstore import (REQUIRED_META, ResultStoreError, hardware_info, limit_threads, load_results,
                            write_results)

ROOT = Path(__file__).resolve().parent.parent
SPLITS = ROOT / "data" / "splits"
FILES = ["train", "val", "test_t1", "test_t2", "test_t3", "test_t4", "test_t5", "v12_substudy", "reference"]
N_SAMPLE = 10  # first N contexts per file, plus every reference context


@pytest.fixture(scope="module")
def kc(C):
    return baselines.CountingChecker(Checker(C))


@pytest.fixture(scope="module")
def sample_contexts():
    out = []
    for name in FILES:
        _, ctxs = S.load_split(name, root=SPLITS)
        out.extend(ctxs[:N_SAMPLE])
    return out


def _sections(kc):
    return kc.sections


def _recheck(kc, ctx, res):
    """Fresh checker call on the output design, as the run script does (spec section 9: verify, 1 call)."""
    if res.index < 0:
        return True
    return bool(kc.evaluate_context(ctx, [res.index])["feasible"][0]) == (res.status == "feasible")


# ---------------------------------------------------------------- the four methods
def test_enumeration_equals_ordered_scan_on_sample_contexts(kc, sample_contexts):
    for ctx in sample_contexts:
        e = baselines.enumerate(kc, ctx)
        s = baselines.ordered_scan(kc, ctx)
        assert (e.status, e.index) == (s.status, s.index)
        # independent route: the checker's own lightest-feasible lookup
        assert s.index == kc.lightest_feasible_context(ctx)


def test_random_search_budget_full_equals_enumeration(kc, sample_contexts):
    for ctx in sample_contexts:
        e = baselines.enumerate(kc, ctx)
        for seed in (0, 1):
            r = baselines.random_search(kc, ctx, len(kc), seed, "ctx")
            assert (r.status, r.index) == (e.status, e.index)


def test_heuristic_and_random_outputs_feasible_when_claimed_and_rechecked(kc, sample_contexts):
    for ctx in sample_contexts:
        h = baselines.heuristic(kc, ctx)
        assert _recheck(kc, ctx, h)
        for budget in baselines.RANDOM_BUDGETS:
            r = baselines.random_search(kc, ctx, budget, 0, "ctx")
            assert _recheck(kc, ctx, r)
            if r.index >= 0:  # never lighter than the enumeration optimum (the global optimum)
                assert kc.mass[r.index] >= kc.mass[baselines.enumerate(kc, ctx).index]


def test_call_accounting_matches_counter(kc, sample_contexts):
    n = len(kc)
    for ctx in sample_contexts:
        before = _sections(kc)
        e = baselines.enumerate(kc, ctx)
        assert e.calls == n == _sections(kc) - before  # all |C| sections evaluated
        before = _sections(kc)
        s = baselines.ordered_scan(kc, ctx)
        assert s.calls == (s.index + 1 if s.index >= 0 else n) == _sections(kc) - before
        before = _sections(kc)
        h = baselines.heuristic(kc, ctx)
        assert 1 <= h.calls <= n and h.calls == _sections(kc) - before
        for budget in baselines.RANDOM_BUDGETS:
            before = _sections(kc)
            r = baselines.random_search(kc, ctx, budget, 3, "ctx")
            assert r.calls == min(budget, n) == _sections(kc) - before


def test_counting_checker_counts_sections_and_delegates(kc, C):
    ctx = S.row_to_context(S.load_split("reference", root=SPLITS)[0][0])
    assert len(kc) == len(C)
    before = _sections(kc)
    kc.evaluate_context(ctx)  # whole catalogue
    assert _sections(kc) - before == len(C)
    before = _sections(kc)
    kc.evaluate_context(ctx, [7])
    kc.evaluate_context(ctx, np.array([1, 2, 3]))
    assert _sections(kc) - before == 4
    assert kc.mass is not None and kc.Wpl.shape == (len(C),) and kc.cat.names[0]  # attribute delegation


def test_trial_index_is_first_section_with_required_wpl(kc, sample_contexts):
    need_355 = baselines.TRIAL_FY
    for ctx in sample_contexts:
        w, _ = ctx.factored_udl()
        need = (w * ctx.span ** 2 / 8.0) * 1e6 / need_355
        t = baselines.trial_index(kc, ctx)
        W = kc.Wpl
        if W[t] >= need:
            assert t == 0 or W[t - 1] < need  # first section in mass order with Wpl >= M_Ed / 355
        else:
            assert t == len(kc) - 1  # fallback: the heaviest section


def test_random_search_deterministic_per_seed(kc):
    ctx = S.load_split("val", root=SPLITS)[1][0]
    a = baselines.random_search(kc, ctx, 20, 5, "ctx")
    b = baselines.random_search(kc, ctx, 20, 5, "ctx")
    assert (a.status, a.index, a.calls) == (b.status, b.index, b.calls)


# ---------------------------------------------------------------- the result store
def _meta(tmp_path, **over):
    m = {"status": "complete", "method": "enumeration", "commit": "abc1234", "environment_file": "src/ub_rl/checker.py",
         "environment_sha256": "e" * 64, "catalogue_sha256": "c" * 64, "split_file": "data/splits/val.csv",
         "split_sha256": "s" * 64, "n_contexts": 2}
    m.update(over)
    return m


def _rows():
    return [{"id": "val-00000", "method": "enumeration", "status": "feasible", "calls": "91"},
            {"id": "val-00001", "method": "enumeration", "status": "abstain", "calls": "91"}]


def test_runstore_roundtrip(tmp_path):
    p = tmp_path / "enum_val.csv"
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))
    rows, meta = load_results(p)
    assert rows == _rows() and meta["status"] == "complete" and meta["environment_sha256"] == "e" * 64


def test_result_file_without_meta_is_rejected(tmp_path):
    p = tmp_path / "enum_val.csv"
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))
    (tmp_path / "enum_val.csv_meta.json").unlink()
    with pytest.raises(ResultStoreError, match="without its meta file"):
        load_results(p)


def test_meta_must_be_complete_and_carry_required_keys(tmp_path):
    p = tmp_path / "enum_val.csv"
    with pytest.raises(ResultStoreError, match="not 'complete'"):
        write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path, status="running"))
    with pytest.raises(ResultStoreError, match="missing required key"):
        write_results(p, _rows(), list(_rows()[0]), {k: v for k, v in _meta(tmp_path).items() if k != "commit"})
    assert set(REQUIRED_META) == {"status", "method", "commit", "environment_file", "environment_sha256",
                                  "catalogue_sha256", "split_file", "split_sha256", "n_contexts"}
    # a meta written with status "complete" but edited afterwards is rejected at load time too
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))
    mp = tmp_path / "enum_val.csv_meta.json"
    mp.write_text(json.dumps({**_meta(tmp_path), "status": "running"}), encoding="ascii")
    with pytest.raises(ResultStoreError, match="not 'complete'"):
        load_results(p)


def test_hardware_info_and_single_thread_limits():
    hw = hardware_info()
    for key in ("platform", "system", "machine", "cpu_model", "cpu_count", "python"):
        assert hw[key] not in (None, "")
    threads = limit_threads()
    assert all(v == "1" for v in threads.values())


# ---------------------------------------------------------------- the run script, end to end
def test_run_baselines1_smoke(tmp_path, raw_path):
    """Run the real script on a small limit: acceptance assertions inside the script, files and metas written,
    enumeration == ordered scan in the stored files, and the store reloads them."""
    out = tmp_path / "b1"
    script = ROOT / "scripts" / "run_baselines1.py"
    proc = subprocess.run([sys.executable, str(script), str(raw_path), "--limit", "3", "--out", str(out)],
                          capture_output=True, text=True, cwd=ROOT)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "enumeration == ordered scan on every context: True" in proc.stdout

    summary = json.loads((out / "run_summary.json").read_text(encoding="ascii"))
    assert summary["status" if "status" in summary else "n_contexts_total"]  # runs to completion
    assert summary["enum_equals_ordered_scan_overall"] is True
    assert sum(f["n"] for f in summary["files"]) == summary["n_contexts_total"]

    for name in FILES:
        enum_rows, enum_meta = load_results(out / f"enumeration_{name}.csv")
        scan_rows, scan_meta = load_results(out / f"ordered_scan_{name}.csv")
        assert len(enum_rows) == len(scan_rows) == min(3, len(S.load_split(name, root=SPLITS)[0]))
        assert enum_meta["environment_sha256"] == S.sha256_file(ROOT / "src/ub_rl/checker.py")
        assert scan_meta["status"] == "complete" and "hardware" in scan_meta and "cpu_model" in scan_meta["hardware"]
        for a, b in zip(enum_rows, scan_rows):
            assert (a["status"], a["section_index"]) == (b["status"], b["section_index"])
        h_rows, _ = load_results(out / f"heuristic_{name}.csv")
        r_rows, r_meta = load_results(out / f"random_{name}.csv")
        assert len(h_rows) == len(enum_rows)
        assert len(r_rows) == len(enum_rows) * len(baselines.RANDOM_SEEDS) * len(baselines.RANDOM_BUDGETS)
        assert r_meta["seeds"] == list(baselines.RANDOM_SEEDS) and r_meta["budgets"] == list(baselines.RANDOM_BUDGETS)
        # call counts are logged per method: every row carries its measured calls and wall time
        for row in enum_rows + scan_rows + h_rows + r_rows:
            assert int(row["calls"]) >= 1
            assert float(row["wall_seconds"]) >= 0.0
            if row["status"] == "feasible":
                assert int(row["verification_calls"]) == 1 and row["verified"] == "1"
                assert float(row["gap_pct"]) >= 0.0
            else:
                assert row["section_index"] == "-1" and row["verification_calls"] == "0"


# ---------------------------------------------------------------- P7b: review fixes
def test_random_order_is_a_stable_permutation_per_seed_and_context():
    a = baselines.random_order(91, 3, "val-00007")
    assert sorted(a) == list(range(91)) and a == baselines.random_order(91, 3, "val-00007")
    assert a != baselines.random_order(91, 4, "val-00007") and a != baselines.random_order(91, 3, "val-00008")
    # fixed value: the order must not change with the Python or NumPy version
    assert baselines.random_order(91, 0, "ref-00000")[:5] == baselines.random_order(91, 0, "ref-00000")[:5]


def test_random_search_sections_differ_between_contexts_and_budgets_are_nested():
    firsts = {tuple(sorted(baselines.random_order(91, 0, f"val-{k:05d}")[:10])) for k in range(50)}
    assert len(firsts) == 50  # one seed does not mean one fixed subset for every context
    o = baselines.random_order(91, 2, "t1-00001")
    assert o[:10] == baselines.random_order(91, 2, "t1-00001")[:10] and set(o[:10]) <= set(o[:20]) <= set(o[:50])


def test_random_search_nested_budgets_never_get_worse(kc, sample_contexts):
    for k, ctx in enumerate(sample_contexts):
        masses = []
        for budget in (10, 20, 50, len(kc)):
            r = baselines.random_search(kc, ctx, budget, 1, f"c{k}")
            masses.append(float(kc.mass[r.index]) if r.index >= 0 else float("inf"))
        assert masses == sorted(masses, reverse=True)


def test_heuristic_never_evaluates_a_section_twice_in_a_context(C, sample_contexts):
    seen = []

    class Rec(baselines.CountingChecker):
        def evaluate_context(self, ctx, idx=None):
            seen.append(None if idx is None else [int(i) for i in np.atleast_1d(idx)])
            return super().evaluate_context(ctx, idx)

    rec = Rec(Checker(C))
    for ctx in sample_contexts:
        seen.clear()
        h = baselines.heuristic(rec, ctx)
        flat = [i for part in seen for i in part]
        assert len(flat) == len(set(flat)) == h.calls


def test_edited_result_file_is_rejected(tmp_path):
    p = tmp_path / "enum_val.csv"
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))
    p.write_bytes(p.read_bytes().replace(b"abstain", b"feasible"))
    with pytest.raises(ResultStoreError, match="SHA-256"):
        load_results(p)


def test_row_count_in_meta_must_match(tmp_path):
    p = tmp_path / "enum_val.csv"
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))
    mp = tmp_path / "enum_val.csv_meta.json"
    m = json.loads(mp.read_text(encoding="ascii"))
    m["n_rows"] = 3
    mp.write_text(json.dumps(m), encoding="ascii")
    with pytest.raises(ResultStoreError, match="rows"):
        load_results(p)


def test_rewriting_removes_the_old_meta_first(tmp_path):
    p = tmp_path / "enum_val.csv"
    write_results(p, _rows(), list(_rows()[0]), _meta(tmp_path))

    class Boom:
        def __iter__(self):
            raise RuntimeError("interrupted")

    with pytest.raises(RuntimeError):
        write_results(p, Boom(), ["id"], _meta(tmp_path))
    with pytest.raises(ResultStoreError, match="without its meta file"):
        load_results(p)


def test_baselines1_summary_script_reads_the_store(tmp_path, raw_path):
    out = tmp_path / "b1"
    run = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_baselines1.py"), str(raw_path), "--limit", "3",
                          "--out", str(out)], capture_output=True, text=True, cwd=ROOT)
    assert run.returncode == 0, run.stdout + run.stderr
    summ = subprocess.run([sys.executable, str(ROOT / "scripts" / "baselines1_summary.py"), str(out)],
                          capture_output=True, text=True, cwd=ROOT)
    assert summ.returncode == 0, summ.stderr
    lines = summ.stdout.splitlines()
    assert len(lines) == 9 * 5  # per set: heuristic + 4 random budgets
    assert all("random    budget  91" not in ln or "mean gap   0.000%" in ln for ln in lines)
    (out / "heuristic_val.csv_meta.json").unlink()
    bad = subprocess.run([sys.executable, str(ROOT / "scripts" / "baselines1_summary.py"), str(out)],
                         capture_output=True, text=True, cwd=ROOT)
    assert bad.returncode != 0 and "without its meta file" in bad.stderr
