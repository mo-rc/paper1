"""P11 step 4: the prioritized replay buffer with a sum tree and the n-step return builder for the
F1-R1 Dueling Double DQN (docs/p11_plan.md section 1). Pure data structures: no torch, no checker,
no training here.

PrioritizedReplay: proportional priorities (|TD error| + PER_EPS) ** alpha over a binary sum tree
(O(log N) sampling and updates - the 200,000-call runs need it); new transitions take the current
max priority (the agent passes it); importance-sampling weights (N * p_i) ** -beta are normalised
to <= 1, so the max-priority transition gets the smallest weight; priorities are updated from the
new TD errors after each gradient step. All randomness comes from the seeded numpy Generator
passed in - never the global RNG.

NStepBuilder: n-step returns from the transition stream; a terminal transition flushes every
remaining partial window with no bootstrap, so a window shorter than n yields a proper n-step
target of its own length.
"""
import numpy as np

PER_EPS = 1e-6  # fixed provisional constant (not tuned): proportional priorities (|td| + eps)^alpha
OBS_DIM = 22    # the F1 observation (P11 plan section 1: 9 context + 5 section + 7 utilisation + steps/13)


class SumTree:
    """A binary sum tree over a fixed capacity N (rounded up to a power of two). Leaves hold the
    stored priorities; internal nodes hold sums. O(log N) add/update/sample. Leaf slot i is fixed
    to storage slot i, so overwriting a slot updates the same leaf."""

    def __init__(self, capacity):
        self.capacity = int(capacity)
        self.size = 1 << (self.capacity - 1).bit_length()  # the next power of two
        self.values = np.zeros(2 * self.size - 1, dtype=np.float64)
        self.pos = 0  # the next slot to write (cycles over the capacity)

    def leaf_index(self, slot):
        return self.size - 1 + int(slot)

    def add(self, priority):
        slot = self.pos % self.capacity
        self.pos += 1
        self.update(slot, priority)
        return slot

    def update(self, slot, priority):
        idx = self.leaf_index(slot)
        delta = float(priority) - self.values[idx]
        self.values[idx] = float(priority)
        while idx > 0:
            idx = (idx - 1) // 2
            self.values[idx] += delta

    def total(self):
        return float(self.values[0])

    def max(self):
        return float(self.values[self.size - 1: self.size - 1 + self.capacity].max())

    def get(self, prefix):
        """The slot whose cumulative sum range contains prefix (0 <= prefix < total)."""
        idx = 0
        while idx < self.size - 1:
            left = 2 * idx + 1
            if prefix < self.values[left]:
                idx = left
            else:
                prefix -= self.values[left]
                idx = left + 1
        return int(idx - (self.size - 1))


