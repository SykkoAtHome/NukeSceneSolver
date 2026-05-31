"""Numerically guarded geometry operations."""

from __future__ import annotations

from lens_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Segment2D


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

