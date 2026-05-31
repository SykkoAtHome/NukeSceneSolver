"""Nuke-independent geometry and camera-solving foundations."""

from lens_solver.core.coordinates import (
    ImageDimensions,
    pixel_to_ui,
    solver_to_ui,
    ui_to_pixel,
    ui_to_solver,
)
from lens_solver.core.box_match import (
    BOX_AXIS_EDGES,
    BOX_CORNER_NAMES,
    BOX_EDGES,
    box_axis_segments,
    solve_box_match,
)
from lens_solver.core.geometry import GeometryError, line_intersection, line_intersection_least_squares
from lens_solver.core.models import Matrix4, Point2D, Segment2D, Vector2D, Vector3D
from lens_solver.core.projection import (
    camera_direction_to_solver_point,
    solver_point_to_camera_ray,
)
from lens_solver.core.reference_distance import (
    ReferenceDistanceCalibration,
    ReferenceDistanceInput,
    calibrate_reference_distance,
)
from lens_solver.core.scene_reconstruction import MatchBox, reconstruct_match_box
from lens_solver.core.solver_2vp import SolveInput, SolveResult, solve_2vp

__all__ = [
    "GeometryError",
    "BOX_AXIS_EDGES",
    "BOX_CORNER_NAMES",
    "BOX_EDGES",
    "ImageDimensions",
    "Matrix4",
    "Point2D",
    "ReferenceDistanceCalibration",
    "ReferenceDistanceInput",
    "Segment2D",
    "SolveInput",
    "SolveResult",
    "Vector2D",
    "Vector3D",
    "camera_direction_to_solver_point",
    "box_axis_segments",
    "calibrate_reference_distance",
    "line_intersection",
    "line_intersection_least_squares",
    "pixel_to_ui",
    "reconstruct_match_box",
    "solve_2vp",
    "solve_box_match",
    "solver_point_to_camera_ray",
    "solver_to_ui",
    "ui_to_pixel",
    "ui_to_solver",
    "MatchBox",
]