class PrioritizedReplay:
    """Proportional PER over a SumTree with preallocated numpy ring storage."""

    def __init__(self, capacity, alpha, rng):
        self.capacity = int(capacity)
        self.alpha = float(alpha)
        self.rng = rng  # a seeded numpy Generator, never the global RNG
        self.tree = SumTree(self.capacity)
        self.obs = np.zeros((self.capacity, OBS_DIM), dtype=np.float32)
        self.act = np.zeros(self.capacity, dtype=np.int64)
        self.ret = np.zeros(self.capacity, dtype=np.float32)
        self.next_obs = np.zeros((self.capacity, OBS_DIM), dtype=np.float32)
        self.term = np.zeros(self.capacity, dtype=bool)
        self.n = 0    # stored transitions
        self.pos = 0  # next storage slot (ring)

    def __len__(self):
        return self.n

    def add(self, transition, priority):
        """Store one (s, a, r, s_next, done) transition with the given tree priority; new
        transitions take the current max priority (the agent passes max_priority())."""
        s, a, r, s_next, term = transition
        slot = self.pos
        self.pos = (self.pos + 1) % self.capacity
        self.obs[slot] = np.asarray(s, dtype=np.float32)
        self.act[slot] = int(a)
        self.ret[slot] = float(r)
        self.next_obs[slot] = np.asarray(s_next, dtype=np.float32)
        self.term[slot] = bool(term)
        self.n = min(self.n + 1, self.capacity)
        self.tree.update(slot, float(priority))

    def max_priority(self):
        """1.0 when the buffer is empty (the first transition starts there), else the tree max."""
        return 1.0 if self.n == 0 else self.tree.max()

    REDRAW_ATTEMPTS = 16  # bounded retries within the segment before raising

    def sample(self, batch_size, beta):
        """One uniform-segment draw per slot: (slots, transition batch, is_weights) with the
        importance weights (N * p_i) ** -beta normalised to <= 1. All randomness from self.rng. A
        draw that lands past the stored transitions or on a priority-0 leaf (a floating-point
        boundary crossing next to an empty slot) is redrawn within the same segment, bounded by
        REDRAW_ATTEMPTS, then the sampling raises rather than return NaN/inf weights."""
        total = self.tree.total()
        if self.n < batch_size or total <= 0:
            raise ValueError("the replay does not hold enough transitions to sample")
        slots = np.empty(batch_size, dtype=np.int64)
        seg = total / batch_size
        for k in range(batch_size):
            slot = -1
            for _ in range(self.REDRAW_ATTEMPTS):
                prefix = seg * k + self.rng.uniform(0.0, seg)
                s = self.tree.get(min(prefix, total - 1e-15))
                if s < self.n and self.tree.values[self.tree.leaf_index(s)] > 0:
                    slot = s
                    break
            if slot < 0:
                raise RuntimeError("replay sampling could not find a stored transition "
                                   "in its segment")
            slots[k] = slot
        probs = np.asarray([self.tree.values[self.tree.leaf_index(s)] / total for s in slots])
        weights = (self.n * probs) ** (-float(beta))
        weights /= weights.max()  # in (0, 1]; the max-priority transition gets the smallest weight
        return (slots, (self.obs[slots], self.act[slots], self.ret[slots],
                        self.next_obs[slots], self.term[slots]), weights.astype(np.float32))

    def update_priorities(self, slots, td_abs):
        """(|TD error| + PER_EPS) ** alpha for each slot, after each gradient step."""
        for s, td in zip(slots, np.abs(np.asarray(td_abs, dtype=np.float64))):
            self.tree.update(int(s), float((td + PER_EPS) ** self.alpha))

    def state(self):
        """The full replay content (the 200,000-call checkpoints save and restore it)."""
        return {"tree": self.tree.values.copy(), "obs": self.obs.copy(), "act": self.act.copy(),
                "ret": self.ret.copy(), "next_obs": self.next_obs.copy(), "term": self.term.copy(),
                "n": self.n, "pos": self.pos}

    def load_state(self, state):
        self.tree.values[:] = state["tree"]
        self.obs[:] = state["obs"]
        self.act[:] = state["act"]
        self.ret[:] = state["ret"]
        self.next_obs[:] = state["next_obs"]
        self.term[:] = state["term"]
        self.n = int(state["n"])
        self.pos = int(state["pos"])


class NStepBuilder:
    """Builds n-step training transitions (s_0, a_0, G, s_n, terminal) from the transition stream:
    G = sum_{i < n} gamma^i r_i, bootstrapped with gamma^n Q(s_n) by the learner unless the window
    ended in a terminal (done), where the bootstrap is dropped. A terminal transition flushes every
    remaining partial window with no bootstrap; a truncated episode (budget stop, no done) leaves
    its windows pending and the agent discards them when the next episode starts."""

    def __init__(self, n, gamma):
        self.n = int(n)
        self.gamma = float(gamma)
        self.window = []  # [(s, a, r, s_next, done)]
        self.cum = []     # cum[i] = discounted return from window[i] to the newest entry

    def push(self, t):
        """Add one transition; yield the completed n-step training transitions (a generator)."""
        s, a, r, s_next, done = t
        k = len(self.window)
        self.cum = [c + (self.gamma ** (k - i)) * r for i, c in enumerate(self.cum)] + [float(r)]
        self.window.append((np.asarray(s, dtype=np.float32), int(a), float(r),
                            np.asarray(s_next, dtype=np.float32), bool(done)))
        if len(self.window) >= self.n:
            out = self.window.pop(0)
            c = self.cum.pop(0)
            yield (out[0], out[1], c, self.window[-1][3], self.window[-1][4])
        if done:  # the terminal flush: every remaining partial window, no bootstrap
            while self.window:
                out = self.window.pop(0)
                c = self.cum.pop(0)
                yield (out[0], out[1], c, np.asarray(s_next, dtype=np.float32), True)

    def discard(self):
        """Drop pending partial windows (a truncated episode is never learned from)."""
        self.window = []
        self.cum = []

    def state(self):
        return {"window": [(s.copy(), a, r, s_next.copy(), d)
                           for s, a, r, s_next, d in self.window],
                "cum": list(self.cum)}

    def load_state(self, state):
        self.window = [(s.copy(), a, r, s_next.copy(), d)
                       for s, a, r, s_next, d in state["window"]]
        self.cum = list(state["cum"])
