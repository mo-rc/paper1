"""P11 step 4: the prioritized replay (sum tree) and the n-step return builder
(src/ub_rl/replay.py) for the F1-R1 Dueling Double DQN. Pure data-structure tests: no checker
calls, no training, no results."""
import numpy as np
import pytest

from ub_rl.replay import NStepBuilder, PER_EPS, PrioritizedReplay, SumTree


def _tr(k, r, done=False):
    """A transition with marker obs: s = k, s' = k + 0.5 (so bootstrap states are identifiable)."""
    return (np.full(22, float(k), dtype=np.float32), 0, float(r),
            np.full(22, float(k) + 0.5, dtype=np.float32), done)


# ------------------------------------------------------------------ the n-step builder
def test_nstep_gamma1_full_windows_and_terminal_flush():
    """n=3, gamma=1, rewards 1..6 with a terminal at 6: three full windows (G = 6, 9, 12 with
    bootstrap states 3.5/4.5/5.5) and the terminal flush (G = 15, 11, 6, all terminal, bootstrap
    dropped and s_n = the terminal state)."""
    b = NStepBuilder(n=3, gamma=1.0)
    out = []
    for k in range(1, 7):
        out += list(b.push(_tr(k, k, done=(k == 6))))
    assert [(float(o[2]), bool(o[4])) for o in out] == [(6.0, False), (9.0, False), (12.0, False),
                                                        (15.0, True), (11.0, True), (6.0, True)]
    assert out[0][3][0] == 3.5  # the first full window bootstraps at s_3
    assert all(np.allclose(o[3], np.full(22, 6.5, dtype=np.float32)) for o in out[3:])
    assert b.window == []  # the terminal consumed every window


def test_nstep_gamma09():
    """G = r0 + gamma r1 + gamma^2 r2 with gamma = 0.9: 1 + 0.9*2 + 0.81*3 = 5.23."""
    b = NStepBuilder(n=3, gamma=0.9)
    out = list(b.push(_tr(1, 1.0))) + list(b.push(_tr(2, 2.0))) + list(b.push(_tr(3, 3.0)))
    assert len(out) == 1
    assert out[0][2] == pytest.approx(1.0 + 0.9 * 2.0 + 0.81 * 3.0, abs=1e-12)
    assert not out[0][4] and out[0][3][0] == 3.5


def test_nstep_terminal_flush_of_a_window_shorter_than_n():
    """A window shorter than n: two transitions, the second terminal - both flush with no
    bootstrap, G = r0 + gamma r1 for the first and r1 for the second."""
    b = NStepBuilder(n=5, gamma=1.0)
    out = list(b.push(_tr(1, 1.0))) + list(b.push(_tr(2, 2.0, done=True)))
    assert [(float(o[2]), bool(o[4])) for o in out] == [(3.0, True), (2.0, True)]
    assert all(np.allclose(o[3], np.full(22, 2.5, dtype=np.float32)) for o in out)


def test_nstep_discard_drops_pending_windows():
    b = NStepBuilder(n=5, gamma=1.0)
    list(b.push(_tr(1, 1.0)))  # pending, no done
    b.discard()
    out = list(b.push(_tr(2, 2.0, done=True)))
    assert [(float(o[2]),) for o in out] == [(2.0,)]  # the discarded window never yielded


# ------------------------------------------------------------------ the sum tree
def test_sum_tree_total_max_and_overwrite():
    t = SumTree(4)
    for p in (1.0, 2.0, 3.0, 4.0):
        t.add(p)
    assert t.total() == pytest.approx(10.0) and t.max() == pytest.approx(4.0)
    t.add(7.0)  # overwrites slot 0 (the 1.0)
    assert t.total() == pytest.approx(2.0 + 3.0 + 4.0 + 7.0)
    assert t.max() == pytest.approx(7.0)
    t.update(2, 0.5)  # slot 2 (the 3.0)
    assert t.total() == pytest.approx(2.0 + 0.5 + 4.0 + 7.0)


def test_sum_tree_get_returns_slots_by_prefix():
    t = SumTree(4)
    for p in (1.0, 2.0, 3.0, 4.0):
        t.add(p)
    assert t.get(0.0) == 0
    assert t.get(0.9999) == 0
    assert t.get(1.0) == 1
    assert t.get(5.9999) == 2
    assert t.get(6.0) == 3
    assert t.get(9.9999) == 3


# ------------------------------------------------------------------ prioritized replay
def _rng(seed=0):
    return np.random.default_rng(seed)


def test_per_sampling_frequencies_are_proportional():
    """Sampling frequencies proportional to the stored priorities (fixed seed, stated tolerance):
    with priorities 1, 2, 3, 4 the expected shares are 0.1, 0.2, 0.3, 0.4 over 4,000 draws."""
    r = PrioritizedReplay(16, alpha=0.6, rng=_rng(0))
    for p in (1.0, 2.0, 3.0, 4.0):
        r.add((np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True), p)
    counts = np.zeros(4)
    for _ in range(4000):
        slots, _, _ = r.sample(1, beta=0.4)
        counts[slots[0]] += 1
    shares = counts / counts.sum()
    assert np.allclose(shares, [0.1, 0.2, 0.3, 0.4], atol=0.03)


