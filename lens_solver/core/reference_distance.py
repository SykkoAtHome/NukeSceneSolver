"""Reference-distance calibration for an arbitrary-scale camera solve."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from lens_solver.core.coordinates import ImageDimensions, ui_to_solver
from lens_solver.core.models import (
    DEFAULT_TOLERANCE,
    GeometryError,
    Matrix4,
    Point2D,
    Segment2D,
    Vector3D,
)
from lens_solver.core.projection import solver_point_to_camera_ray


AXIS_VECTORS = {
    "+X": Vector3D(1.0, 0.0, 0.0),
    "-X": Vector3D(-1.0, 0.0, 0.0),
    "+Y": Vector3D(0.0, 1.0, 0.0),
    "-Y": Vector3D(0.0, -1.0, 0.0),
    "+Z": Vector3D(0.0, 0.0, 1.0),
    "-Z": Vector3D(0.0, 0.0, -1.0),
}


@dataclass(frozen=True, slots=True)
class ReferenceDistanceInput:
    """A known-length image segment on a world axis through scene origin."""

    segment_ui: Segment2D
    axis: str = "+X"
    distance: float = 1.0


@dataclass(frozen=True, slots=True)
class ReferenceDistanceCalibration:
    axis: str
    distance: float
    measured_distance: float
    scale_factor: float
    points_world: tuple[Vector3D, Vector3D]
    warnings: tuple[str, ...]


def calibrate_reference_distance(
    reference: ReferenceDistanceInput,
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
    camera_position: Vector3D,
) -> ReferenceDistanceCalibration:
    """Recover scene scale from a segment on an axis passing through origin."""

    if not isfinite(reference.distance) or reference.distance <= 0.0:
        raise GeometryError("Reference distance must be a finite positive value.")

    axis = world_axis_vector(reference.axis)
    start_coordinate, start_residual = axis_coordinate_from_ui(
        reference.segment_ui.start,
        line_origin=Vector3D(0.0, 0.0, 0.0),
        line_direction=axis,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
        camera_position=camera_position,
    )
    end_coordinate, end_residual = axis_coordinate_from_ui(
        reference.segment_ui.end,
        line_origin=Vector3D(0.0, 0.0, 0.0),
        line_direction=axis,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
        camera_position=camera_position,
    )
    measured_distance = abs(end_coordinate - start_coordinate)
    if measured_distance <= DEFAULT_TOLERANCE:
        raise GeometryError("Reference line endpoints must define a non-zero world distance.")

    scale_factor = reference.distance / measured_distance
    warnings: list[str] = []
    residual = max(start_residual, end_residual)
    if residual > max(measured_distance * 0.02, 1e-6):
        warnings.append(
            "Reference line is not closely aligned with the selected world axis; "
            "scene scale is approximate."
        )

    return ReferenceDistanceCalibration(
        axis=reference.axis.upper(),
        distance=reference.distance,
        measured_distance=measured_distance,
        scale_factor=scale_factor,
        points_world=(
            axis * (start_coordinate * scale_factor),
            axis * (end_coordinate * scale_factor),
        ),
        warnings=tuple(warnings),
    )


def world_axis_vector(axis: str) -> Vector3D:
    try:
        return AXIS_VECTORS[axis.upper()]
    except (AttributeError, KeyError) as error:
        raise GeometryError(
            f"Unsupported world axis {axis!r}. Expected one of: {', '.join(AXIS_VECTORS)}."
        ) from error


def world_ray_from_ui(
    point: Point2D,
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
) -> Vector3D:
    solver_point = ui_to_solver(point, dimensions, principal_point)
    camera_ray = solver_point_to_camera_ray(solver_point, focal_plane_distance)
    return camera_to_world_rotation.transform_direction(camera_ray).normalized()


def axis_coordinate_from_ui(
    point: Point2D,
    *,
    line_origin: Vector3D,
    line_direction: Vector3D,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
    camera_position: Vector3D,
) -> tuple[float, float]:
    """Return closest line coordinate and residual for a projected world line."""

    direction = line_direction.normalized()
    world_ray = world_ray_from_ui(
        point,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
    )
    offset = camera_position - line_origin
    direction_cross_ray = direction.cross(world_ray)
    denominator = direction_cross_ray.dot(direction_cross_ray)
    if denominator <= DEFAULT_TOLERANCE:
        raise GeometryError("Reference line projects too close to its vanishing point.")

    coordinate = offset.cross(world_ray).dot(direction_cross_ray) / denominator
    point_on_line = line_origin + direction * coordinate
    ray_parameter = (point_on_line - camera_position).dot(world_ray)
    point_on_ray = camera_position + world_ray * ray_parameter
    return coordinate, (point_on_ray - point_on_line).length()


def intersect_ui_ray_with_plane(
    point: Point2D,
    *,
    plane_origin: Vector3D,
    plane_normal: Vector3D,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
    camera_position: Vector3D,
) -> Vector3D:
    """Intersect an image ray with a world-space plane."""

    normal = plane_normal.normalized()
    world_ray = world_ray_from_ui(
        point,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
    )
    denominator = normal.dot(world_ray)
    if abs(denominator) <= DEFAULT_TOLERANCE:
        raise GeometryError("Image ray is parallel to the reconstruction plane.")
    distance = normal.dot(plane_origin - camera_position) / denominator
    return camera_position + world_ray * distance
