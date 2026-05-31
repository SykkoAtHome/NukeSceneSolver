from math import isclose

from lens_solver.core import (
    ImageDimensions,
    Point2D,
    Segment2D,
    SolveInput,
    Vector3D,
    reconstruct_match_box,
    solve_2vp,
    solver_to_ui,
)


DIMENSIONS = ImageDimensions(1920, 1080)
FOCAL_PLANE_DISTANCE = 0.9
CAMERA_X = Vector3D(-0.8, 0.0, -0.6)
CAMERA_Y = Vector3D(0.36, -0.8, -0.48)
CAMERA_Z = Vector3D(-0.48, -0.6, 0.64)


def project_direction(direction: Vector3D) -> Point2D:
    return Point2D(
        -FOCAL_PLANE_DISTANCE * direction.x / direction.z,
        -FOCAL_PLANE_DISTANCE * direction.y / direction.z,
    )


def segments_for(vanishing_point: Point2D) -> tuple[Segment2D, Segment2D]:
    return (
        Segment2D(Point2D(0.1, 0.2), vanishing_point),
        Segment2D(Point2D(0.8, 0.7), vanishing_point),
    )


def assert_vector_close(actual: Vector3D, expected: Vector3D) -> None:
    assert isclose(actual.x, expected.x, abs_tol=1e-8)
    assert isclose(actual.y, expected.y, abs_tol=1e-8)
    assert isclose(actual.z, expected.z, abs_tol=1e-8)


def assert_point_close(actual: Point2D, expected: Point2D) -> None:
    assert isclose(actual.x, expected.x, abs_tol=1e-8)
    assert isclose(actual.y, expected.y, abs_tol=1e-8)


def match_box_corners(center: Vector3D, size: Vector3D) -> dict[str, Vector3D]:
    low = center - size * 0.5
    high = center + size * 0.5
    return {
        "box_v000": Vector3D(low.x, low.y, low.z),
        "box_v100": Vector3D(high.x, low.y, low.z),
        "box_v010": Vector3D(low.x, high.y, low.z),
        "box_v110": Vector3D(high.x, high.y, low.z),
        "box_v001": Vector3D(low.x, low.y, high.z),
        "box_v101": Vector3D(high.x, low.y, high.z),
        "box_v011": Vector3D(low.x, high.y, high.z),
        "box_v111": Vector3D(high.x, high.y, high.z),
    }


def test_reconstruct_match_box_recovers_axis_aligned_dimensions() -> None:
    result = solve_2vp(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=segments_for(solver_to_ui(project_direction(CAMERA_X), DIMENSIONS)),
            vp2_segments=segments_for(solver_to_ui(project_direction(CAMERA_Y), DIMENSIONS)),
            origin=Point2D(0.5, 0.5),
        )
    )
    assert result.ok
    assert result.world_to_camera_matrix is not None

    def project_world_point(point: Vector3D) -> Point2D:
        camera_point = result.world_to_camera_matrix.transform_point(point)
        return solver_to_ui(project_direction(camera_point), DIMENSIONS)

    corners = {
        "box_v000": project_world_point(Vector3D(-2.0, -1.0, 0.0)),
        "box_v100": project_world_point(Vector3D(2.0, -1.0, 0.0)),
        "box_v010": project_world_point(Vector3D(-2.0, 2.0, 0.0)),
        "box_v110": project_world_point(Vector3D(2.0, 2.0, 0.0)),
        "box_v001": project_world_point(Vector3D(-2.0, -1.0, 5.0)),
        "box_v101": project_world_point(Vector3D(2.0, -1.0, 5.0)),
        "box_v011": project_world_point(Vector3D(-2.0, 2.0, 5.0)),
        "box_v111": project_world_point(Vector3D(2.0, 2.0, 5.0)),
    }

    match_box = reconstruct_match_box(result, corners, "+X", "+Y")

    assert isclose(match_box.size.x / match_box.size.y, 4.0 / 3.0, abs_tol=1e-8)
    assert isclose(match_box.size.z / match_box.size.y, 5.0 / 3.0, abs_tol=1e-8)
    for name, point in match_box_corners(match_box.center, match_box.size).items():
        assert_point_close(project_world_point(point), corners[name])


def test_reconstruct_match_box_uses_positive_y_as_up_for_nuke_ground_plane() -> None:
    result = solve_2vp(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=segments_for(solver_to_ui(project_direction(CAMERA_X), DIMENSIONS)),
            vp2_segments=segments_for(solver_to_ui(project_direction(CAMERA_Z), DIMENSIONS)),
            origin=Point2D(0.5, 0.5),
            first_axis="+X",
            second_axis="+Z",
        )
    )
    assert result.ok
    assert result.world_to_camera_matrix is not None

    def project_world_point(point: Vector3D) -> Point2D:
        camera_point = result.world_to_camera_matrix.transform_point(point)
        return solver_to_ui(project_direction(camera_point), DIMENSIONS)

    corners = {
        "box_v000": project_world_point(Vector3D(-2.0, 0.0, -1.0)),
        "box_v100": project_world_point(Vector3D(2.0, 0.0, -1.0)),
        "box_v010": project_world_point(Vector3D(-2.0, 0.0, 2.0)),
        "box_v110": project_world_point(Vector3D(2.0, 0.0, 2.0)),
        "box_v001": project_world_point(Vector3D(-2.0, 5.0, -1.0)),
        "box_v101": project_world_point(Vector3D(2.0, 5.0, -1.0)),
        "box_v011": project_world_point(Vector3D(-2.0, 5.0, 2.0)),
        "box_v111": project_world_point(Vector3D(2.0, 5.0, 2.0)),
    }

    match_box = reconstruct_match_box(result, corners, "+X", "+Z")

    assert isclose(match_box.size.x / match_box.size.z, 4.0 / 3.0, abs_tol=1e-8)
    assert isclose(match_box.size.y / match_box.size.z, 5.0 / 3.0, abs_tol=1e-8)
    world_corners = match_box_corners(match_box.center, match_box.size)
    nuke_mapping = {
        "box_v000": "box_v000",
        "box_v100": "box_v100",
        "box_v010": "box_v001",
        "box_v110": "box_v101",
        "box_v001": "box_v010",
        "box_v101": "box_v110",
        "box_v011": "box_v011",
        "box_v111": "box_v111",
    }
    for source_name, world_name in nuke_mapping.items():
        assert_point_close(project_world_point(world_corners[world_name]), corners[source_name])
