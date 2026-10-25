"""Stage 1 context box and splits (spec Amendment A2, 2026-10-23).

Generates the training pool, validation set and test sets of seven-parameter contexts. A context is
(span, width, dead, live, restraint_ratio, deflection_rule, depth_cap), see `ub_rl.context.Context`.
Nothing here calls the checker: the files depend only on the constants below and the seeds.
Randomness: `random.Random(seed)` (Mersenne Twister, stream fixed across Python versions); every value is drawn with
`random()` in a fixed order, so the files are identical on any machine. Values are rounded by formatting
(span, width 2 decimals; dead, live 3; factored UDL 4), and all tests of ranges use the rounded values."""
import csv
import functools
import hashlib
import itertools
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ub_rl.context import Context

# ------------------------------------------------------------------ the box (A2, table 1)
SPAN = (9.0, 15.0)  # m
WIDTH = (4.0, 8.0)  # m, tributary width
DEAD = (2.5, 5.0)  # kN/m2
LIVE = (2.0, 5.0)  # kN/m2
W_BOX = (56.0, 100.0)  # kN/m, factored superimposed UDL (v1.2 box); contexts outside it are rejected
# Extended load box, used only by E2 and E3 (the factored UDL must exceed the training maximum)
WIDTH_EXT = (4.0, 10.0)
DEAD_EXT = (2.5, 6.5)
LIVE_EXT = (2.0, 6.5)
W_EXT = (100.0, 130.0)  # kN/m, lower bound open
SPAN_EXT = (15.0, 18.0)  # m, lower bound open
HOLE = {"span": (11.5, 12.5), "w": (75.0, 85.0)}  # closed block, as in spec section 8
RESTRAINT_TRAIN = (0.0, 0.25, 0.5, 1.0)
RESTRAINT_HELD_OUT = 1.0 / 3.0  # T4-B
RULES = ("var360", "var200", "tot250")
CAPS = (None, 700, 800, 900)  # mm; 500 and 600 of the proposal are infeasible for 73 to 100 % of the box (A2 audit)
N_HELD_OUT_CELLS = 8
CELL_SEED = 506
GAMMA_G, GAMMA_Q = 1.35, 1.5

REFERENCE = dict(span=9.0, width=6.0, dead=3.675, live=3.0)

# T5 lattice (supervisor's "lower, real, upper" idea as a deterministic test): end points and middle of each range
LATTICE = {"span": (9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0), "width": (4.0, 6.0, 8.0),
           "dead": (2.5, 3.675, 5.0), "live": (2.0, 3.0, 5.0)}  # lower, real (reference), upper


COLUMNS = ["id", "set", "span", "width", "dead", "live", "restraint_ratio", "deflection_rule", "depth_cap",
           "w_factored", "slice_full_restraint"]


def _cap_str(cap):
    return "none" if cap is None else str(int(cap))


def cap_from_str(s):
    return None if s == "none" else float(s)


def _fmt(x, nd):
    return float(f"{x:.{nd}f}")


def factored_w(width, dead, live):
    return _fmt((GAMMA_G * dead + GAMMA_Q * live) * width, 4)


def all_cells():
    """The 48 (restraint, rule, cap) cells of the training restraint values."""
    return sorted(itertools.product(RESTRAINT_TRAIN, RULES, CAPS), key=lambda c: (c[0], c[1], -1 if c[2] is None else c[2]))


@functools.lru_cache(maxsize=None)
def held_out_cells():
    """The cells held out for T4-A (unseen combinations): 8 of 48. Seeded draw (seed 506, one `random()` per cell, the cells
    with the smallest keys are taken, so the draw does not depend on library internals). Conditions, fixed in A2:
    (a) exactly one held-out cell has restraint 0 (not the primary cell); (b) the primary cell (0, var360, none) stays in
    training; (c) every pair (restraint, rule), (restraint, cap), (rule, cap) still occurs in a training cell, so only the
    triple is unseen. The first draw satisfying all three is used; returns (cells, attempt number)."""
    cells = all_cells()
    primary = (0.0, "var360", None)
    rng = random.Random(CELL_SEED)
    for attempt in range(1, 10001):
        keys = sorted((rng.random(), i) for i in range(len(cells)))
        held = [cells[i] for _, i in keys[:N_HELD_OUT_CELLS]]
        train = [c for c in cells if c not in held]
        if primary in held or sum(c[0] == 0.0 for c in held) != 1:
            continue
        ok = all({(c[i], c[j]) for c in train} == {(c[i], c[j]) for c in cells} for i, j in ((0, 1), (0, 2), (1, 2)))
        if ok:
            return tuple(sorted(held, key=cells.index)), attempt
    raise RuntimeError("no admissible held-out cell set")


