"""Numerically guarded geometry operations."""

from __future__ import annotations

from collections.abc import Iterable

from scene_solver.core.models import DEFAULT_TOLERANCE, GeometryError, Point2D, Segment2D


# The accumulated normal matrix M = AtA (A = rows of unit normals) is positive
# semi-definite, and by Cauchy-Binet det(M) = sum over line pairs of
# sin^2(angle between that pair). Dividing by the pair count therefore yields
# the MEAN pairwise sin^2, which equals sin^2(theta) for exactly two lines.
# Testing that mean (instead of the raw determinant) keeps the threshold's
# angular meaning independent of how many lines were fitted: the raw
# determinant grows ~N^2, so a fixed floor would silently get more lenient as
# more lines are added (e.g. box mode supplies four edges per axis).
#
# A 1e-6 floor rejects a mean angular spread narrower than ~0.06 degrees, where
# the recovered intersection is dominated by handle-marking noise rather than
# the real vanishing point. This is intentionally far stricter than
# DEFAULT_TOLERANCE, which would silently accept near-parallel lines and return
# a wildly unstable point.
MIN_INTERSECTION_DETERMINANT = 1e-6


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
    # Mean pairwise sin^2 (see MIN_INTERSECTION_DETERMINANT). len(values) >= 2 is
    # guaranteed above, so the pair count is always >= 1.
    pair_count = len(values) * (len(values) - 1) / 2.0
    if determinant / pair_count <= MIN_INTERSECTION_DETERMINANT:
        raise GeometryError(
            "Vanishing-point lines are too close to parallel; their intersection "
            "is numerically unstable. Mark lines that diverge more clearly."
        )
    return Point2D(
        (normal_x_rhs * normal_y_squared - normal_xy * normal_y_rhs) / determinant,
        (normal_x_squared * normal_y_rhs - normal_xy * normal_x_rhs) / determinant,
    )