def test_per_new_transitions_get_max_priority():
    r = PrioritizedReplay(8, alpha=0.6, rng=_rng(0))
    t = (np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True)
    for p in (1.0, 2.0, 3.0):
        r.add(t, p)
    r.add(t, r.max_priority())  # the agent's convention: new transitions take the current max
    assert r.tree.max() == pytest.approx(3.0)
    assert r.tree.values[r.tree.leaf_index(3)] == pytest.approx(3.0)


def test_per_max_priority_empty_buffer_is_one():
    r = PrioritizedReplay(8, alpha=0.6, rng=_rng(0))
    assert r.max_priority() == 1.0  # the empty buffer
    r.add((np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True), 3.0)
    assert r.max_priority() == 3.0  # else the tree max


def test_per_sample_redraws_past_empty_slots_and_stays_finite(monkeypatch):
    """A draw landing past the stored transitions or on a priority-0 leaf (a floating-point
    boundary crossing next to an empty slot) is redrawn within the same segment: no NaN/inf
    weights; the retries are bounded and then the sampling raises."""
    r = PrioritizedReplay(8, alpha=0.6, rng=_rng(0))
    t = (np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True)
    r.add(t, 1.0)
    r.add(t, 1.0)  # slots 0 and 1 stored; slots 2..7 empty (priority 0)
    calls = {"n": 0}
    real_get = r.tree.get

    def fake_get(prefix):
        calls["n"] += 1
        return 3 if calls["n"] == 1 else real_get(prefix)  # the first draw hits an empty slot

    monkeypatch.setattr(r.tree, "get", fake_get)
    slots, _, w = r.sample(2, beta=1.0)
    assert calls["n"] > 1  # it redrew
    assert np.all(slots < 2)
    assert np.all(np.isfinite(w)) and np.all(w > 0.0) and np.all(w <= 1.0)
    monkeypatch.setattr(r.tree, "get", lambda prefix: 3)  # always invalid: bounded retries raise
    with pytest.raises(RuntimeError, match="segment"):
        r.sample(2, beta=1.0)


def test_per_sample_prefix_on_a_segment_boundary_stays_finite():
    """The prefix landing exactly on a segment boundary next to an empty slot (a stubbed uniform
    returning the segment width) still yields a stored slot and finite weights."""
    class StubRng:
        def uniform(self, a, b):
            return b  # the prefix lands exactly on the segment end

    r = PrioritizedReplay(4, alpha=0.6, rng=StubRng())
    t = (np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True)
    r.add(t, 1.0)
    r.add(t, 1.0)  # slots 0, 1; slots 2, 3 empty
    slots, _, w = r.sample(2, beta=1.0)
    assert set(slots.tolist()) <= {0, 1}
    assert np.all(np.isfinite(w)) and np.all(w > 0.0)


def test_per_priorities_change_after_an_update():
    r = PrioritizedReplay(8, alpha=1.0, rng=_rng(0))
    t = (np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True)
    for p in (1.0, 2.0, 3.0):
        r.add(t, p)
    r.update_priorities([0, 1], [4.0, 1.0])
    assert r.tree.values[r.tree.leaf_index(0)] == pytest.approx(4.0 + PER_EPS)
    assert r.tree.values[r.tree.leaf_index(1)] == pytest.approx(1.0 + PER_EPS)
    assert r.tree.values[r.tree.leaf_index(2)] == pytest.approx(3.0)  # untouched


def test_per_is_weights_in_unit_interval_and_min_for_max_priority():
    r = PrioritizedReplay(8, alpha=0.6, rng=_rng(0))
    t = (np.zeros(22, np.float32), 0, 0.0, np.zeros(22, np.float32), True)
    for p in (1.0, 2.0, 3.0, 4.0):
        r.add(t, p)
    slots, _, w = r.sample(4, beta=1.0)
    assert np.all(w > 0.0) and np.all(w <= 1.0)
    assert slots[int(np.argmin(w))] == 3  # the max-priority transition gets the smallest weight


def test_per_ring_buffer_overwrites_oldest_and_roundtrips_state():
    r = PrioritizedReplay(4, alpha=0.6, rng=_rng(0))
    for k in range(6):  # 6 adds into a capacity-4 ring
        r.add((np.full(22, float(k), np.float32), k, float(k), np.zeros(22, np.float32), True), 1.0)
    assert r.n == 4 and r.pos == 2
    assert set(r.act.tolist()) == {2, 3, 4, 5}  # the two oldest were overwritten
    r2 = PrioritizedReplay(4, alpha=0.6, rng=_rng(0))
    r2.load_state(r.state())
    assert r2.n == r.n and r2.pos == r.pos
    assert np.array_equal(r2.tree.values, r.tree.values)
    assert np.array_equal(r2.obs, r.obs) and np.array_equal(r2.act, r.act)
    assert r2.tree.total() == pytest.approx(r.tree.total())
