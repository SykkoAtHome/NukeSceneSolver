"""Coarse axis-aligned scene reconstruction helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from scene_solver.core.box_match import BOX_CORNER_NAMES
from scene_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Vector3D
from scene_solver.core.reference_distance import (
    axis_coordinate_from_ui,
    world_ray_from_ui,
    world_axis_vector,
)
from scene_solver.core.solver_2vp import SolveResult


@dataclass(frozen=True, slots=True)
class MatchBox:
    """Axis-aligned box transform suitable for a Nuke Cube node."""

    center: Vector3D
    size: Vector3D
    warnings: tuple[str, ...] = ()


def reconstruct_match_box(
    result: SolveResult,
    corners: Mapping[str, Point2D],
    first_axis: str,
    second_axis: str,
    *,
    base_plane_offset: float | None = None,
) -> MatchBox:
    """Recover a coarse box, optionally anchored to a known parallel base plane."""

    if not result.ok:
        raise GeometryError("Cannot reconstruct a match box from an unsuccessful solve.")
    if (
        result.image_dimensions is None
        or result.relative_focal_length is None
        or result.camera_to_world_matrix is None
        or result.camera_position is None
    ):
        raise GeometryError("Solve result is missing data required for box reconstruction.")
    missing = [name for name in BOX_CORNER_NAMES if name not in corners]
    if missing:
        raise GeometryError(f"Match box is missing corners: {', '.join(missing)}.")

    axis1 = world_axis_vector(first_axis)
    axis2 = world_axis_vector(second_axis)
    if abs(axis1.dot(axis2)) > DEFAULT_TOLERANCE:
        raise GeometryError("Match box axes must be perpendicular.")
    axis3 = _missing_axis_vector(first_axis, second_axis)
    focal_plane_distance = result.relative_focal_length / 2.0
    common = {
        "dimensions": result.image_dimensions,
        "principal_point": result.principal_point_ui,
        "focal_plane_distance": focal_plane_distance,
        "camera_to_world_rotation": result.camera_to_world_matrix,
        "camera_position": result.camera_position,
    }
    anchor_ray = world_ray_from_ui(corners["box_v000"], **{
        key: value for key, value in common.items() if key != "camera_position"
    })
    if base_plane_offset is None:
        base = result.camera_position + anchor_ray * result.camera_position.length()
    else:
        denominator = axis3.dot(anchor_ray)
        if abs(denominator) <= DEFAULT_TOLERANCE:
            raise GeometryError("Match box anchor ray is parallel to its base plane.")
        distance = (
            base_plane_offset - axis3.dot(result.camera_position)
        ) / denominator
        base = result.camera_position + anchor_ray * distance
    extent1, residual1 = axis_coordinate_from_ui(
        corners["box_v100"],
        line_origin=base,
        line_direction=axis1,
        **common,
    )
    extent2, residual2 = axis_coordinate_from_ui(
        corners["box_v010"],
        line_origin=base,
        line_direction=axis2,
        **common,
    )
    base_points = {
        "box_v000": base,
        "box_v100": base + axis1 * extent1,
        "box_v010": base + axis2 * extent2,
    }
    alternative_extent1, residual3 = axis_coordinate_from_ui(
        corners["box_v110"],
        line_origin=base_points["box_v010"],
        line_direction=axis1,
        **common,
    )
    alternative_extent2, residual4 = axis_coordinate_from_ui(
        corners["box_v110"],
        line_origin=base_points["box_v100"],
        line_direction=axis2,
        **common,
    )
    extent1 = _average(
        extent1,
        alternative_extent1,
    )
    extent2 = _average(
        extent2,
        alternative_extent2,
    )
    if abs(extent1) <= DEFAULT_TOLERANCE or abs(extent2) <= DEFAULT_TOLERANCE:
        raise GeometryError("Match box base must have non-zero dimensions.")

    reconstructed_bases = {
        "box_v000": base,
        "box_v100": base + axis1 * extent1,
        "box_v010": base + axis2 * extent2,
        "box_v110": base + axis1 * extent1 + axis2 * extent2,
    }
    upper_by_base = {
        "box_v000": "box_v001",
        "box_v100": "box_v101",
        "box_v010": "box_v011",
        "box_v110": "box_v111",
    }
    heights: list[float] = []
    residuals: list[float] = [residual1, residual2, residual3, residual4]
    for base_name, upper_name in upper_by_base.items():
        height, residual = axis_coordinate_from_ui(
            corners[upper_name],
            line_origin=reconstructed_bases[base_name],
            line_direction=axis3,
            **common,
        )
        heights.append(height)
        residuals.append(residual)
    extent3 = sum(heights) / len(heights)
    if abs(extent3) <= DEFAULT_TOLERANCE:
        raise GeometryError("Match box height must be non-zero.")

    warnings: list[str] = []
    max_extent = max(abs(extent1), abs(extent2), abs(extent3))
    if max(residuals) > max(max_extent * 0.02, 1e-6):
        warnings.append("Match box edges are approximate for the current solve.")
    if base_plane_offset is None:
        warnings.append(
            "Match box placement is local to its image projection; provide a base-plane "
            "offset for absolute world placement. Scene grid remains anchored at Scene Origin."
        )

    center = base + axis1 * (extent1 * 0.5) + axis2 * (extent2 * 0.5) + axis3 * (extent3 * 0.5)
    return MatchBox(
        center=center,
        size=Vector3D(
            abs(axis1.x * extent1) + abs(axis2.x * extent2) + abs(axis3.x * extent3),
            abs(axis1.y * extent1) + abs(axis2.y * extent2) + abs(axis3.y * extent3),
            abs(axis1.z * extent1) + abs(axis2.z * extent2) + abs(axis3.z * extent3),
        ),
        warnings=tuple(warnings),
    )


def _average(first: float, second: float) -> float:
    return (first + second) * 0.5


def _missing_axis_vector(first_axis: str, second_axis: str) -> Vector3D:
    """Return the right-handed third axis regardless of input axis order."""

    axis_by_index = {
        _axis_index(first_axis): world_axis_vector(first_axis),
        _axis_index(second_axis): world_axis_vector(second_axis),
    }
    if len(axis_by_index) != 2:
        raise GeometryError("Match box axes must be different.")
    missing_axis = ({0, 1, 2} - set(axis_by_index)).pop()
    if missing_axis == 0:
        return axis_by_index[1].cross(axis_by_index[2]).normalized()
    if missing_axis == 1:
        return axis_by_index[2].cross(axis_by_index[0]).normalized()
    return axis_by_index[0].cross(axis_by_index[1]).normalized()


def _axis_index(axis: str) -> int:
    try:
        return {"X": 0, "Y": 1, "Z": 2}[axis.upper().strip("+-")]
    except (AttributeError, KeyError) as error:
        raise GeometryError(f"Unsupported world axis {axis!r}.") from error
