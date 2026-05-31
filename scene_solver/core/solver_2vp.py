"""Two-vanishing-point calibration for a pinhole camera.

Input segment handles and the origin are stored in normalized UI coordinates.
The resulting matrices use row-major storage and column-vector transforms.
``camera_to_world_matrix`` maps camera-space points into the solver's world
space. Its translation is arbitrary until a reference distance is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, isfinite, sqrt

from scene_solver.core.coordinates import (
    DEFAULT_PRINCIPAL_POINT,
    ImageDimensions,
    solver_to_ui,
    ui_to_solver,
)
from scene_solver.core.geometry import line_intersection_least_squares
from scene_solver.core.models import (
    DEFAULT_TOLERANCE,
    GeometryError,
    Matrix4,
    Point2D,
    Segment2D,
    Vector3D,
)
from scene_solver.core.projection import (
    camera_direction_to_solver_point,
    solver_point_to_camera_ray,
)
from scene_solver.core.reference_distance import (
    ReferenceDistanceCalibration,
    ReferenceDistanceInput,
    calibrate_reference_distance,
)


DEFAULT_SENSOR_WIDTH_MM = 36.0
DEFAULT_CAMERA_DISTANCE = 10.0
AXIS_VECTORS = {
    "+X": (0, 1.0),
    "-X": (0, -1.0),
    "+Y": (1, 1.0),
    "-Y": (1, -1.0),
    "+Z": (2, 1.0),
    "-Z": (2, -1.0),
}


@dataclass(frozen=True, slots=True)
class SolveInput:
    image_width: int
    image_height: int
    vp1_segments: tuple[Segment2D, ...]
    vp2_segments: tuple[Segment2D, ...]
    vp3_segments: tuple[Segment2D, ...] = ()
    principal_point: Point2D | None = None
    origin: Point2D = DEFAULT_PRINCIPAL_POINT
    first_axis: str = "+X"
    second_axis: str = "+Y"
    third_axis: str = "+Z"
    sensor_width_mm: float = DEFAULT_SENSOR_WIDTH_MM
    known_focal_length_mm: float | None = None
    camera_distance: float = DEFAULT_CAMERA_DISTANCE
    reference_distance: ReferenceDistanceInput | None = None
    mode: str = "2vp"


@dataclass(frozen=True, slots=True)
class SolveResult:
    """Successful calibration data or controlled validation errors."""

    camera_to_world_matrix: Matrix4 | None
    world_to_camera_matrix: Matrix4 | None
    projection_matrix: Matrix4 | None  # Full P = K @ [R|t] projection
    camera_position: Vector3D | None
    relative_focal_length: float | None
    focal_length_mm: float | None
    horizontal_fov_radians: float | None
    vertical_fov_radians: float | None
    image_dimensions: ImageDimensions | None
    sensor_width_mm: float | None
    sensor_height_mm: float | None
    principal_point_ui: Point2D
    origin_ui: Point2D
    vanishing_points_ui: tuple[Point2D | None, Point2D | None, Point2D | None]
    vanishing_points_solver: tuple[Point2D | None, Point2D | None, Point2D | None]
    reference_distance: ReferenceDistanceCalibration | None
    warnings: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def camera_matrix(self) -> Matrix4 | None:
        """Compatibility alias for the camera-to-world matrix."""

        return self.camera_to_world_matrix


def solve_2vp(solve_input: SolveInput) -> SolveResult:
    """Recover camera intrinsics, orientation, and arbitrary-scale position."""

    warnings: list[str] = []
    dimensions = ImageDimensions(solve_input.image_width, solve_input.image_height)
    principal_point = solve_input.principal_point or DEFAULT_PRINCIPAL_POINT

    try:
        _validate_scalar("Sensor width", solve_input.sensor_width_mm)
        _validate_scalar("Camera distance", solve_input.camera_distance)
        first_axis = _parse_axis(solve_input.first_axis)
        second_axis = _parse_axis(solve_input.second_axis)

        if solve_input.mode == "1vp":
            return _solve_1vp(solve_input, dimensions)

        if solve_input.principal_point is None:
            if solve_input.vp3_segments:
                principal_point = _solve_principal_point_3vp(
                    solve_input.vp1_segments,
                    solve_input.vp2_segments,
                    solve_input.vp3_segments,
                    dimensions,
                )
            else:
                principal_point = DEFAULT_PRINCIPAL_POINT

        if first_axis[0] == second_axis[0]:
            raise GeometryError("The two vanishing points must map to different world axes.")

        first_vp_solver = _intersect_ui_segments(
            solve_input.vp1_segments,
            dimensions,
            principal_point,
        )
        second_vp_solver = _intersect_ui_segments(
            solve_input.vp2_segments,
            dimensions,
            principal_point,
        )

        focal_plane_squared = -(
            first_vp_solver.x * second_vp_solver.x
            + first_vp_solver.y * second_vp_solver.y
        )
        if focal_plane_squared <= DEFAULT_TOLERANCE:
            raise GeometryError(
                "Vanishing points do not define a positive focal length. "
                "Check that the marked directions are perpendicular."
            )
        focal_plane_distance = sqrt(focal_plane_squared)
        relative_focal_length = 2.0 * focal_plane_distance

        first_camera_direction = solver_point_to_camera_ray(
            first_vp_solver,
            focal_plane_distance,
        )
        second_camera_direction = solver_point_to_camera_ray(
            second_vp_solver,
            focal_plane_distance,
        )
        columns = _world_to_camera_columns(
            first_camera_direction,
            first_axis,
            second_camera_direction,
            second_axis,
        )
        camera_to_world_rotation = _camera_to_world_rotation(columns)
        if abs(camera_to_world_rotation.determinant() - 1.0) > 1e-7:
            raise GeometryError("Recovered camera rotation has an invalid determinant.")

        origin_solver = ui_to_solver(solve_input.origin, dimensions, principal_point)
        origin_camera_ray = solver_point_to_camera_ray(origin_solver, focal_plane_distance)
        origin_world_ray = camera_to_world_rotation.transform_direction(origin_camera_ray)
        camera_position = origin_world_ray * -solve_input.camera_distance
        reference_distance: ReferenceDistanceCalibration | None = None
        if solve_input.reference_distance is not None:
            reference_distance = calibrate_reference_distance(
                solve_input.reference_distance,
                dimensions=dimensions,
                principal_point=principal_point,
                focal_plane_distance=focal_plane_distance,
                camera_to_world_rotation=camera_to_world_rotation,
                camera_position=camera_position,
            )
            camera_position = camera_position * reference_distance.scale_factor
            warnings.extend(reference_distance.warnings)
        else:
            warnings.append(
                "Camera distance and scene scale are arbitrary until a reference distance is supplied."
            )
        camera_to_world_matrix = _with_translation(camera_to_world_rotation, camera_position)
        world_to_camera_matrix = camera_to_world_matrix.inverse()

        third_camera_direction = columns[_missing_axis_index(first_axis[0], second_axis[0])]
        third_vp_solver: Point2D | None
        third_vp_ui: Point2D | None
        try:
            third_vp_solver = camera_direction_to_solver_point(
                third_camera_direction,
                focal_plane_distance,
            )
            third_vp_ui = solver_to_ui(third_vp_solver, dimensions, principal_point)
        except GeometryError:
            third_vp_solver = None
            third_vp_ui = None
            warnings.append("The third vanishing point is at infinity.")

        sensor_height_mm = solve_input.sensor_width_mm * dimensions.height_relative_to_width
        focal_length_mm = focal_plane_distance * solve_input.sensor_width_mm
        # Build full projection matrix: P = K @ [R|t]
        # K maps camera-space points [Xc, Yc, Zc] to solver-plane [nx, ny]
        # Xc / Zc * focal_plane_distance, etc.
        # Note: focal_plane_distance is defined such that image height is 2.0 (from -1 to 1) 
        # in the solver coordinate system.
        k_matrix = Matrix4.from_rows((
            (-focal_plane_distance, 0.0, 0.0, 0.0),
            (0.0, -focal_plane_distance, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 1.0, 0.0)
        ))
        projection_matrix = k_matrix @ world_to_camera_matrix

        return SolveResult(
            camera_to_world_matrix=camera_to_world_matrix,
            world_to_camera_matrix=world_to_camera_matrix,
            projection_matrix=projection_matrix,
            camera_position=camera_position,
            relative_focal_length=relative_focal_length,
            focal_length_mm=focal_length_mm,
            horizontal_fov_radians=2.0 * atan(0.5 * solve_input.sensor_width_mm / focal_length_mm),
            vertical_fov_radians=2.0 * atan(0.5 * sensor_height_mm / focal_length_mm),
            image_dimensions=dimensions,
            sensor_width_mm=solve_input.sensor_width_mm,
            sensor_height_mm=sensor_height_mm,
            principal_point_ui=principal_point,
            origin_ui=solve_input.origin,
            vanishing_points_ui=(
                solver_to_ui(first_vp_solver, dimensions, principal_point),
                solver_to_ui(second_vp_solver, dimensions, principal_point),
                third_vp_ui,
            ),
            vanishing_points_solver=(first_vp_solver, second_vp_solver, third_vp_solver),
            reference_distance=reference_distance,
            warnings=tuple(warnings),
            errors=(),
        )
    except (GeometryError, ValueError) as error:
        return _error_result(principal_point, solve_input.origin, str(error), warnings)


def _solve_1vp(solve_input: SolveInput, dimensions: ImageDimensions) -> SolveResult:
    """Calibrate from one vanishing point and a known focal length + horizon."""

    principal_point = solve_input.principal_point or DEFAULT_PRINCIPAL_POINT
    warnings: list[str] = []

    if solve_input.known_focal_length_mm is None:
        raise GeometryError("Focal length must be provided for 1VP mode.")
    
    focal_plane_distance = solve_input.known_focal_length_mm / solve_input.sensor_width_mm
    relative_focal_length = 2.0 * focal_plane_distance
    
    first_vp_solver = _intersect_ui_segments(solve_input.vp1_segments, dimensions, principal_point)
    first_camera_direction = solver_point_to_camera_ray(first_vp_solver, focal_plane_distance)
    first_axis = _parse_axis(solve_input.first_axis)
    
    # Use VP2 segments to fit a horizon line
    if not solve_input.vp2_segments:
        raise GeometryError("Horizon line segments (VP2) must be provided for 1VP mode.")
    
    # Fit a line ax + by + c = 0 to all points in vp2_segments
    points = []
    for seg in solve_input.vp2_segments:
        points.append(ui_to_solver(seg.start, dimensions, principal_point))
        points.append(ui_to_solver(seg.end, dimensions, principal_point))
    
    # Least squares line fit for the horizon
    # Normal to ground plane in camera space: (a, b, c / focal_plane_distance)
    # For now, assume horizon is roughly horizontal and use a simpler approach:
    # the cross product of rays to two horizon points gives the normal.
    if len(points) < 2:
        raise GeometryError("Need at least two points for the horizon line.")
    
    r_h1 = solver_point_to_camera_ray(points[0], focal_plane_distance)
    r_h2 = solver_point_to_camera_ray(points[1], focal_plane_distance)
    world_up_camera = r_h1.cross(r_h2).normalized()
    
    # We have first_camera_direction (axis A) and world_up_camera (Y axis in world if ground axes are used)
    # Let's construct the rotation matrix.
    # Note: If ground axes are +X, +Z, then world-up is +Y.
    # We need to find which world axis corresponds to the horizon normal.
    # Usually world +Y is up.
    
    # Constructing columns of R (camera-to-world rotation)
    # R = [X_c, Y_c, Z_c] where X_c is camera X in world coordinates?
    # No, our _camera_to_world_rotation takes columns as world axes in camera coordinates.
    
    # We have axis_A_camera = first_camera_direction
    # We have world_up_camera = world_up_camera
    
    # For now, let's assume world-up is always +Y.
    world_up_axis = (1, 1.0) # +Y
    
    # Target: columns[0] = world X in camera, columns[1] = world Y, columns[2] = world Z
    
    primary_axis_idx = first_axis[0]
    primary_axis_dir = first_camera_direction * first_axis[1]
    
    columns = [Vector3D(0, 0, 0) for _ in range(3)]
    columns[primary_axis_idx] = primary_axis_dir
    
    if primary_axis_idx == 1:
        # Primary axis is Y. Horizon gives XZ plane orientation.
        # Use the first point of horizon to define a temporary X-ish axis.
        # Points on horizon are in XZ plane, so they are perpendicular to Y.
        r_h1 = solver_point_to_camera_ray(points[0], focal_plane_distance)
        columns[0] = r_h1.normalized()
        columns[2] = columns[0].cross(columns[1]).normalized()
    else:
        columns[1] = world_up_camera
        # Orthogonalize Y to primary axis if needed
        dot = columns[1].dot(columns[primary_axis_idx])
        columns[1] = (columns[1] - columns[primary_axis_idx] * dot).normalized()
        
        # Recover the third axis using cross product
        # X cross Y = Z, Y cross Z = X, Z cross X = Y
        if primary_axis_idx == 0: # X, Y -> Z
            columns[2] = columns[0].cross(columns[1])
        else: # Z, Y -> X (since Y cross Z = X, then Z cross Y = -X, but we want X)
            columns[0] = columns[1].cross(columns[2])

    camera_to_world_rotation = _camera_to_world_rotation(tuple(columns)) # type: ignore
    
    # Rest of the logic (origin, position, result)
    origin_solver = ui_to_solver(solve_input.origin, dimensions, principal_point)
    origin_camera_ray = solver_point_to_camera_ray(origin_solver, focal_plane_distance)
    origin_world_ray = camera_to_world_rotation.transform_direction(origin_camera_ray)
    camera_position = origin_world_ray * -solve_input.camera_distance
    
    reference_distance: ReferenceDistanceCalibration | None = None
    if solve_input.reference_distance is not None:
        reference_distance = calibrate_reference_distance(
            solve_input.reference_distance,
            dimensions=dimensions,
            principal_point=principal_point,
            focal_plane_distance=focal_plane_distance,
            camera_to_world_rotation=camera_to_world_rotation,
            camera_position=camera_position,
        )
        camera_position = camera_position * reference_distance.scale_factor
        warnings.extend(reference_distance.warnings)

    camera_to_world_matrix = _with_translation(camera_to_world_rotation, camera_position)
    world_to_camera_matrix = camera_to_world_matrix.inverse()
    
    sensor_height_mm = solve_input.sensor_width_mm * dimensions.height_relative_to_width
    focal_length_mm = focal_plane_distance * solve_input.sensor_width_mm

    k_matrix = Matrix4.from_rows((
        (-focal_plane_distance, 0.0, 0.0, 0.0),
        (0.0, -focal_plane_distance, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0, 0.0)
    ))
    projection_matrix = k_matrix @ world_to_camera_matrix

    return SolveResult(
        camera_to_world_matrix=camera_to_world_matrix,
        world_to_camera_matrix=world_to_camera_matrix,
        projection_matrix=projection_matrix,
        camera_position=camera_position,
        relative_focal_length=relative_focal_length,
        focal_length_mm=focal_length_mm,
        horizontal_fov_radians=2.0 * atan(0.5 * solve_input.sensor_width_mm / focal_length_mm),
        vertical_fov_radians=2.0 * atan(0.5 * sensor_height_mm / focal_length_mm),
        image_dimensions=dimensions,
        sensor_width_mm=solve_input.sensor_width_mm,
        sensor_height_mm=sensor_height_mm,
        principal_point_ui=principal_point,
        origin_ui=solve_input.origin,
        vanishing_points_ui=(
            solver_to_ui(first_vp_solver, dimensions, principal_point),
            None,
            None,
        ),
        vanishing_points_solver=(first_vp_solver, None, None),
        reference_distance=reference_distance,
        warnings=tuple(warnings),
        errors=(),
    )


def _solve_principal_point_3vp(
    vp1_segments: tuple[Segment2D, ...],
    vp2_segments: tuple[Segment2D, ...],
    vp3_segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
) -> Point2D:
    # Use image center as temporary principal point to find VPs in a stable solver space
    center = DEFAULT_PRINCIPAL_POINT
    v1 = _intersect_ui_segments(vp1_segments, dimensions, center)
    v2 = _intersect_ui_segments(vp2_segments, dimensions, center)
    v3 = _intersect_ui_segments(vp3_segments, dimensions, center)

    # Orthocenter O(x,y) equations:
    # (x - x1)(x2 - x3) + (y - y1)(y2 - y3) = 0
    # (x - x2)(x1 - x3) + (y - y2)(y1 - y3) = 0
    # 
    # Rearranging into Ax = B:
    # x(x2 - x3) + y(y2 - y3) = x1(x2 - x3) + y1(y2 - y3)
    # x(x1 - x3) + y(y1 - y3) = x2(x1 - x3) + y2(y1 - y3)
    
    a1, b1 = v2.x - v3.x, v2.y - v3.y
    c1 = v1.x * a1 + v1.y * b1
    
    a2, b2 = v1.x - v3.x, v1.y - v3.y
    c2 = v2.x * a2 + v2.y * b2
    
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        raise GeometryError("Could not calculate Principal Point from 3VP (vanishing points are collinear).")
    
    ox = (c1 * b2 - c2 * b1) / det
    oy = (a1 * c2 - a2 * c1) / det
    
    # O is in solver coordinates relative to image center.
    # Convert O back to UI coordinates.
    return solver_to_ui(Point2D(ox, oy), dimensions, center)


def _validate_scalar(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise GeometryError(f"{name} must be a finite positive value.")


def _parse_axis(axis: str) -> tuple[int, float]:
    try:
        return AXIS_VECTORS[axis.upper()]
    except (AttributeError, KeyError) as error:
        raise GeometryError(
            f"Unsupported world axis {axis!r}. Expected one of: {', '.join(AXIS_VECTORS)}."
        ) from error


def _intersect_ui_segments(
    segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
    principal_point: Point2D,
) -> Point2D:
    return line_intersection_least_squares(
        _ui_segment_to_solver(segment, dimensions, principal_point)
        for segment in segments
    )


def _ui_segment_to_solver(
    segment: Segment2D,
    dimensions: ImageDimensions,
    principal_point: Point2D,
) -> Segment2D:
    return Segment2D(
        ui_to_solver(segment.start, dimensions, principal_point),
        ui_to_solver(segment.end, dimensions, principal_point),
    )


def _world_to_camera_columns(
    first_direction: Vector3D,
    first_axis: tuple[int, float],
    second_direction: Vector3D,
    second_axis: tuple[int, float],
) -> tuple[Vector3D, Vector3D, Vector3D]:
    columns: list[Vector3D | None] = [None, None, None]
    columns[first_axis[0]] = first_direction * first_axis[1]
    columns[second_axis[0]] = second_direction * second_axis[1]
    missing_axis = _missing_axis_index(first_axis[0], second_axis[0])

    if missing_axis == 0:
        columns[0] = _require_column(columns[1]).cross(_require_column(columns[2])).normalized()
    elif missing_axis == 1:
        columns[1] = _require_column(columns[2]).cross(_require_column(columns[0])).normalized()
    else:
        columns[2] = _require_column(columns[0]).cross(_require_column(columns[1])).normalized()

    result = tuple(_require_column(column) for column in columns)
    return result  # type: ignore[return-value]


def _missing_axis_index(first_axis: int, second_axis: int) -> int:
    return ({0, 1, 2} - {first_axis, second_axis}).pop()


def _require_column(column: Vector3D | None) -> Vector3D:
    if column is None:
        raise GeometryError("Could not construct camera orientation.")
    return column


def _camera_to_world_rotation(columns: tuple[Vector3D, Vector3D, Vector3D]) -> Matrix4:
    x_axis, y_axis, z_axis = columns
    return Matrix4.from_rows(
        (
            (x_axis.x, x_axis.y, x_axis.z, 0.0),
            (y_axis.x, y_axis.y, y_axis.z, 0.0),
            (z_axis.x, z_axis.y, z_axis.z, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def _with_translation(rotation: Matrix4, translation: Vector3D) -> Matrix4:
    return Matrix4.from_rows(
        (
            (*rotation.rows[0][:3], translation.x),
            (*rotation.rows[1][:3], translation.y),
            (*rotation.rows[2][:3], translation.z),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def _error_result(
    principal_point: Point2D,
    origin: Point2D,
    error: str,
    warnings: list[str],
) -> SolveResult:
    return SolveResult(
        camera_to_world_matrix=None,
        world_to_camera_matrix=None,
        projection_matrix=None,
        camera_position=None,
        relative_focal_length=None,
        focal_length_mm=None,
        horizontal_fov_radians=None,
        vertical_fov_radians=None,
        image_dimensions=None,
        sensor_width_mm=None,
        sensor_height_mm=None,
        principal_point_ui=principal_point,
        origin_ui=origin,
        vanishing_points_ui=(None, None, None),
        vanishing_points_solver=(None, None, None),
        reference_distance=None,
        warnings=tuple(warnings),
        errors=(error,),
    )