@dataclass(frozen=True)
class SetSpec:
    name: str  # set name, also the id prefix
    n: int
    span: tuple = SPAN
    span_lo_open: bool = False
    width: tuple = WIDTH
    dead: tuple = DEAD
    live: tuple = LIVE
    w: tuple = W_BOX
    w_lo_open: bool = False
    restraints: tuple = RESTRAINT_TRAIN
    cells: str = "train"  # 'train' (not held out), 'heldout', or 'any'
    hole: str = "exclude"  # 'exclude' or 'only'
    shift: str = ""  # one-line description of how the set differs from training


def in_hole(span, w):
    return HOLE["span"][0] <= span <= HOLE["span"][1] and HOLE["w"][0] <= w <= HOLE["w"][1]


def lattice_rows(forbidden):
    """T5: every lattice point in the box and outside H, in the trained (restraint, rule, cap) cells. No randomness. The
    reference contexts lie on the lattice; they are in reference.csv and excluded here so that contexts stay unique."""
    held, _ = held_out_cells()
    rows = []
    for L, B, d, l in itertools.product(LATTICE["span"], LATTICE["width"], LATTICE["dead"], LATTICE["live"]):
        w = factored_w(B, d, l)
        if not (W_BOX[0] <= w <= W_BOX[1]) or in_hole(L, w):
            continue
        for cell in all_cells():
            if cell in held:
                continue
            c = (L, B, d, l) + cell
            if c in forbidden:
                continue
            forbidden.add(c)
            rows.append(c)
    return rows


def _draw(rng, spec):
    """One candidate; returns (span, width, dead, live, restraint, rule, cap) or None if rejected by the set's rules."""
    u = [rng.random() for _ in range(7)]
    span = _fmt(spec.span[0] + u[0] * (spec.span[1] - spec.span[0]), 2)
    width = _fmt(spec.width[0] + u[1] * (spec.width[1] - spec.width[0]), 2)
    dead = _fmt(spec.dead[0] + u[2] * (spec.dead[1] - spec.dead[0]), 3)
    live = _fmt(spec.live[0] + u[3] * (spec.live[1] - spec.live[0]), 3)
    r = spec.restraints[min(int(u[4] * len(spec.restraints)), len(spec.restraints) - 1)]
    rule = RULES[min(int(u[5] * len(RULES)), len(RULES) - 1)]
    cap = CAPS[min(int(u[6] * len(CAPS)), len(CAPS) - 1)]
    if span < spec.span[0] or span > spec.span[1] or (spec.span_lo_open and span <= spec.span[0]):
        return None
    w = factored_w(width, dead, live)
    if w < spec.w[0] or w > spec.w[1] or (spec.w_lo_open and w <= spec.w[0]):
        return None
    if in_hole(span, w) != (spec.hole == "only"):
        return None
    if spec.cells != "any":
        held, _ = held_out_cells()
        if ((r, rule, cap) in held) != (spec.cells == "heldout"):
            return None
    return span, width, dead, live, r, rule, cap


def sample_set(spec, rng, forbidden):
    rows = []
    while len(rows) < spec.n:
        c = _draw(rng, spec)
        if c is None or c in forbidden:
            continue
        forbidden.add(c)
        rows.append(c)
    return rows


def _row(set_name, k, c):
    span, width, dead, live, r, rule, cap = c
    return {"id": f"{set_name}-{k:05d}", "set": set_name, "span": f"{span:.2f}", "width": f"{width:.2f}",
            "dead": f"{dead:.3f}", "live": f"{live:.3f}", "restraint_ratio": repr(float(r)), "deflection_rule": rule,
            "depth_cap": _cap_str(cap), "w_factored": f"{factored_w(width, dead, live):.4f}",
            "slice_full_restraint": int(r == 0.0 and rule == "var360" and cap is None)}


# file name -> (seed, [SetSpec, ...]). Sets within a file share one random stream, in the order listed.
def file_plan():
    e_load = dict(width=WIDTH_EXT, dead=DEAD_EXT, live=LIVE_EXT, w=W_EXT, w_lo_open=True)
    return {
        "train": (100, [SetSpec("train", 20000, shift="none (training distribution)")]),
        "val": (101, [SetSpec("val", 1000, shift="none")]),
        "test_t1": (202, [SetSpec("t1", 2000, shift="none: interpolation")]),
        "test_t2": (303, [SetSpec("t2", 500, hole="only", shift="held-out block in (span, w)")]),
        "test_t3": (404, [
            SetSpec("t3-E1", 500, span=SPAN_EXT, span_lo_open=True, shift="span in (15, 18] m"),
            SetSpec("t3-E2", 500, shift="factored UDL in (100, 130] kN/m (extended load box)", **e_load),
            SetSpec("t3-E3", 500, span=SPAN_EXT, span_lo_open=True, shift="both E1 and E2", **e_load),
        ]),
        "test_t4": (505, [
            SetSpec("t4-A", 1000, cells="heldout", shift="unseen (restraint, rule, cap) combinations"),
            SetSpec("t4-B", 500, restraints=(RESTRAINT_HELD_OUT,), cells="any",
                    shift="restraint ratio 1/3 (never trained; between trained values, so interpolation in restraint)"),
        ]),
    }


