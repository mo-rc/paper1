import math

import pytest

from ub_rl.welded_sections import (
    Design, classify_section, geometry_valid, grid_count, make_grid,
    section_properties, yield_strength,
)


def test_grid_count_and_strict_ratio_boundary():
    assert grid_count() == 710_325
    assert geometry_valid(Design(610, 200, 10, 10))
    assert not geometry_valid(Design(620, 200, 10, 10))
    assert not geometry_valid(Design(630, 200, 10, 10))
    assert not geometry_valid(Design(300, 310, 10, 10))


def test_grid_order_is_area_then_geometry_tuple():
    grid = make_grid()
    assert len(grid) == 710_325
    keys = [(2*d.b*d.tf + (d.h-2*d.tf)*d.tw, d.h, d.b, d.tw, d.tf) for d in grid]
    assert keys == sorted(keys)


@pytest.mark.parametrize("design, expected", [
    # 600x200x10x10: hw=580; A=4,000+5,800=9,800 mm2.
    # Iy=2*(200*10^3/12 + 2,000*295^2)+10*580^3/12=510,726,666.667 mm4.
    # Iz=2*10*200^3/12 + 580*10^3/12=13,381,666.667 mm4.
    # Wel,y=Iy/300; Wpl,y=200*10*590 + 10*580^2/4=2,021,000 mm3.
    (Design(600, 200, 10, 10), (9800, 510_726_666.6666667, 13_381_666.6666667,
                                 1_702_422.2222222, 2_021_000.0)),
    # 800x300x12x20: hw=760; A=12,000+9,120=21,120 mm2.
    # Iy=2*(300*20^3/12 + 6,000*390^2)+12*760^3/12=2,264,576,000 mm4.
    # Iz=2*20*300^3/12 + 760*12^3/12=90,109,440 mm4.
    # Wel,y=Iy/400; Wpl,y=300*20*780 + 12*760^2/4=6,412,800 mm3.
    (Design(800, 300, 12, 20), (21120, 2_264_576_000.0, 90_109_440.0,
                                 5_661_440.0, 6_412_800.0)),
])
def test_section_property_hand_arithmetic(design, expected):
    p = section_properties(design)
    assert p.area == expected[0]
    assert p.iy == pytest.approx(expected[1], rel=1e-12)
    assert p.iz == pytest.approx(expected[2], rel=1e-12)
    assert p.wel_y == pytest.approx(expected[3], rel=1e-12)
    assert p.wpl_y == pytest.approx(expected[4], rel=1e-12)


@pytest.mark.parametrize("thickness,fy", [(16,355), (16.0001,345), (40,345),
                                          (40.0001,335), (63,335), (63.0001,325)])
def test_yield_strength_at_thickness_boundaries(thickness, fy):
    assert yield_strength(thickness) == fy


@pytest.mark.parametrize("limit", [9.0, 10.0, 14.0])
def test_flange_class_limits_and_immediately_above(limit):
    eps = math.sqrt(235.0 / 355.0)
    exact = classify_section(limit * eps, 0.0, eps)[0]
    above = classify_section(math.nextafter(limit * eps, math.inf), 0.0, eps)[0]
    assert above == exact + 1


@pytest.mark.parametrize("limit", [72.0, 83.0, 124.0])
def test_web_class_limits_and_immediately_above(limit):
    eps = math.sqrt(235.0 / 355.0)
    exact = classify_section(0.0, limit * eps, eps)[1]
    above = classify_section(0.0, math.nextafter(limit * eps, math.inf), eps)[1]
    assert above == exact + 1


def test_class4_section_is_rejected():
    p = section_properties(Design(900, 450, 6, 8))
    assert p.section_class == 4
