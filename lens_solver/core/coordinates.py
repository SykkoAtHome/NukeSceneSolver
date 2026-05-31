"""Explicit conversions between UI, pixel, and solver image coordinates.

UI coordinates are relative to image dimensions: ``(0, 0)`` is the top-left
corner and ``(1, 1)`` is the bottom-right corner. Solver coordinates use the
principal point as origin, point upward on Y, and are normalized by image
width. Consequently, the full solver-plane height is ``image_height /
image_width``.
"""

from __future__ import annotations

from dataclasses import dataclass

from lens_solver.core.models import Point2D


@dataclass(frozen=True, slots=True)
class ImageDimensions:
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Image dimensions must be positive.")

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height

    @property
    def height_relative_to_width(self) -> float:
        return self.height / self.width


DEFAULT_PRINCIPAL_POINT = Point2D(0.5, 0.5)


def pixel_to_ui(point: Point2D, dimensions: ImageDimensions) -> Point2D:
    """Convert continuous pixel coordinates to normalized UI coordinates."""

    return Point2D(point.x / dimensions.width, point.y / dimensions.height)


def ui_to_pixel(point: Point2D, dimensions: ImageDimensions) -> Point2D:
    """Convert normalized UI coordinates to continuous pixel coordinates."""

    return Point2D(point.x * dimensions.width, point.y * dimensions.height)


def ui_to_solver(
    point: Point2D,
    dimensions: ImageDimensions,
    principal_point: Point2D = DEFAULT_PRINCIPAL_POINT,
) -> Point2D:
    """Convert normalized UI coordinates to the solver image plane."""

    return Point2D(
        point.x - principal_point.x,
        (principal_point.y - point.y) * dimensions.height_relative_to_width,
    )


def solver_to_ui(
    point: Point2D,
    dimensions: ImageDimensions,
    principal_point: Point2D = DEFAULT_PRINCIPAL_POINT,
) -> Point2D:
    """Convert solver image-plane coordinates to normalized UI coordinates."""

    return Point2D(
        point.x + principal_point.x,
        principal_point.y - point.y / dimensions.height_relative_to_width,
    )

