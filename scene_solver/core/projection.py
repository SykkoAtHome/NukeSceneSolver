"""Projection helpers for the solver's pinhole-camera convention."""

from __future__ import annotations

from math import sqrt

from scene_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Matrix4, Point2D, Vector3D


def solver_point_to_camera_ray(point: Point2D, focal_plane_distance: float) -> Vector3D:
    """Return a normalized camera-space ray through a solver-plane point."""

    if focal_plane_distance <= 0.0:
        raise GeometryError("Focal plane distance must be positive.")
    return Vector3D(point.x, point.y, -focal_plane_distance).normalized()


def camera_direction_to_solver_point(
    direction: Vector3D,
    focal_plane_distance: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Point2D:
    """Project a camera-space direction onto the normalized solver plane."""

    if focal_plane_distance <= 0.0:
        raise GeometryError("Focal plane distance must be positive.")
    if abs(direction.z) <= tolerance:
        raise GeometryError("Camera direction projects to a vanishing point at infinity.")
    return Point2D(
        -focal_plane_distance * direction.x / direction.z,
        -focal_plane_distance * direction.y / direction.z,
    )


def solver_projection_matrix(
    focal_plane_distance: float,
    world_to_camera_matrix: Matrix4,
) -> Matrix4:
    """Build the full world-to-solver-plane homogeneous projection matrix."""

    if focal_plane_distance <= 0.0:
        raise GeometryError("Focal plane distance must be positive.")
    camera_to_solver = Matrix4.from_rows(
        (
            (-focal_plane_distance, 0.0, 0.0, 0.0),
            (0.0, -focal_plane_distance, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
        )
    )
    return camera_to_solver @ world_to_camera_matrix


def world_plane_horizon_solver_line(
    projection_matrix: Matrix4,
    first_axis_index: int,
    second_axis_index: int,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[float, float, float]:
    """Return ``a, b, c`` for a projected world plane's solver-space horizon."""

    if (
        first_axis_index not in (0, 1, 2)
        or second_axis_index not in (0, 1, 2)
        or first_axis_index == second_axis_index
    ):
        raise GeometryError("A world plane requires two different axis indices.")

    vanishing_points = []
    for axis_index in (first_axis_index, second_axis_index):
        direction = [0.0, 0.0, 0.0, 0.0]
        direction[axis_index] = 1.0
        vanishing_points.append(
            tuple(
                sum(projection_matrix.rows[row][column] * direction[column] for column in range(4))
                for row in (0, 1, 3)
            )
        )

    first, second = vanishing_points
    a = first[1] * second[2] - first[2] * second[1]
    b = first[2] * second[0] - first[0] * second[2]
    c = first[0] * second[1] - first[1] * second[0]
    normal_length = sqrt(a * a + b * b)
    if normal_length <= tolerance:
        raise GeometryError("Could not project the world-plane horizon.")
    return a / normal_length, b / normal_length, c / normal_length
