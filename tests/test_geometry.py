from math import isclose

import pytest

from lens_solver.core.geometry import (
    GeometryError,
    line_intersection,
    line_intersection_least_squares,
)
from lens_solver.core.models import Matrix4, Point2D, Segment2D, Vector2D, Vector3D


def assert_vector3_close(actual: Vector3D, expected: Vector3D) -> None:
    assert isclose(actual.x, expected.x, abs_tol=1e-9)
    assert isclose(actual.y, expected.y, abs_tol=1e-9)
    assert isclose(actual.z, expected.z, abs_tol=1e-9)


def test_line_intersection_uses_infinite_lines() -> None:
    first = Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 1.0))
    second = Segment2D(Point2D(0.0, 2.0), Point2D(1.0, 2.0))

    assert line_intersection(first, second) == Point2D(2.0, 2.0)


def test_line_intersection_rejects_parallel_lines() -> None:
    first = Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 1.0))
    second = Segment2D(Point2D(0.0, 1.0), Point2D(1.0, 2.0))

    with pytest.raises(GeometryError, match="parallel"):
        line_intersection(first, second)


def test_line_intersection_rejects_nearly_parallel_lines() -> None:
    first = Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 0.0))
    second = Segment2D(Point2D(0.0, 1.0), Point2D(1.0, 1.0 + 1e-12))

    with pytest.raises(GeometryError, match="parallel"):
        line_intersection(first, second)


def test_line_intersection_rejects_zero_length_segment() -> None:
    first = Segment2D(Point2D(1.0, 1.0), Point2D(1.0, 1.0))
    second = Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 1.0))

    with pytest.raises(GeometryError, match="zero-length"):
        line_intersection(first, second)


def test_line_intersection_least_squares_uses_all_lines() -> None:
    segments = (
        Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 1.0)),
        Segment2D(Point2D(0.0, 2.0), Point2D(1.0, 2.0)),
        Segment2D(Point2D(2.0, 0.0), Point2D(2.0, 1.0)),
    )

    intersection = line_intersection_least_squares(segments)

    assert isclose(intersection.x, 2.0, abs_tol=1e-9)
    assert isclose(intersection.y, 2.0, abs_tol=1e-9)


def test_vector2_normalization_rejects_zero_vector() -> None:
    with pytest.raises(GeometryError, match="zero-length"):
        Vector2D(0.0, 0.0).normalized()


def test_vector3_dot_cross_and_normalization() -> None:
    x_axis = Vector3D(1.0, 0.0, 0.0)
    y_axis = Vector3D(0.0, 1.0, 0.0)

    assert x_axis.dot(y_axis) == 0.0
    assert x_axis.cross(y_axis) == Vector3D(0.0, 0.0, 1.0)
    assert Vector3D(3.0, 0.0, 4.0).normalized() == Vector3D(0.6, 0.0, 0.8)


def test_vector3_normalization_rejects_zero_vector() -> None:
    with pytest.raises(GeometryError, match="zero-length"):
        Vector3D(0.0, 0.0, 0.0).normalized()


def test_matrix_composition_and_inverse_restore_point() -> None:
    transform = Matrix4.translation(Vector3D(10.0, -2.0, 4.0)) @ Matrix4.scaling(
        Vector3D(2.0, 3.0, 4.0)
    )
    point = Vector3D(1.0, 2.0, 3.0)

    assert_vector3_close(transform.transform_point(point), Vector3D(12.0, 4.0, 16.0))
    assert_vector3_close(transform.inverse().transform_point(transform.transform_point(point)), point)
    assert isclose(transform.determinant(), 24.0)


def test_matrix_transform_direction_ignores_translation() -> None:
    transform = Matrix4.translation(Vector3D(10.0, -2.0, 4.0))

    assert transform.transform_direction(Vector3D(1.0, 2.0, 3.0)) == Vector3D(1.0, 2.0, 3.0)


def test_matrix_inverse_rejects_singular_matrix() -> None:
    matrix = Matrix4.scaling(Vector3D(1.0, 0.0, 1.0))

    with pytest.raises(GeometryError, match="singular"):
        matrix.inverse()
