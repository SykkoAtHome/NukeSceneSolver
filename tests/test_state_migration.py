"""Saved-state migration tests for pre-directed VP handles."""

from __future__ import annotations

import copy

from scene_solver.core.geometry import line_intersection_least_squares
from scene_solver.core.models import Point2D, Segment2D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp
from scene_solver.ui.state_migration import migrate_legacy_canvas_directions


def _axis_oriented_by_segments(
    axis: str,
    segments: tuple[Segment2D, ...],
    vanishing_point: Point2D,
) -> str:
    """Resolve the signed world axis from consistent directed VP lines."""
    orientation: bool | None = None
    for segment in segments:
        direction = segment.direction().normalized()
        to_vanishing_point = (vanishing_point - segment.start).normalized()
        score = direction.dot(to_vanishing_point)
        points_toward_vp = score > 0.0
        if orientation is not None and points_toward_vp != orientation:
            raise ValueError("Inconsistent directions")
        orientation = points_toward_vp
    return f"{'+' if orientation else '-'}{axis}"



def _point(x: float, y: float) -> dict[str, float]:
    return {"x": x, "y": y}


def _line(
    state: dict[str, dict[str, float]],
    name: str,
) -> Segment2D:
    start, end = state[f"{name}_start"], state[f"{name}_end"]
    return Segment2D(Point2D(start["x"], start["y"]), Point2D(end["x"], end["y"]))


def _segments(
    state: dict[str, dict[str, float]],
    group: str,
) -> tuple[Segment2D, Segment2D]:
    return _line(state, f"{group}_a"), _line(state, f"{group}_b")


def _legacy_state() -> dict[str, dict[str, float]]:
    return {
        "vp1_a_start": _point(0.10, 0.40),
        "vp1_a_end": _point(0.50, 0.45),
        "vp1_b_start": _point(0.10, 0.60),
        "vp1_b_end": _point(0.50, 0.55),
        "vp2_a_start": _point(0.50, 0.45),
        "vp2_a_end": _point(0.90, 0.40),
        "vp2_b_start": _point(0.50, 0.55),
        "vp2_b_end": _point(0.90, 0.60),
        "vp3_a_start": _point(0.40, 0.80),
        "vp3_a_end": _point(0.40, 0.20),
        "vp3_b_start": _point(0.60, 0.20),
        "vp3_b_end": _point(0.60, 0.80),
        "origin": _point(0.50, 0.50),
    }


def test_legacy_2vp_migration_preserves_signed_axis_selectors():
    legacy = _legacy_state()
    original = copy.deepcopy(legacy)
    migrated = migrate_legacy_canvas_directions(
        legacy,
        first_axis="-X",
        second_axis="+Z",
        mode="2vp",
    )

    vp1 = _segments(migrated, "vp1")
    vp2 = _segments(migrated, "vp2")
    assert _axis_oriented_by_segments("X", vp1, line_intersection_least_squares(vp1)) == "-X"
    assert _axis_oriented_by_segments("Z", vp2, line_intersection_least_squares(vp2)) == "+Z"
    assert legacy == original


def test_legacy_1vp_migration_does_not_reverse_the_undirected_horizon():
    legacy = _legacy_state()
    migrated = migrate_legacy_canvas_directions(legacy, first_axis="+X", mode="1vp")

    assert _segments(migrated, "vp2") == _segments(legacy, "vp2")


def test_legacy_3vp_migration_orients_arbitrary_third_axis_endpoints():
    migrated = migrate_legacy_canvas_directions(
        _legacy_state(),
        first_axis="+X",
        second_axis="+Z",
        third_axis="+Y",
        mode="3vp",
    )
    result = solve_2vp(
        SolveInput(
            image_width=1920,
            image_height=1080,
            vp1_segments=_segments(migrated, "vp1"),
            vp2_segments=_segments(migrated, "vp2"),
            vp3_segments=_segments(migrated, "vp3"),
            first_axis="X",
            second_axis="Z",
            third_axis="Y",
            mode="3vp",
        )
    )

    assert result.ok
