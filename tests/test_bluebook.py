"""Gate 2: checker against the Blue Book resistance tables. Skipped if the workbooks are not in data/raw/."""
import os
import pytest
from ub_rl import bluebook as bb
from ub_rl.catalogue import parse_workbook

D = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROPS = os.path.join(D, "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx")
BEND = os.path.join(D, "UB-bending-S355-EC3UKNA-UK-10-20-2026.xlsx")
BEAR = os.path.join(D, "UB-webbearingbuckling-S355-EC3UKNA-UK-10-20-2026.xlsx")
pytestmark = pytest.mark.skipif(not all(os.path.exists(p) for p in (PROPS, BEND, BEAR)), reason="Blue Book workbooks not in data/raw/")


@pytest.fixture(scope="module")
def data():
    return parse_workbook(PROPS)[0], bb.parse_bending(BEND), bb.parse_bearing(BEAR)


def test_tables_cover_the_catalogue(data):
    cat, bend, bear = data
    assert set(bend) == set(bear) == set(cat.names) and len(bend) == 107


def test_class_mc_iy(data):
    r = bb.compare_class_mc(data[0], data[1])
    assert r["n"] == 107 and not r["class_mismatch"] and not r["Iy_mismatch"] and not r["Mc_outside"]


def test_vc(data):
    assert not bb.compare_vc(data[0], data[2])["Vc_outside"]


def test_web_bearing(data):
    r = bb.compare_bearing(data[0], data[2])
    assert not r["strict_outside"] and not r["capped_unconservative"]
    assert r["min_hw"] > 100.0  # the ss = 100 mm study value never reaches the hw limit


def test_mb(data):
    r = bb.compare_mb(data[0], data[1])
    assert r["n"] == 107 * 17 * 7 and not r["outside"]


def test_reference_section_values(data):
    """457x191x74 as tabulated: Mc,y,Rd 586 kNm, Vc,Rd 895 kN, FRd(ss=100, c=0) 408 kN, class 1."""
    cat, bend, bear = data
    n = "457x191x74"
    assert (bend[n]["Mc"], bend[n]["cls"], bear[n]["Vc"]) == (586.0, 1, 895.0)
    assert bear[n]["F0"][bb.SS.index(100.0)] == 408.0


def test_wrong_curve_would_fail(data):
    """The comparison is sensitive: curve c instead of d for h/b > 3.1 puts Mb,Rd above the table."""
    import numpy as np
    from ub_rl import checker as ck
    cat, bend, _ = data
    K = ck.Checker(cat)
    K.alpha_LT = np.where(cat.cols["h"] / cat.cols["b"] <= 2.0, 0.34, 0.49)
    i = cat.names.index("1016x305x222")
    m = K.with_config(restraint_ratio=1.0, ltb_C1=1.5, ltb_kc=1 / 1.5 ** 0.5)._ltb([i], 10.0, 1e12)[2][0]
    assert m > 1.1 * bend["1016x305x222"]["Mb"][1.5][bb.LENGTHS.index(10.0)]
