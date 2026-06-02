"""Two-vanishing-point calibration for a pinhole camera.

Input segment handles and the origin are stored in normalized UI coordinates.
The resulting matrices use row-major storage and column-vector transforms.
``camera_to_world_matrix`` maps camera-space points into the solver's world
space. Its translation is arbitrary until a reference distance is supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan, isfinite, sqrt

from scene_solver.core.axes import (
    is_nuke_ground_plane_axes,
    missing_world_axis,
    normalized_world_axis_name,
    parse_world_axis,
    signed_world_axis_name,
    world_axis_index,
)
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
    Vector2D,
    Vector3D,
)
from scene_solver.core.projection import (
    camera_direction_to_solver_point,
    solver_projection_matrix,
    solver_point_to_camera_ray,
)
from scene_solver.core.reference_distance import (
    ReferenceDistanceCalibration,
    ReferenceDistanceInput,
    calibrate_reference_distance,
)


DEFAULT_SENSOR_WIDTH_MM = 36.0
DEFAULT_CAMERA_DISTANCE = 10.0
ARBITRARY_SCALE_WARNING = (
    "Camera distance and scene scale are arbitrary until a reference distance is supplied."
)


@dataclass(frozen=True, slots=True)
class SolveInput:
    image_width: int
    image_height: int
    vp1_segments: tuple[Segment2D, ...]
    vp2_segments: tuple[Segment2D, ...]
    vp3_segments: tuple[Segment2D, ...] = ()
    principal_point: Point2D | None = None
    origin: Point2D = DEFAULT_PRINCIPAL_POINT
    first_axis: str = "X"
    second_axis: str = "Y"
    third_axis: str = "Z"
    sensor_width_mm: float = DEFAULT_SENSOR_WIDTH_MM
    known_focal_length_mm: float | None = None
    flip_world_up: bool = False
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
    principal_point = solve_input.principal_point or DEFAULT_PRINCIPAL_POINT

    try:
        dimensions = ImageDimensions(solve_input.image_width, solve_input.image_height)
        _validate_scalar("Sensor width", solve_input.sensor_width_mm)
        _validate_scalar("Camera distance", solve_input.camera_distance)
        preserve_sign = solve_input.mode == "box"
        first_axis_name = signed_world_axis_name(solve_input.first_axis, preserve_sign=preserve_sign)
        second_axis_name = signed_world_axis_name(solve_input.second_axis, preserve_sign=preserve_sign)

        if solve_input.mode == "1vp":
            return _solve_1vp(solve_input, dimensions)

        if world_axis_index(first_axis_name) == world_axis_index(second_axis_name):
            raise GeometryError("The two vanishing points must map to different world axes.")
        third_axis_letter: str | None = None
        if solve_input.mode == "3vp":
            expected_third_axis_letter = normalized_world_axis_name(missing_world_axis(
                first_axis_name,
                second_axis_name,
            ))
            third_axis_letter = normalized_world_axis_name(solve_input.third_axis)
            if third_axis_letter != expected_third_axis_letter:
                raise GeometryError(
                    f"The third VP axis must be {expected_third_axis_letter} "
                    "for a right-handed Nuke coordinate system."
                )

        if solve_input.principal_point is None:
            if solve_input.vp3_segments:
                principal_point, third_vp_at_infinity = _solve_principal_point_3vp(
                    solve_input.vp1_segments,
                    solve_input.vp2_segments,
                    solve_input.vp3_segments,
                    dimensions,
                )
                if third_vp_at_infinity:
                    warnings.append(
                        "The third VP is at infinity; auto principal point is partially "
                        "constrained. Assuming image center for its unresolved component."
                    )
            else:
                principal_point = DEFAULT_PRINCIPAL_POINT

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
        # Box mode keeps the signed names derived above (preserve_sign=True);
        # line modes re-derive the orientation from the drawn segment direction.
        if solve_input.mode != "box":
            first_axis_name = _axis_oriented_by_segments(
                solve_input.first_axis,
                solve_input.vp1_segments,
                solver_to_ui(first_vp_solver, dimensions, principal_point),
            )
            second_axis_name = _axis_oriented_by_segments(
                solve_input.second_axis,
                solve_input.vp2_segments,
                solver_to_ui(second_vp_solver, dimensions, principal_point),
            )
        first_axis = parse_world_axis(first_axis_name)
        second_axis = parse_world_axis(second_axis_name)

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
        if _reflects_below_nuke_floor(
            solve_input.mode,
            first_axis,
            second_axis,
            _camera_to_world_rotation(columns),
            dimensions=dimensions,
            principal_point=principal_point,
            focal_plane_distance=focal_plane_distance,
            origin=solve_input.origin,
        ):
            # A vanishing point is identical for an axis and its reverse, so one
            # mis-drawn ground line mirrors the camera through the X/Z floor.
            # Flipping a single ground axis sign also flips the cross-product up
            # axis, restoring Nuke's +Y half-space without breaking handedness.
            first_axis = (first_axis[0], -first_axis[1])
            columns = _world_to_camera_columns(
                first_camera_direction,
                first_axis,
                second_camera_direction,
                second_axis,
            )
        camera_to_world_rotation = _camera_to_world_rotation(columns)
        _validate_rotation(camera_to_world_rotation)

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
        if solve_input.mode == "3vp":
            assert third_axis_letter is not None
            _validate_third_axis_segments(
                third_axis_letter,
                solve_input.vp3_segments,
                dimensions=dimensions,
                principal_point=principal_point,
                focal_plane_distance=focal_plane_distance,
                expected_camera_direction=third_camera_direction,
            )

        return _finalize_result(
            solve_input,
            dimensions=dimensions,
            principal_point=principal_point,
            focal_plane_distance=focal_plane_distance,
            camera_to_world_rotation=camera_to_world_rotation,
            vanishing_points_ui=(
                solver_to_ui(first_vp_solver, dimensions, principal_point),
                solver_to_ui(second_vp_solver, dimensions, principal_point),
                third_vp_ui,
            ),
            vanishing_points_solver=(first_vp_solver, second_vp_solver, third_vp_solver),
            warnings=warnings,
        )
    except (GeometryError, ValueError) as error:
        return _error_result(principal_point, solve_input.origin, str(error), warnings)


def _solve_1vp(solve_input: SolveInput, dimensions: ImageDimensions) -> SolveResult:
    """Calibrate from one vanishing point and a known focal length + horizon."""

    principal_point = solve_input.principal_point or DEFAULT_PRINCIPAL_POINT
    warnings: list[str] = []

    if solve_input.known_focal_length_mm is None:
        raise GeometryError("Focal length must be provided for 1VP mode.")
    _validate_scalar("Focal length", solve_input.known_focal_length_mm)
    focal_plane_distance = solve_input.known_focal_length_mm / solve_input.sensor_width_mm
    
    first_vp_solver = _intersect_ui_segments(solve_input.vp1_segments, dimensions, principal_point)
    first_camera_direction = solver_point_to_camera_ray(first_vp_solver, focal_plane_distance)
    first_axis_name = _axis_oriented_by_segments(
        solve_input.first_axis,
        solve_input.vp1_segments,
        solver_to_ui(first_vp_solver, dimensions, principal_point),
    )
    first_axis = parse_world_axis(first_axis_name)
    if first_axis[0] == 1:
        raise GeometryError(
            "1VP mode requires an X or Z vanishing-point axis; "
            "Y alone does not determine Nuke yaw."
        )
    
    # Use VP2 segments to fit a horizon line.
    if not solve_input.vp2_segments:
        raise GeometryError("Horizon line segments (VP2) must be provided for 1VP mode.")
    points = [
        ui_to_solver(point, dimensions, principal_point)
        for segment in solve_input.vp2_segments
        for point in (segment.start, segment.end)
    ]
    if len(points) < 2:
        raise GeometryError("Need at least two points for the horizon line.")
    r_h1 = solver_point_to_camera_ray(points[0], focal_plane_distance)
    r_h2 = solver_point_to_camera_ray(points[1], focal_plane_distance)
    camera_to_world_rotation = _one_vp_camera_to_world_rotation(
        first_camera_direction,
        first_axis,
        r_h1,
        r_h2,
        flip_world_up=solve_input.flip_world_up,
    )
    return _finalize_result(
        solve_input,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
        vanishing_points_ui=(
            solver_to_ui(first_vp_solver, dimensions, principal_point),
            None,
            None,
        ),
        vanishing_points_solver=(first_vp_solver, None, None),
        warnings=warnings,
        warn_arbitrary_scale=False,
    )


def _one_vp_camera_to_world_rotation(
    first_camera_direction: Vector3D,
    first_axis: tuple[int, float],
    first_horizon_ray: Vector3D,
    second_horizon_ray: Vector3D,
    *,
    flip_world_up: bool = False,
) -> Matrix4:
    """Recover rotation from one axis vanishing point and the ground horizon."""

    world_up_camera = first_horizon_ray.cross(second_horizon_ray).normalized()
    if world_up_camera.y < 0.0:
        world_up_camera = world_up_camera * -1.0
    if flip_world_up:
        world_up_camera = world_up_camera * -1.0
    primary_axis_idx = first_axis[0]
    primary_axis_dir = first_camera_direction * first_axis[1]
    columns = [Vector3D(0, 0, 0) for _ in range(3)]
    columns[primary_axis_idx] = primary_axis_dir

    columns[1] = world_up_camera
    dot = columns[1].dot(columns[primary_axis_idx])
    columns[1] = (columns[1] - columns[primary_axis_idx] * dot).normalized()
    if primary_axis_idx == 0:
        columns[2] = columns[0].cross(columns[1])
    else:
        columns[0] = columns[1].cross(columns[2])
    return _camera_to_world_rotation((columns[0], columns[1], columns[2]))


def _solve_principal_point_3vp(
    vp1_segments: tuple[Segment2D, ...],
    vp2_segments: tuple[Segment2D, ...],
    vp3_segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
) -> tuple[Point2D, bool]:
    # Use image center as temporary principal point to find VPs in a stable solver space
    center = DEFAULT_PRINCIPAL_POINT
    v1 = _intersect_ui_segments(vp1_segments, dimensions, center)
    v2 = _intersect_ui_segments(vp2_segments, dimensions, center)
    v3 = _optional_intersect_ui_segments(vp3_segments, dimensions, center)
    if v3 is None:
        heading = _average_ui_segment_heading_solver(vp3_segments, dimensions, center)
        heading_offset = 0.5 * (
            v1.x * heading.x
            + v1.y * heading.y
            + v2.x * heading.x
            + v2.y * heading.y
        )
        partial_principal_point = Point2D(
            heading.x * heading_offset,
            heading.y * heading_offset,
        )
        return solver_to_ui(partial_principal_point, dimensions, center), True

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
    return solver_to_ui(Point2D(ox, oy), dimensions, center), False


def _validate_scalar(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0.0:
        raise GeometryError(f"{name} must be a finite positive value.")


def _axis_oriented_by_segments(
    axis: str,
    segments: tuple[Segment2D, ...],
    vanishing_point: Point2D,
) -> str:
    """Resolve the signed world axis from consistent directed VP lines."""
    letter = normalized_world_axis_name(axis)
    orientation: bool | None = None
    for segment in segments:
        try:
            direction = segment.direction().normalized()
            to_vanishing_point = (vanishing_point - segment.start).normalized()
        except GeometryError as error:
            raise GeometryError(f"The {letter} VP lines must have a visible direction.") from error
        score = direction.dot(to_vanishing_point)
        if abs(score) <= DEFAULT_TOLERANCE:
            raise GeometryError(
                f"The {letter} VP lines must have a clear direction."
            )
        points_toward_vp = score > 0.0
        if orientation is not None and points_toward_vp != orientation:
            raise GeometryError(
                f"The {letter} VP lines must use a consistent direction."
            )
        orientation = points_toward_vp
    if orientation is None:
        raise GeometryError(f"The {letter} VP lines must be marked.")
    return f"{'+' if orientation else '-'}{letter}"


def _validate_third_axis_segments(
    axis: str,
    segments: tuple[Segment2D, ...],
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    expected_camera_direction: Vector3D,
) -> None:
    """Validate a finite or infinite third VP against the solved Nuke frame."""
    _optional_intersect_ui_segments(segments, dimensions, principal_point)
    letter = normalized_world_axis_name(axis)
    expected_vanishing_point: Point2D | None
    try:
        expected_vanishing_point = solver_to_ui(
            camera_direction_to_solver_point(expected_camera_direction, focal_plane_distance),
            dimensions,
            principal_point,
        )
    except GeometryError:
        expected_vanishing_point = None
        try:
            expected_heading = Vector2D(
                expected_camera_direction.x,
                -expected_camera_direction.y / dimensions.height_relative_to_width,
            ).normalized()
        except GeometryError as error:
            raise GeometryError(f"Could not resolve the projected {letter} axis direction.") from error

    for segment in segments:
        try:
            heading = segment.direction().normalized()
            if expected_vanishing_point is None:
                desired_heading = expected_heading
            else:
                desired_heading = (expected_vanishing_point - segment.start).normalized()
                if expected_camera_direction.z > 0.0:
                    desired_heading = desired_heading * -1.0
        except GeometryError as error:
            raise GeometryError(f"The {letter} VP lines must have a visible direction.") from error

        alignment = heading.dot(desired_heading)
        if alignment <= DEFAULT_TOLERANCE:
            raise GeometryError(
                f"The {letter} VP lines point opposite to the solved Nuke axis direction."
            )
        if alignment < 0.995:
            raise GeometryError(
                f"The {letter} VP lines do not align with the solved Nuke axis direction."
            )


def _intersect_ui_segments(
    segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
    principal_point: Point2D,
) -> Point2D:
    return line_intersection_least_squares(
        _ui_segment_to_solver(segment, dimensions, principal_point)
        for segment in segments
    )


def _optional_intersect_ui_segments(
    segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
    principal_point: Point2D,
) -> Point2D | None:
    """Return a finite VP, or None when valid marked lines meet at infinity."""
    if len(segments) < 2:
        raise GeometryError("At least two line segments are required for intersection.")
    if any(segment.length() <= DEFAULT_TOLERANCE for segment in segments):
        raise GeometryError("Cannot intersect a line defined by a zero-length segment.")
    try:
        return _intersect_ui_segments(segments, dimensions, principal_point)
    except GeometryError:
        return None


def _average_ui_segment_heading_solver(
    segments: tuple[Segment2D, ...],
    dimensions: ImageDimensions,
    principal_point: Point2D,
) -> Vector2D:
    """Average an unoriented family of parallel UI lines in solver space."""
    reference_heading: Vector2D | None = None
    heading_sum = Vector2D(0.0, 0.0)
    for segment in segments:
        heading = _ui_segment_to_solver(segment, dimensions, principal_point).direction().normalized()
        if reference_heading is None:
            reference_heading = heading
        elif heading.dot(reference_heading) < 0.0:
            heading = heading * -1.0
        heading_sum = heading_sum + heading
    try:
        return heading_sum.normalized()
    except GeometryError as error:
        raise GeometryError("Could not resolve the third VP direction at infinity.") from error


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


def _reflects_below_nuke_floor(
    mode: str,
    first_axis: tuple[int, float],
    second_axis: tuple[int, float],
    camera_to_world_rotation: Matrix4,
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    origin: Point2D,
) -> bool:
    """Detect the floor-reflected line solve for Nuke's X/Z ground workflow.

    Mirrors box mode's ``_is_reflected_below_nuke_ground_plane``: only the X/Z
    ground frame has a Y up axis to canonicalize, and box mode runs its own
    correction, so this stays scoped to the line modes.
    """
    if mode == "box":
        return False
    if not is_nuke_ground_plane_axes(first_axis[0], second_axis[0]):
        return False
    origin_solver = ui_to_solver(origin, dimensions, principal_point)
    origin_world_ray = camera_to_world_rotation.transform_direction(
        solver_point_to_camera_ray(origin_solver, focal_plane_distance)
    )
    # camera_position == origin_world_ray * -camera_distance, so a +Y origin ray
    # places the camera below the floor regardless of the (positive) scale.
    return origin_world_ray.y > DEFAULT_TOLERANCE


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


def _validate_rotation(rotation: Matrix4) -> None:
    if abs(rotation.determinant() - 1.0) > 1e-7:
        raise GeometryError("Recovered camera rotation has an invalid determinant.")


def _camera_position(
    solve_input: SolveInput,
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
    warnings: list[str],
    warn_arbitrary_scale: bool,
) -> tuple[Vector3D, ReferenceDistanceCalibration | None]:
    origin_solver = ui_to_solver(solve_input.origin, dimensions, principal_point)
    origin_camera_ray = solver_point_to_camera_ray(origin_solver, focal_plane_distance)
    origin_world_ray = camera_to_world_rotation.transform_direction(origin_camera_ray)
    camera_position = origin_world_ray * -solve_input.camera_distance
    if solve_input.reference_distance is None:
        if warn_arbitrary_scale:
            warnings.append(ARBITRARY_SCALE_WARNING)
        return camera_position, None

    reference_distance = calibrate_reference_distance(
        solve_input.reference_distance,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
        camera_position=camera_position,
    )
    warnings.extend(reference_distance.warnings)
    return camera_position * reference_distance.scale_factor, reference_distance


def _finalize_result(
    solve_input: SolveInput,
    *,
    dimensions: ImageDimensions,
    principal_point: Point2D,
    focal_plane_distance: float,
    camera_to_world_rotation: Matrix4,
    vanishing_points_ui: tuple[Point2D | None, Point2D | None, Point2D | None],
    vanishing_points_solver: tuple[Point2D | None, Point2D | None, Point2D | None],
    warnings: list[str],
    warn_arbitrary_scale: bool = True,
) -> SolveResult:
    camera_position, reference_distance = _camera_position(
        solve_input,
        dimensions=dimensions,
        principal_point=principal_point,
        focal_plane_distance=focal_plane_distance,
        camera_to_world_rotation=camera_to_world_rotation,
        warnings=warnings,
        warn_arbitrary_scale=warn_arbitrary_scale,
    )
    camera_to_world_matrix = _with_translation(camera_to_world_rotation, camera_position)
    world_to_camera_matrix = camera_to_world_matrix.inverse()
    sensor_height_mm = solve_input.sensor_width_mm * dimensions.height_relative_to_width
    focal_length_mm = focal_plane_distance * solve_input.sensor_width_mm
    return SolveResult(
        camera_to_world_matrix=camera_to_world_matrix,
        world_to_camera_matrix=world_to_camera_matrix,
        projection_matrix=solver_projection_matrix(focal_plane_distance, world_to_camera_matrix),
        camera_position=camera_position,
        relative_focal_length=2.0 * focal_plane_distance,
        focal_length_mm=focal_length_mm,
        horizontal_fov_radians=2.0 * atan(0.5 * solve_input.sensor_width_mm / focal_length_mm),
        vertical_fov_radians=2.0 * atan(0.5 * sensor_height_mm / focal_length_mm),
        image_dimensions=dimensions,
        sensor_width_mm=solve_input.sensor_width_mm,
        sensor_height_mm=sensor_height_mm,
        principal_point_ui=principal_point,
        origin_ui=solve_input.origin,
        vanishing_points_ui=vanishing_points_ui,
        vanishing_points_solver=vanishing_points_solver,
        reference_distance=reference_distance,
        warnings=tuple(warnings),
        errors=(),
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
