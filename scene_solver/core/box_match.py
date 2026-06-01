"""Projected cuboid helpers shared by the core solver and UI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import isclose, isfinite

from scene_solver.core.axes import flipped_world_axis, normalized_world_axis_name
from scene_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Segment2D


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


@dataclass(frozen=True, slots=True)
class BoxDimensionInput:
    """Known world-space length of one reconstructed cuboid dimension."""

    axis: str = "X"
    length: float = 1.0


@dataclass(frozen=True, slots=True)
class BoxDimensionCalibration:
    """Resolved camera distance for a known match-box dimension."""

    axis: str
    length: float
    measured_length: float
    camera_distance: float
    iterations: int


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

    from scene_solver.core.solver_2vp import solve_2vp

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
        return solve_2vp(
            replace(oriented_input, first_axis=flipped_world_axis(oriented_input.first_axis))
        )
    return result


def solve_box_match_with_dimension(
    solve_input,
    corners: Mapping[str, Point2D],
    reference: BoxDimensionInput,
    *,
    base_plane_offset: float = 0.0,
) -> tuple[object, BoxDimensionCalibration | None]:
    """Calibrate scene scale from a known cuboid dimension and base plane."""

    from scene_solver.core.scene_reconstruction import reconstruct_match_box

    axis = _dimension_axis(reference.axis)
    if not isfinite(reference.length) or reference.length <= 0.0:
        raise GeometryError("Match-box dimension must be a finite positive value.")
    if not isfinite(base_plane_offset):
        raise GeometryError("Match-box base offset must be finite.")

    base_input = replace(solve_input, reference_distance=None)
    result = solve_box_match(base_input, corners)
    if not result.ok:
        return result, None

    def evaluate(camera_distance: float):
        current_input = replace(base_input, camera_distance=camera_distance)
        current_result = solve_box_match(current_input, corners)
        if not current_result.ok:
            raise GeometryError("Could not solve match box while calibrating scene scale.")
        match_box = reconstruct_match_box(
            current_result,
            corners,
            base_input.first_axis,
            base_input.second_axis,
            base_plane_offset=base_plane_offset,
        )
        measured_length = _dimension_length(match_box.size, axis)
        if measured_length <= DEFAULT_TOLERANCE:
            raise GeometryError("Selected match-box dimension must be non-zero.")
        return current_result, measured_length

    def calibrated(current_result, measured_length: float, camera_distance: float, iterations: int):
        return (
            replace(
                current_result,
                warnings=tuple(
                    warning
                    for warning in current_result.warnings
                    if "scale are arbitrary" not in warning
                ),
            ),
            BoxDimensionCalibration(
                axis=axis,
                length=reference.length,
                measured_length=measured_length,
                camera_distance=camera_distance,
                iterations=iterations,
            ),
        )

    initial_distance = base_input.camera_distance
    result, measured_length = evaluate(initial_distance)
    if isclose(measured_length, reference.length, rel_tol=1e-9, abs_tol=1e-9):
        return calibrated(result, measured_length, initial_distance, 1)

    samples = [(initial_distance, result, measured_length)]
    bracket = None
    for expansion in range(1, 33):
        for camera_distance in (
            initial_distance / (2.0 ** expansion),
            initial_distance * (2.0 ** expansion),
        ):
            try:
                current_result, current_length = evaluate(camera_distance)
            except GeometryError:
                continue
            if isclose(current_length, reference.length, rel_tol=1e-9, abs_tol=1e-9):
                return calibrated(current_result, current_length, camera_distance, expansion + 1)
            samples.append((camera_distance, current_result, current_length))
        samples.sort(key=lambda sample: sample[0])
        for lower, upper in zip(samples, samples[1:]):
            if (lower[2] - reference.length) * (upper[2] - reference.length) < 0.0:
                bracket = (lower, upper)
                break
        if bracket is not None:
            break

    if bracket is None:
        raise GeometryError(
            "Could not bracket scene scale from the selected match-box dimension."
        )

    lower, upper = bracket
    for iteration in range(1, 65):
        camera_distance = (lower[0] + upper[0]) * 0.5
        current_result, current_length = evaluate(camera_distance)
        if isclose(current_length, reference.length, rel_tol=1e-9, abs_tol=1e-9):
            return calibrated(current_result, current_length, camera_distance, iteration)
        if (lower[2] - reference.length) * (current_length - reference.length) < 0.0:
            upper = (camera_distance, current_result, current_length)
        else:
            lower = (camera_distance, current_result, current_length)

    raise GeometryError(
        "Could not calibrate scene scale from the selected match-box dimension."
    )


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
    return axis if score > 0.0 else flipped_world_axis(axis)


def _is_reflected_below_nuke_ground_plane(result, solve_input) -> bool:
    """Prefer the +Y half-space for Nuke's X/Z ground-plane box workflow."""

    if not result.ok or result.camera_position is None:
        return False
    axes = {
        solve_input.first_axis.upper().strip("+-"),
        solve_input.second_axis.upper().strip("+-"),
    }
    return axes == {"X", "Z"} and result.camera_position.y < -DEFAULT_TOLERANCE


def _dimension_axis(axis: str) -> str:
    try:
        return normalized_world_axis_name(axis)
    except GeometryError as error:
        raise GeometryError(f"Unsupported match-box dimension axis {axis!r}.") from error


def _dimension_length(size, axis: str) -> float:
    return {"X": size.x, "Y": size.y, "Z": size.z}[axis]
