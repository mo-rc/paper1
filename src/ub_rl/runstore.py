"""P7 run infrastructure (spec section 12): result store and single-thread timing harness.

Every result file is a CSV with a sidecar `*_meta.json` (the CSV name plus `_meta.json`). The meta carries
`status: "complete"`, the commit, the SHA-256 of the environment file (`src/ub_rl/checker.py` until the
environments exist, P10), the catalogue and split SHA-256, the hardware and the single-thread limits.
A result file whose meta file is missing or whose status is not "complete" is rejected when loaded.

`limit_threads()` sets the BLAS/OpenMP thread env vars to 1 before numpy is imported; `hardware_info()`
records what the machine is. Generated results are never committed (`results/` is ignored)."""
import csv
import hashlib
import json
import os
import platform
import sys
from pathlib import Path


class ResultStoreError(Exception):
    pass


REQUIRED_META = ("status", "method", "commit", "environment_file", "environment_sha256", "catalogue_sha256",
                 "split_file", "split_sha256", "n_contexts")

# Added by write_results and checked by load_results: the CSV cannot be edited or swapped without being noticed.
INTEGRITY_META = ("result_sha256", "n_rows")

THREAD_ENV_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                   "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS")


def limit_threads(n=1):
    """Pin the linear-algebra thread count to n. Call before importing numpy (spec section 10: search and
    inference run on a single CPU thread)."""
    for name in THREAD_ENV_VARS:
        os.environ.setdefault(name, str(n))
    return {name: os.environ.get(name) for name in THREAD_ENV_VARS}


def hardware_info():
    """One dict describing the machine, for the `*_meta.json` files. Read-only, no imports of numpy."""
    cpu_model = platform.processor() or ""
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
    memory_gb = ""
    try:
        page, pages = os.sysconf("SC_PAGE_SIZE"), os.sysconf("SC_PHYS_PAGES")
        memory_gb = round(page * pages / 1e9, 1)
    except (ValueError, OSError):
        pass
    return {
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor() or "",
        "cpu_model": cpu_model,
        "cpu_count": os.cpu_count(),
        "memory_gb": memory_gb,
        "python": platform.python_version(),
    }


def meta_name(path):
    return str(path) + "_meta.json"


def _check_meta(path, meta):
    for key in REQUIRED_META:
        if key not in meta:
            raise ResultStoreError(f"meta for {Path(path).name} is missing required key {key!r}")
    if meta.get("status") != "complete":
        raise ResultStoreError(f"refusing to write {Path(path).name}: status is {meta['status']!r}, not 'complete'")


def write_meta(path, meta):
    """Write a meta sidecar alone (used for non-CSV result files such as run summaries)."""
    _check_meta(path, meta)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(meta_name(path), "w", encoding="ascii", newline="\n") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_results(path, rows, columns, meta):
    """Write a result CSV and its meta sidecar together. The meta must already carry `status: "complete"` and
    every REQUIRED_META key; `result_sha256` and `n_rows` of the written CSV are added here. An old meta file is
    removed first, so an interrupted write never leaves a new CSV next to a stale meta file."""
    path = Path(path)
    _check_meta(path, meta)
    path.parent.mkdir(parents=True, exist_ok=True)
    Path(meta_name(path)).unlink(missing_ok=True)
    rows = list(rows)
    with open(path, "w", newline="", encoding="ascii") as f:
        wr = csv.DictWriter(f, fieldnames=columns, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    write_meta(path, dict(meta, result_sha256=_sha256(path), n_rows=len(rows)))


def load_results(path):
    """(rows, meta) of a stored result. A result file without its meta file is rejected; so is a meta whose
    status is not "complete" or that misses a required key (spec section 12)."""
    path = Path(path)
    mp = Path(meta_name(path))
    if not mp.exists():
        raise ResultStoreError(f"{path.name} without its meta file {mp.name} is rejected")
    meta = json.loads(mp.read_text(encoding="ascii"))
    if meta.get("status") != "complete":
        raise ResultStoreError(f"{path.name} is rejected: meta status is {meta.get('status')!r}, not 'complete'")
    for key in REQUIRED_META:
        if key not in meta:
            raise ResultStoreError(f"{path.name} is rejected: meta is missing required key {key!r}")
    for key in INTEGRITY_META:
        if key not in meta:
            raise ResultStoreError(f"{path.name} is rejected: meta is missing {key!r}")
    if _sha256(path) != meta["result_sha256"]:
        raise ResultStoreError(f"{path.name} is rejected: the file differs from the SHA-256 in its meta file")
    with open(path, newline="", encoding="ascii") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != meta["n_rows"]:
        raise ResultStoreError(f"{path.name} is rejected: {len(rows)} rows, meta says {meta['n_rows']}")
    return rows, meta
