"""Integration test for the Lens Solver Camera2 adapter.

Run with:

    Nuke15.1.exe --safe -t -V 0 nuke_tests/test_camera2_projection.py
"""

from __future__ import annotations

from math import isclose
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nuke
from nukescripts import snap3d

from lens_solver.core import (
    ImageDimensions,
    Point2D,
    Segment2D,
    SolveInput,
    Vector3D,
    solve_2vp,
    solver_to_ui,
)
from lens_solver.nuke_integration import core_camera_to_nuke_matrix, create_camera


DIMENSIONS = ImageDimensions(1920, 1080)
PRINCIPAL_POINT = Point2D(0.5, 0.5)
ORIGIN = Point2D(0.63, 0.34)
FOCAL_PLANE_DISTANCE = 0.9
CAMERA_X = Vector3D(-0.8, 0.0, -0.6)
CAMERA_Y = Vector3D(0.36, -0.8, -0.48)


def project_direction(direction: Vector3D) -> Point2D:
    return Point2D(
        -FOCAL_PLANE_DISTANCE * direction.x / direction.z,
        -FOCAL_PLANE_DISTANCE * direction.y / direction.z,
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


def flatten(matrix) -> tuple[float, ...]:
    return tuple(value for row in matrix.rows for value in row)


def assert_close(actual: float, expected: float, tolerance: float = 1e-5) -> None:
    if not isclose(actual, expected, abs_tol=tolerance):
        raise AssertionError(f"{actual!r} != {expected!r}")


def assert_point_close(actual: Point2D, expected: Point2D) -> None:
    assert_close(actual.x, expected.x)
    assert_close(actual.y, expected.y)


def nuke_projection_to_ui(camera, world_point: Vector3D) -> Point2D:
    projected = snap3d.projectPoint(camera, (world_point.x, world_point.y, world_point.z))
    return Point2D(projected.x / DIMENSIONS.width, 1.0 - projected.y / DIMENSIONS.height)


def core_projection_to_ui(result, world_point: Vector3D) -> Point2D:
    assert result.world_to_camera_matrix is not None
    camera_point = result.world_to_camera_matrix.transform_point(world_point)
    solver_point = Point2D(
        -FOCAL_PLANE_DISTANCE * camera_point.x / camera_point.z,
        -FOCAL_PLANE_DISTANCE * camera_point.y / camera_point.z,
    )
    return solver_to_ui(solver_point, DIMENSIONS, PRINCIPAL_POINT)


def main() -> None:
    nuke.root()["format"].setValue("HD_1080")
    first_vp_ui = solver_to_ui(project_direction(CAMERA_X), DIMENSIONS, PRINCIPAL_POINT)
    second_vp_ui = solver_to_ui(project_direction(CAMERA_Y), DIMENSIONS, PRINCIPAL_POINT)
    result = solve_2vp(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=segments_for_vp(first_vp_ui),
            vp2_segments=segments_for_vp(second_vp_ui),
            principal_point=PRINCIPAL_POINT,
            origin=ORIGIN,
        )
    )
    if not result.ok:
        raise AssertionError(result.errors)

    camera = create_camera(result, name="LensSolverProjectionTest")
    assert camera["useMatrix"].value() is True
    assert_close(camera["focal"].value(), 32.4)
    assert_close(camera["haperture"].value(), 36.0)
    assert_close(camera["vaperture"].value(), 20.25)
    assert_close(camera["win_translate"].value(0), 0.0)
    assert_close(camera["win_translate"].value(1), 0.0)

    assert result.camera_to_world_matrix is not None
    expected_world_matrix = flatten(core_camera_to_nuke_matrix(result.camera_to_world_matrix))
    actual_world_matrix = tuple(
        camera["world_matrix"].valueAt(nuke.frame(), index) for index in range(16)
    )
    for actual, expected in zip(actual_world_matrix, expected_world_matrix):
        assert_close(actual, expected)

    core_camera_points = (
        Vector3D(0.0, 0.0, -FOCAL_PLANE_DISTANCE),
        Vector3D(0.2, -0.1, -1.4),
        Vector3D(-0.35, 0.25, -2.2),
    )
    world_points = [Vector3D(0.0, 0.0, 0.0)]
    world_points.extend(
        result.camera_to_world_matrix.transform_point(point) for point in core_camera_points
    )
    for world_point in world_points:
        assert_point_close(
            nuke_projection_to_ui(camera, world_point),
            core_projection_to_ui(result, world_point),
        )

    assert_point_close(nuke_projection_to_ui(camera, Vector3D(0.0, 0.0, 0.0)), ORIGIN)
    print("camera2-projection-test passed", flush=True)
    nuke.scriptClear()


if __name__ == "__main__":
    main()