# ------------------------------------------------------------------ v1.2 sub-study (spec section 8, two parameters)
# Full restraint (restraint 0, var360, no cap), width 6 m, dead and live scaled together from the reference case so that
# the factored UDL is w; sizes and seeds of section 8. Sets with the same seed share one stream, in the order listed.
def _v12_w_ref():
    return factored_w(REFERENCE["width"], REFERENCE["dead"], REFERENCE["live"])


V12_PLAN = [  # (set, seed, n, span range, span lo open, w range, w lo open, hole)
    ("s12-val", 101, 500, SPAN, False, W_BOX, False, "exclude"),
    ("s12-t1", 202, 2000, SPAN, False, W_BOX, False, "exclude"),
    ("s12-t2", 303, 500, SPAN, False, W_BOX, False, "only"),
    ("s12-E1", 404, 500, SPAN_EXT, True, W_BOX, False, "exclude"),
    ("s12-E2", 404, 500, SPAN, False, W_EXT, True, "exclude"),
    ("s12-E3", 404, 500, SPAN_EXT, True, W_EXT, True, "exclude"),
]


def _v12_draw(rng, span_rng, span_lo_open, w_rng, w_lo_open, hole):
    u0, u1 = rng.random(), rng.random()
    span = _fmt(span_rng[0] + u0 * (span_rng[1] - span_rng[0]), 2)
    k = (w_rng[0] + u1 * (w_rng[1] - w_rng[0])) / _v12_w_ref()
    dead, live = _fmt(REFERENCE["dead"] * k, 3), _fmt(REFERENCE["live"] * k, 3)
    w = factored_w(REFERENCE["width"], dead, live)
    if span < span_rng[0] or span > span_rng[1] or (span_lo_open and span <= span_rng[0]):
        return None
    if w < w_rng[0] or w > w_rng[1] or (w_lo_open and w <= w_rng[0]):
        return None
    if in_hole(span, w) != (hole == "only"):
        return None
    return span, REFERENCE["width"], dead, live, 0.0, "var360", None


def generate_v12(forbidden):
    rows, streams = [], {}
    for name, seed, n, srng, slo, wrng, wlo, hole in V12_PLAN:
        rng = streams.setdefault(seed, random.Random(seed))
        k = 0
        while k < n:
            c = _v12_draw(rng, srng, slo, wrng, wlo, hole)
            if c is None or c in forbidden:
                continue
            forbidden.add(c)
            rows.append(_row(name, k, c))
            k += 1
    return rows


def generate_all():
    """Returns {file name: list of row dicts}. Order of generation (and of the no-duplicate rule): train, val, t1, t2,
    t3, t4, v12_substudy; a context never appears twice in the union of these files."""
    forbidden = set()
    out = {}
    for fname, (seed, specs) in file_plan().items():
        rng = random.Random(seed)
        rows = []
        for spec in specs:
            for k, c in enumerate(sample_set(spec, rng, forbidden)):
                rows.append(_row(spec.name, k, c))
        out[fname] = rows
    out["v12_substudy"] = generate_v12(forbidden)
    # T5 lattice: no randomness, generated last so the files above are unchanged
    forbidden.update((REFERENCE["span"], REFERENCE["width"], REFERENCE["dead"], REFERENCE["live"], r, "var360", None)
                     for r in RESTRAINT_TRAIN)
    out["test_t5"] = [_row("t5", k, c) for k, c in enumerate(lattice_rows(forbidden))]
    # reference contexts: reference case at each training restraint value (restraint 0 is the spec's reference case)
    out["reference"] = [
        _row("ref", k, (REFERENCE["span"], REFERENCE["width"], REFERENCE["dead"], REFERENCE["live"], r, "var360", None))
        for k, r in enumerate(RESTRAINT_TRAIN)
    ]
    return out


def write_csv(path, rows, columns=COLUMNS):
    with open(path, "w", newline="", encoding="ascii") as f:
        wr = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)


def heldout_rows():
    held, _ = held_out_cells()
    return [{"restraint_ratio": repr(float(r)), "deflection_rule": rule, "depth_cap": _cap_str(cap)} for r, rule, cap in held]


def read_csv(path):
    with open(path, newline="", encoding="ascii") as f:
        return list(csv.DictReader(f))


def row_to_context(row):
    return Context(span=float(row["span"]), width=float(row["width"]), dead=float(row["dead"]), live=float(row["live"]),
                   restraint_ratio=float(row["restraint_ratio"]), deflection_rule=row["deflection_rule"],
                   depth_cap=cap_from_str(row["depth_cap"]))


def load_split(name, root="data/splits"):
    """(rows, contexts) of a split file, name in train, val, test_t1, test_t2, test_t3, test_t4, test_t5, v12_substudy, reference."""
    rows = read_csv(Path(root) / f"{name}.csv")
    return rows, [row_to_context(r) for r in rows]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
