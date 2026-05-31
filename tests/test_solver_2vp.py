from dataclasses import replace
from math import atan, isclose, sqrt

import pytest

from lens_solver.core.coordinates import ImageDimensions, solver_to_ui
from lens_solver.core.models import Point2D, Segment2D, Vector3D
from lens_solver.core.reference_distance import ReferenceDistanceInput
from lens_solver.core.solver_2vp import SolveInput, solve_2vp


def assert_close(actual: float | None, expected: float, tolerance: float = 1e-9) -> None:
    assert actual is not None
    assert isclose(actual, expected, abs_tol=tolerance)


def assert_point_close(actual: Point2D | None, expected: Point2D, tolerance: float = 1e-9) -> None:
    assert actual is not None
    assert isclose(actual.x, expected.x, abs_tol=tolerance)
    assert isclose(actual.y, expected.y, abs_tol=tolerance)


def assert_vector_close(actual: Vector3D, expected: Vector3D, tolerance: float = 1e-9) -> None:
    assert isclose(actual.x, expected.x, abs_tol=tolerance)
    assert isclose(actual.y, expected.y, abs_tol=tolerance)
    assert isclose(actual.z, expected.z, abs_tol=tolerance)


def project_direction(direction: Vector3D, focal_plane_distance: float) -> Point2D:
    return Point2D(
        -focal_plane_distance * direction.x / direction.z,
        -focal_plane_distance * direction.y / direction.z,
    )


def interpolate(start: Point2D, end: Point2D, amount: float) -> Point2D:
    return Point2D(
        start.x + (end.x - start.x) * amount,
        start.y + (end.y - start.y) * amount,
    )


def segments_for_vp(vanishing_point_ui: Point2D) -> tuple[Segment2D, Segment2D]:
    first_start = Point2D(0.12, 0.23)
    second_start = Point2D(0.79, 0.81)
    return (
        Segment2D(first_start, interpolate(first_start, vanishing_point_ui, 0.41)),
        Segment2D(second_start, interpolate(second_start, vanishing_point_ui, 0.63)),
    )


def make_input(
    dimensions: ImageDimensions,
    first_camera_direction: Vector3D,
    second_camera_direction: Vector3D,
    *,
    focal_plane_distance: float = 0.9,
    principal_point: Point2D = Point2D(0.5, 0.5),
    origin: Point2D = Point2D(0.63, 0.34),
    first_axis: str = "+X",
    second_axis: str = "+Y",
    sensor_width_mm: float = 36.0,
    camera_distance: float = 10.0,
) -> SolveInput:
    first_vp_ui = solver_to_ui(
        project_direction(first_camera_direction, focal_plane_distance),
        dimensions,
        principal_point,
    )
    second_vp_ui = solver_to_ui(
        project_direction(second_camera_direction, focal_plane_distance),
        dimensions,
        principal_point,
    )
    return SolveInput(
        image_width=dimensions.width,
        image_height=dimensions.height,
        vp1_segments=segments_for_vp(first_vp_ui),
        vp2_segments=segments_for_vp(second_vp_ui),
        principal_point=principal_point,
        origin=origin,
        first_axis=first_axis,
        second_axis=second_axis,
        sensor_width_mm=sensor_width_mm,
        camera_distance=camera_distance,
    )


CAMERA_X = Vector3D(-0.8, 0.0, -0.6)
CAMERA_Y = Vector3D(0.36, -0.8, -0.48)
CAMERA_Z = Vector3D(-0.48, -0.6, 0.64)


@pytest.mark.parametrize(
    "dimensions",
    (
        ImageDimensions(1920, 1080),
        ImageDimensions(1080, 1920),
    ),
)
def test_solver_recovers_focal_length_rotation_and_origin(dimensions: ImageDimensions) -> None:
    solve_input = make_input(dimensions, CAMERA_X, CAMERA_Y)

    result = solve_2vp(solve_input)

    assert result.ok
    assert result.errors == ()
    assert result.world_to_camera_matrix is not None
    assert result.camera_to_world_matrix is not None
    assert result.camera_position is not None
    assert_close(result.relative_focal_length, 1.8)
    assert_close(result.focal_length_mm, 32.4)
    assert_close(result.horizontal_fov_radians, 2.0 * atan(0.5 / 0.9))
    assert_close(
        result.vertical_fov_radians,
        2.0 * atan(0.5 * dimensions.height_relative_to_width / 0.9),
    )
    assert_vector_close(
        result.world_to_camera_matrix.transform_direction(Vector3D(1.0, 0.0, 0.0)),
        CAMERA_X,
    )
    assert_vector_close(
        result.world_to_camera_matrix.transform_direction(Vector3D(0.0, 1.0, 0.0)),
        CAMERA_Y,
    )
    assert_vector_close(
        result.world_to_camera_matrix.transform_direction(Vector3D(0.0, 0.0, 1.0)),
        CAMERA_Z,
    )
    assert_close(result.camera_position.length(), 10.0)

    origin_camera = result.world_to_camera_matrix.transform_point(Vector3D(0.0, 0.0, 0.0))
    origin_solver = project_direction(origin_camera, 0.9)
    origin_ui = solver_to_ui(origin_solver, dimensions)
    assert_point_close(origin_ui, solve_input.origin)
    assert any("scale are arbitrary" in warning for warning in result.warnings)


