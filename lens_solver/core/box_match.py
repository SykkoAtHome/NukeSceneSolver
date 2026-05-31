"""Projected cuboid helpers shared by the core solver and UI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from lens_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Segment2D


BOX_CORNER_NAMES = (
    "box_v000",
    "box_v100",
    "box_v010",
    "box_v110",
    "box_v001",
    "box_v101",
    "box_v011",
    "box_v111",
)

BOX_AXIS_EDGES = (
    (
        ("box_v000", "box_v100"),
        ("box_v010", "box_v110"),
        ("box_v001", "box_v101"),
        ("box_v011", "box_v111"),
    ),
    (
        ("box_v000", "box_v010"),
        ("box_v100", "box_v110"),
        ("box_v001", "box_v011"),
        ("box_v101", "box_v111"),
    ),
    (
        ("box_v000", "box_v001"),
        ("box_v100", "box_v101"),
        ("box_v010", "box_v011"),
        ("box_v110", "box_v111"),
    ),
)

BOX_EDGES = tuple(edge for axis_edges in BOX_AXIS_EDGES for edge in axis_edges)


def box_axis_segments(
    corners: Mapping[str, Point2D],
    axis_index: int,
) -> tuple[Segment2D, ...]:
    """Return all four projected cuboid edges for one local box axis."""

    try:
        edges = BOX_AXIS_EDGES[axis_index]
    except IndexError as error:
        raise GeometryError(f"Unsupported box axis index {axis_index!r}.") from error
    missing = [name for edge in edges for name in edge if name not in corners]
    if missing:
        raise GeometryError(f"Match box is missing corners: {', '.join(sorted(set(missing)))}.")
    return tuple(Segment2D(corners[start], corners[end]) for start, end in edges)


def solve_box_match(solve_input, corners: Mapping[str, Point2D]):
    """Solve a projected cuboid and resolve VP direction signs from its edges."""

    from lens_solver.core.solver_2vp import solve_2vp

    first_segments = box_axis_segments(corners, 0)
    second_segments = box_axis_segments(corners, 1)
    provisional = solve_2vp(
        replace(
            solve_input,
            vp1_segments=first_segments,
            vp2_segments=second_segments,
        )
    )
    if not provisional.ok:
        return provisional
    first_vp, second_vp, _ = provisional.vanishing_points_ui
    if first_vp is None or second_vp is None:
        return provisional
    oriented_input = replace(
        solve_input,
        vp1_segments=first_segments,
        vp2_segments=second_segments,
        first_axis=_axis_oriented_by_segments(solve_input.first_axis, first_segments, first_vp),
        second_axis=_axis_oriented_by_segments(
            solve_input.second_axis,
            second_segments,
            second_vp,
        ),
    )
    result = solve_2vp(oriented_input)
    if _is_reflected_below_nuke_ground_plane(result, oriented_input):
        return solve_2vp(replace(oriented_input, first_axis=_flipped_axis(oriented_input.first_axis)))
    return result


def _axis_oriented_by_segments(
    axis: str,
    segments: tuple[Segment2D, ...],
    vanishing_point: Point2D,
) -> str:
    """Flip an axis when positive box edges run away from their vanishing point."""

    score = 0.0
    for segment in segments:
        direction = segment.direction().normalized()
        to_vanishing_point = (vanishing_point - segment.start).normalized()
        score += direction.dot(to_vanishing_point)
    if abs(score) <= DEFAULT_TOLERANCE:
        raise GeometryError("Could not resolve match-box axis direction.")
    return axis if score > 0.0 else _flipped_axis(axis)


def _flipped_axis(axis: str) -> str:
    try:
        sign, name = axis[0], axis[1:].upper()
    except (IndexError, TypeError) as error:
        raise GeometryError(f"Unsupported world axis {axis!r}.") from error
    if sign not in ("+", "-") or name not in ("X", "Y", "Z"):
        raise GeometryError(f"Unsupported world axis {axis!r}.")
    return f"{'-' if sign == '+' else '+'}{name}"


def _is_reflected_below_nuke_ground_plane(result, solve_input) -> bool:
    """Prefer the +Y half-space for Nuke's X/Z ground-plane box workflow."""

    if not result.ok or result.camera_position is None:
        return False
    axes = {
        solve_input.first_axis.upper().strip("+-"),
        solve_input.second_axis.upper().strip("+-"),
    }
    return axes == {"X", "Z"} and result.camera_position.y < -DEFAULT_TOLERANCE
