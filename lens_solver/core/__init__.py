"""Nuke-independent geometry and camera-solving foundations."""

from lens_solver.core.coordinates import (
    ImageDimensions,
    pixel_to_ui,
    solver_to_ui,
    ui_to_pixel,
    ui_to_solver,
)
from lens_solver.core.geometry import GeometryError, line_intersection
from lens_solver.core.models import Matrix4, Point2D, Segment2D, Vector2D, Vector3D
from lens_solver.core.projection import (
    camera_direction_to_solver_point,
    solver_point_to_camera_ray,
)
from lens_solver.core.solver_2vp import SolveInput, SolveResult, solve_2vp

__all__ = [
    "GeometryError",
    "ImageDimensions",
    "Matrix4",
    "Point2D",
    "Segment2D",
    "SolveInput",
    "SolveResult",
    "Vector2D",
    "Vector3D",
    "camera_direction_to_solver_point",
    "line_intersection",
    "pixel_to_ui",
    "solve_2vp",
    "solver_point_to_camera_ray",
    "solver_to_ui",
    "ui_to_pixel",
    "ui_to_solver",
]