def test_solver_supports_custom_principal_point() -> None:
    dimensions = ImageDimensions(2048, 2048)
    principal_point = Point2D(0.42, 0.61)
    solve_input = make_input(
        dimensions,
        CAMERA_X,
        CAMERA_Y,
        principal_point=principal_point,
    )

    result = solve_2vp(solve_input)

    assert result.ok
    assert result.principal_point_ui == principal_point
    assert_close(result.relative_focal_length, 1.8)
    assert_point_close(result.vanishing_points_solver[0], project_direction(CAMERA_X, 0.9))
    assert_point_close(result.vanishing_points_solver[1], project_direction(CAMERA_Y, 0.9))


def test_solver_supports_negative_axis_mapping() -> None:
    negative_world_x = CAMERA_X * -1.0
    solve_input = make_input(
        ImageDimensions(1920, 1080),
        negative_world_x * -1.0,
        CAMERA_Y,
        first_axis="-X",
        second_axis="+Y",
    )

    result = solve_2vp(solve_input)

    assert result.ok
    assert result.world_to_camera_matrix is not None
    assert_vector_close(
        result.world_to_camera_matrix.transform_direction(Vector3D(1.0, 0.0, 0.0)),
        negative_world_x,
    )
    assert_vector_close(
        result.world_to_camera_matrix.transform_direction(Vector3D(0.0, 1.0, 0.0)),
        CAMERA_Y,
    )


def test_solver_scales_camera_translation_from_reference_distance() -> None:
    dimensions = ImageDimensions(1920, 1080)
    solve_input = make_input(dimensions, CAMERA_X, CAMERA_Y)
    arbitrary_result = solve_2vp(solve_input)
    assert arbitrary_result.ok
    assert arbitrary_result.world_to_camera_matrix is not None
    assert arbitrary_result.relative_focal_length is not None

    def project_world_point(point: Vector3D) -> Point2D:
        camera_point = arbitrary_result.world_to_camera_matrix.transform_point(point)
        return solver_to_ui(
            project_direction(camera_point, arbitrary_result.relative_focal_length / 2.0),
            dimensions,
        )

    scaled_result = solve_2vp(
        replace(
            solve_input,
            reference_distance=ReferenceDistanceInput(
                segment_ui=Segment2D(
                    project_world_point(Vector3D(-1.0, 0.0, 0.0)),
                    project_world_point(Vector3D(3.0, 0.0, 0.0)),
                ),
                axis="+X",
                distance=12.0,
            ),
        )
    )

    assert scaled_result.ok
    assert scaled_result.camera_position is not None
    assert scaled_result.reference_distance is not None
    assert_close(scaled_result.reference_distance.measured_distance, 4.0)
    assert_close(scaled_result.reference_distance.scale_factor, 3.0)
    assert_close(scaled_result.camera_position.length(), 30.0)
    assert_vector_close(
        scaled_result.reference_distance.points_world[0],
        Vector3D(-3.0, 0.0, 0.0),
    )
    assert_vector_close(
        scaled_result.reference_distance.points_world[1],
        Vector3D(9.0, 0.0, 0.0),
    )
    assert not any("scale are arbitrary" in warning for warning in scaled_result.warnings)


def test_solver_warns_when_third_vanishing_point_is_at_infinity() -> None:
    diagonal = sqrt(0.5)
    first_direction = Vector3D(diagonal, 0.0, diagonal)
    second_direction = Vector3D(-diagonal, 0.0, diagonal)
    solve_input = make_input(
        ImageDimensions(1920, 1080),
        first_direction,
        second_direction,
    )

    result = solve_2vp(solve_input)

    assert result.ok
    assert result.vanishing_points_ui[2] is None
    assert result.vanishing_points_solver[2] is None
    assert any("at infinity" in warning for warning in result.warnings)


def test_solver_returns_error_for_non_positive_focal_length() -> None:
    dimensions = ImageDimensions(1920, 1080)
    first_vp_ui = solver_to_ui(Point2D(1.0, 0.0), dimensions)
    second_vp_ui = solver_to_ui(Point2D(0.5, 1.0), dimensions)
    solve_input = SolveInput(
        image_width=dimensions.width,
        image_height=dimensions.height,
        vp1_segments=segments_for_vp(first_vp_ui),
        vp2_segments=segments_for_vp(second_vp_ui),
    )

    result = solve_2vp(solve_input)

    assert not result.ok
    assert result.camera_matrix is None
    assert any("positive focal length" in error for error in result.errors)


def test_solver_returns_error_for_parallel_lines() -> None:
    parallel_segments = (
        Segment2D(Point2D(0.0, 0.0), Point2D(1.0, 0.0)),
        Segment2D(Point2D(0.0, 0.5), Point2D(1.0, 0.5)),
    )
    solve_input = SolveInput(
        image_width=1920,
        image_height=1080,
        vp1_segments=parallel_segments,
        vp2_segments=segments_for_vp(Point2D(0.2, 0.3)),
    )

    result = solve_2vp(solve_input)

    assert not result.ok
    assert any("parallel" in error for error in result.errors)


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    (
        ("first_axis", "north", "Unsupported world axis"),
        ("second_axis", "+X", "different world axes"),
        ("sensor_width_mm", 0.0, "Sensor width"),
        ("camera_distance", -1.0, "Camera distance"),
    ),
)
def test_solver_returns_error_for_invalid_options(
    field: str,
    value: str | float,
    expected_error: str,
) -> None:
    options: dict[str, object] = {field: value}
    solve_input = make_input(
        ImageDimensions(1920, 1080),
        CAMERA_X,
        CAMERA_Y,
        **options,  # type: ignore[arg-type]
    )

    result = solve_2vp(solve_input)

    assert not result.ok
    assert any(expected_error in error for error in result.errors)
