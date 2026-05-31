"""Numerically guarded geometry operations."""

from __future__ import annotations

from collections.abc import Iterable

from scene_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Segment2D


def line_intersection(
    first: Segment2D,
    second: Segment2D,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Point2D:
    """Return the intersection of two infinite lines defined by segments."""

    first_direction = first.direction()
    second_direction = second.direction()
    first_length = first_direction.length()
    second_length = second_direction.length()

    if first_length <= tolerance or second_length <= tolerance:
        raise GeometryError("Cannot intersect a line defined by a zero-length segment.")

    cross = first_direction.cross(second_direction)
    normalized_cross = abs(cross) / (first_length * second_length)
    if normalized_cross <= tolerance:
        raise GeometryError("Cannot intersect parallel or nearly parallel lines.")

    start_delta = second.start - first.start
    distance_along_first = start_delta.cross(second_direction) / cross
    return first.start + first_direction * distance_along_first


def line_intersection_least_squares(
    segments: Iterable[Segment2D],
    tolerance: float = DEFAULT_TOLERANCE,
) -> Point2D:
    """Return the best-fit intersection of two or more infinite lines."""

    values = tuple(segments)
    if len(values) < 2:
        raise GeometryError("At least two line segments are required for intersection.")

    normal_x_squared = 0.0
    normal_xy = 0.0
    normal_y_squared = 0.0
    normal_x_rhs = 0.0
    normal_y_rhs = 0.0
    for segment in values:
        direction = segment.direction()
        length = direction.length()
        if length <= tolerance:
            raise GeometryError("Cannot intersect a line defined by a zero-length segment.")
        normal_x = -direction.y / length
        normal_y = direction.x / length
        rhs = normal_x * segment.start.x + normal_y * segment.start.y
        normal_x_squared += normal_x * normal_x
        normal_xy += normal_x * normal_y
        normal_y_squared += normal_y * normal_y
        normal_x_rhs += normal_x * rhs
        normal_y_rhs += normal_y * rhs

    determinant = normal_x_squared * normal_y_squared - normal_xy * normal_xy
    if abs(determinant) <= tolerance:
        raise GeometryError("Cannot intersect parallel or nearly parallel lines.")
    return Point2D(
        (normal_x_rhs * normal_y_squared - normal_xy * normal_y_rhs) / determinant,
        (normal_x_squared * normal_y_rhs - normal_xy * normal_x_rhs) / determinant,
    )
