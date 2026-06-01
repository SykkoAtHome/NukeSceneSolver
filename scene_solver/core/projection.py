"""Projection helpers for the solver's pinhole-camera convention."""

from __future__ import annotations

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
