"""Qt-free saved-state migrations for the Scene Solver panel."""

from __future__ import annotations

from itertools import product

from scene_solver.core.axes import normalized_world_axis_name, parse_world_axis, signed_world_axis_name
from scene_solver.core.coordinates import DEFAULT_PRINCIPAL_POINT
from scene_solver.core.geometry import line_intersection_least_squares
from scene_solver.core.models import GeometryError, Point2D, Segment2D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp


def migrate_legacy_canvas_directions(
    canvas_state: dict[str, dict[str, float]],
    *,
    first_axis: str = "+X",
    second_axis: str = "+Z",
    third_axis: str = "+Y",
    mode: str = "2vp",
    principal_point: Point2D | None = None,
) -> dict[str, dict[str, float]]:
    """Convert pre-directed VP handles while preserving their signed-axis solve.

    Older scripts stored signed axis selectors, but segment endpoint order had
    no meaning. The directed-line solver derives the sign from that order, so
    orient each legacy segment to reproduce the old selector signs. Third-axis
    lines need a solved-frame check because the positive projected direction can
    point either toward or away from a finite VP.
    """

    migrated = _copy_canvas_state(canvas_state)
    if mode == "box":
        return migrated

    _orient_group_for_axis(migrated, "vp1", first_axis)
    if mode in {"2vp", "3vp"}:
        _orient_group_for_axis(migrated, "vp2", second_axis)
    if mode == "3vp":
        migrated = _orient_third_axis_group(
            migrated,
            first_axis=first_axis,
            second_axis=second_axis,
            third_axis=third_axis,
            principal_point=principal_point,
        )
    return migrated


def _copy_canvas_state(
    canvas_state: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    return {name: dict(position) for name, position in canvas_state.items()}


def _orient_group_for_axis(
    canvas_state: dict[str, dict[str, float]],
    group: str,
    axis: str,
) -> None:
    segments = _group_segments(canvas_state, group)
    if len(segments) < 2:
        return
    try:
        vanishing_point = line_intersection_least_squares(segment for _, segment in segments)
    except GeometryError:
        return

    points_toward_vp = parse_world_axis(signed_world_axis_name(axis))[1] > 0.0
    for name, segment in segments:
        try:
            score = segment.direction().normalized().dot(
                (vanishing_point - segment.start).normalized()
            )
        except GeometryError:
            continue
        if (score > 0.0) != points_toward_vp:
            _reverse_segment(canvas_state, name)


def _orient_third_axis_group(
    canvas_state: dict[str, dict[str, float]],
    *,
    first_axis: str,
    second_axis: str,
    third_axis: str,
    principal_point: Point2D | None,
) -> dict[str, dict[str, float]]:
    third_segments = _group_segments(canvas_state, "vp3")
    if not third_segments:
        return canvas_state

    names = tuple(name for name, _ in third_segments)
    for reversals in product((False, True), repeat=len(names)):
        candidate = _copy_canvas_state(canvas_state)
        for name, reverse in zip(names, reversals):
            if reverse:
                _reverse_segment(candidate, name)
        if _third_axis_candidate_solves(
            candidate,
            first_axis=first_axis,
            second_axis=second_axis,
            third_axis=third_axis,
            principal_point=principal_point,
        ):
            return candidate
    return canvas_state


def _third_axis_candidate_solves(
    canvas_state: dict[str, dict[str, float]],
    *,
    first_axis: str,
    second_axis: str,
    third_axis: str,
    principal_point: Point2D | None,
) -> bool:
    result = solve_2vp(
        SolveInput(
            image_width=1920,
            image_height=1080,
            vp1_segments=tuple(segment for _, segment in _group_segments(canvas_state, "vp1")),
            vp2_segments=tuple(segment for _, segment in _group_segments(canvas_state, "vp2")),
            vp3_segments=tuple(segment for _, segment in _group_segments(canvas_state, "vp3")),
            principal_point=principal_point,
            origin=_state_point(canvas_state, "origin") or DEFAULT_PRINCIPAL_POINT,
            first_axis=normalized_world_axis_name(first_axis),
            second_axis=normalized_world_axis_name(second_axis),
            third_axis=normalized_world_axis_name(third_axis),
            mode="3vp",
        )
    )
    return result.ok


def _group_segments(
    canvas_state: dict[str, dict[str, float]],
    group: str,
) -> tuple[tuple[str, Segment2D], ...]:
    segments = []
    for suffix in ("a", "b"):
        name = f"{group}_{suffix}"
        start = _state_point(canvas_state, f"{name}_start")
        end = _state_point(canvas_state, f"{name}_end")
        if start is not None and end is not None:
            segments.append((name, Segment2D(start, end)))
    return tuple(segments)


def _state_point(
    canvas_state: dict[str, dict[str, float]],
    name: str,
) -> Point2D | None:
    values = canvas_state.get(name)
    if values is None:
        return None
    try:
        return Point2D(values["x"], values["y"])
    except (KeyError, TypeError, ValueError):
        return None


def _reverse_segment(canvas_state: dict[str, dict[str, float]], name: str) -> None:
    start, end = f"{name}_start", f"{name}_end"
    canvas_state[start], canvas_state[end] = canvas_state[end], canvas_state[start]
