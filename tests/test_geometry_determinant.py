"""Stability-floor tests for the least-squares line intersection.

Guards the regression where the near-parallel rejection threshold depended on
how many lines were fitted: because the raw normal-matrix determinant grows
~N^2, a fixed floor silently grew more lenient as lines were added. The floor
now tests the mean pairwise sin^2, so the angular cutoff is line-count
independent.
"""

from __future__ import annotations

import math

import pytest

from scene_solver.core.geometry import line_intersection_least_squares
from scene_solver.core.models import GeometryError, Point2D, Segment2D


def _segment_at_angle(degrees: float, origin_x: float = 0.0) -> Segment2D:
    """A unit segment through (origin_x, 0) at ``degrees`` from horizontal."""
    angle = math.radians(degrees)
    return Segment2D(
        Point2D(origin_x, 0.0),
        Point2D(origin_x + math.cos(angle), math.sin(angle)),
    )


def _accepts(segments: list[Segment2D]) -> bool:
    try:
        line_intersection_least_squares(segments)
        return True
    except GeometryError:
        return False


@pytest.mark.parametrize("line_count", [2, 3, 4, 6])
def test_near_parallel_spread_rejected_regardless_of_line_count(line_count: int) -> None:
    # All lines fall inside a ~0.04 degree fan: too unstable to intersect.
    segments = [
        _segment_at_angle(0.04 * i / (line_count - 1), origin_x=float(i))
        for i in range(line_count)
    ]
    assert not _accepts(segments)


@pytest.mark.parametrize("line_count", [2, 3, 4, 6])
def test_healthy_spread_accepted_regardless_of_line_count(line_count: int) -> None:
    # A wide, well-conditioned fan must always intersect.
    segments = [
        _segment_at_angle(90.0 * i / (line_count - 1), origin_x=float(i))
        for i in range(line_count)
    ]
    assert _accepts(segments)


def test_two_line_floor_matches_documented_angle() -> None:
    # For exactly two lines the normalized determinant equals sin^2(theta), so
    # the 1e-6 floor sits at ~0.057 degrees. Straddle it to pin the boundary.
    floor_degrees = math.degrees(math.asin(math.sqrt(1e-6)))
    assert _accepts([_segment_at_angle(0.0), _segment_at_angle(floor_degrees * 1.5, 1.0)])
    assert not _accepts([_segment_at_angle(0.0), _segment_at_angle(floor_degrees * 0.5, 1.0)])
