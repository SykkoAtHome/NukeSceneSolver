from math import isclose

import pytest

from lens_solver.core.coordinates import (
    ImageDimensions,
    pixel_to_ui,
    solver_to_ui,
    ui_to_pixel,
    ui_to_solver,
)
from lens_solver.core.models import Point2D


@pytest.mark.parametrize(
    "dimensions",
    (
        ImageDimensions(1920, 1080),
        ImageDimensions(1080, 1920),
        ImageDimensions(2048, 2048),
    ),
)
@pytest.mark.parametrize(
    "point",
    (
        Point2D(0.0, 0.0),
        Point2D(0.5, 0.5),
        Point2D(1.0, 1.0),
        Point2D(0.125, 0.875),
    ),
)
def test_ui_solver_round_trip(dimensions: ImageDimensions, point: Point2D) -> None:
    result = solver_to_ui(ui_to_solver(point, dimensions), dimensions)

    assert isclose(result.x, point.x, abs_tol=1e-12)
    assert isclose(result.y, point.y, abs_tol=1e-12)


@pytest.mark.parametrize(
    ("dimensions", "expected_top_left", "expected_bottom_right"),
    (
        (ImageDimensions(1920, 1080), Point2D(-0.5, 0.28125), Point2D(0.5, -0.28125)),
        (
            ImageDimensions(1080, 1920),
            Point2D(-0.5, 0.8888888888888888),
            Point2D(0.5, -0.8888888888888888),
        ),
        (ImageDimensions(2048, 2048), Point2D(-0.5, 0.5), Point2D(0.5, -0.5)),
    ),
)
def test_ui_to_solver_accounts_for_aspect_ratio(
    dimensions: ImageDimensions,
    expected_top_left: Point2D,
    expected_bottom_right: Point2D,
) -> None:
    assert ui_to_solver(Point2D(0.0, 0.0), dimensions) == expected_top_left
    assert ui_to_solver(Point2D(1.0, 1.0), dimensions) == expected_bottom_right
    assert ui_to_solver(Point2D(0.5, 0.5), dimensions) == Point2D(0.0, 0.0)


def test_ui_solver_round_trip_supports_custom_principal_point() -> None:
    dimensions = ImageDimensions(1920, 1080)
    principal_point = Point2D(0.4, 0.6)
    point = Point2D(0.75, 0.25)

    solver_point = ui_to_solver(point, dimensions, principal_point)

    assert solver_point == Point2D(0.35, 0.196875)
    assert solver_to_ui(solver_point, dimensions, principal_point) == point


def test_pixel_ui_round_trip() -> None:
    dimensions = ImageDimensions(1920, 1080)
    point = Point2D(480.0, 810.0)

    assert ui_to_pixel(pixel_to_ui(point, dimensions), dimensions) == point


@pytest.mark.parametrize(
    ("width", "height"),
    (
        (0, 1080),
        (1920, 0),
        (-1, 1080),
    ),
)
def test_image_dimensions_must_be_positive(width: int, height: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        ImageDimensions(width, height)
