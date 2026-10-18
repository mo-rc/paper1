import os
import pytest
from ub_rl.catalogue import parse_workbook

XLSX = os.path.join(os.path.dirname(__file__), "..", "data", "raw", "UB-secpropsdimsprops-EC3UKNA-UK-10-16-2026.xlsx")


@pytest.fixture(scope="session")
def raw_path():
    if not os.path.exists(XLSX):
        pytest.skip("raw workbook not present in data/raw/")
    return XLSX


@pytest.fixture(scope="session")
def parsed(raw_path):
    return parse_workbook(raw_path)


@pytest.fixture(scope="session")
def full(parsed):
    return parsed[0]


@pytest.fixture(scope="session")
def C(full):
    return full.mass_ordered(False)


@pytest.fixture(scope="session")
def Cplus(full):
    return full.mass_ordered(True)
