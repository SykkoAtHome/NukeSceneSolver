"""Solver/export correctness against real Nuke camera ground truth.

The translate/rotate/focal triples below were copied from rendered Nuke
scripts (see SESSION_HANDOFF.md). We rebuild Nuke's classic camera-to-world
transform (default ``ZXY`` rotation order), project the world cuboid into the
plate, then re-solve and assert the recovered camera matches Nuke. This guards
against any systematic axis flip in the solve or the Camera2 export, which a
closed-loop synthetic test cannot catch.
"""

from __future__ import annotations

from math import cos, isclose, radians, sin

from scene_solver.core.box_match import solve_box_match
from scene_solver.core.coordinates import ImageDimensions, solver_to_ui
from scene_solver.core.models import Matrix4, Point2D, Segment2D, Vector3D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp
from scene_solver.nuke_integration.camera_adapter import CORE_TO_NUKE_CAMERA_BASIS

_DIMS = ImageDimensions(1920, 1080)
_SENSOR_WIDTH_MM = 36.0

# nuke_test_01: ideal unit cube, classic Camera3 SRT, ZXY rotation order.
_TRANSLATE = Vector3D(3.140000105, 1.460000038, 4.684999943)
_ROTATE_DEG = Vector3D(-15.22866726, 33.37726593, -9.817846298)
_FOCAL_MM = 64.0


def _rx(deg: float) -> Matrix4:
    a = radians(deg)
    return Matrix4.from_rows((
        (1.0, 0.0, 0.0, 0.0),
        (0.0, cos(a), -sin(a), 0.0),
        (0.0, sin(a), cos(a), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _ry(deg: float) -> Matrix4:
    a = radians(deg)
    return Matrix4.from_rows((
        (cos(a), 0.0, sin(a), 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (-sin(a), 0.0, cos(a), 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _rz(deg: float) -> Matrix4:
    a = radians(deg)
    return Matrix4.from_rows((
        (cos(a), -sin(a), 0.0, 0.0),
        (sin(a), cos(a), 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


def _nuke_camera_to_world() -> Matrix4:
    return Matrix4.translation(_TRANSLATE) @ _ry(_ROTATE_DEG.y) @ _rx(_ROTATE_DEG.x) @ _rz(_ROTATE_DEG.z)


_M_NUKE = _nuke_camera_to_world()
_M_NUKE_INV = _M_NUKE.inverse()
_FOCAL_PLANE = _FOCAL_MM / _SENSOR_WIDTH_MM


def _project(point: Vector3D) -> Point2D:
    camera_point = CORE_TO_NUKE_CAMERA_BASIS.transform_point(_M_NUKE_INV.transform_point(point))
    return solver_to_ui(
        Point2D(
            -_FOCAL_PLANE * camera_point.x / camera_point.z,
            -_FOCAL_PLANE * camera_point.y / camera_point.z,
        ),
        _DIMS,
    )


_CORNERS = {
    "box_v000": Vector3D(-0.5, -0.5, -0.5),
    "box_v100": Vector3D(0.5, -0.5, -0.5),
    "box_v010": Vector3D(-0.5, -0.5, 0.5),
    "box_v110": Vector3D(0.5, -0.5, 0.5),
    "box_v001": Vector3D(-0.5, 0.5, -0.5),
    "box_v101": Vector3D(0.5, 0.5, -0.5),
    "box_v011": Vector3D(-0.5, 0.5, 0.5),
    "box_v111": Vector3D(0.5, 0.5, 0.5),
}


def _assert_rotation_matches_nuke(matrix: Matrix4) -> None:
    for row in range(3):
        for col in range(3):
            assert isclose(matrix.rows[row][col], _M_NUKE.rows[row][col], abs_tol=1e-3)


def _assert_position_direction_matches_nuke(position: Vector3D) -> None:
    # Single-image scale is arbitrary, so only the direction is constrained.
    solved = position.normalized()
    expected = _TRANSLATE.normalized()
    assert isclose(solved.x, expected.x, abs_tol=1e-3)
    assert isclose(solved.y, expected.y, abs_tol=1e-3)
    assert isclose(solved.z, expected.z, abs_tol=1e-3)


def test_box_mode_recovers_real_nuke_camera_without_flip():
    projected = {name: _project(point) for name, point in _CORNERS.items()}
    result = solve_box_match(
        SolveInput(
            image_width=_DIMS.width, image_height=_DIMS.height,
            vp1_segments=(), vp2_segments=(),
            origin=_project(Vector3D(0, 0, 0)),
            first_axis="+X", second_axis="+Z",
            sensor_width_mm=_SENSOR_WIDTH_MM,
        ),
        projected,
    )
    assert result.ok
    _assert_rotation_matches_nuke(result.camera_to_world_matrix)
    _assert_position_direction_matches_nuke(result.camera_position)
    assert result.camera_position.y > 0.0  # above the X/Z floor


def test_vp_mode_recovers_real_nuke_camera_without_flip():
    # +X edges (low x -> high x) and +Z edges (low z -> high z), drawn along +axis.
    vp_x = (
        Segment2D(_project(Vector3D(-0.5, -0.5, -0.5)), _project(Vector3D(0.5, -0.5, -0.5))),
        Segment2D(_project(Vector3D(-0.5, 0.5, 0.5)), _project(Vector3D(0.5, 0.5, 0.5))),
    )
    vp_z = (
        Segment2D(_project(Vector3D(-0.5, -0.5, -0.5)), _project(Vector3D(-0.5, -0.5, 0.5))),
        Segment2D(_project(Vector3D(0.5, 0.5, -0.5)), _project(Vector3D(0.5, 0.5, 0.5))),
    )
    result = solve_2vp(SolveInput(
        image_width=_DIMS.width, image_height=_DIMS.height,
        vp1_segments=vp_x, vp2_segments=vp_z,
        first_axis="X", second_axis="-Z",
        sensor_width_mm=_SENSOR_WIDTH_MM,
        origin=_project(Vector3D(0, 0, 0)),
    ))
    assert result.ok
    _assert_rotation_matches_nuke(result.camera_to_world_matrix)
    _assert_position_direction_matches_nuke(result.camera_position)
    assert isclose(result.focal_length_mm, _FOCAL_MM, abs_tol=0.5)


def test_world_origin_projects_to_the_canvas_origin_marker():
    # The origin is fixed at world (0,0,0); no rotation/flip can move it off the
    # marker. Confirm the solved camera reprojects it back to where it was set.
    origin_ui = _project(Vector3D(0, 0, 0))
    vp_x = (
        Segment2D(_project(Vector3D(-0.5, -0.5, -0.5)), _project(Vector3D(0.5, -0.5, -0.5))),
        Segment2D(_project(Vector3D(-0.5, 0.5, 0.5)), _project(Vector3D(0.5, 0.5, 0.5))),
    )
    vp_z = (
        Segment2D(_project(Vector3D(-0.5, -0.5, -0.5)), _project(Vector3D(-0.5, -0.5, 0.5))),
        Segment2D(_project(Vector3D(0.5, 0.5, -0.5)), _project(Vector3D(0.5, 0.5, 0.5))),
    )
    result = solve_2vp(SolveInput(
        image_width=_DIMS.width, image_height=_DIMS.height,
        vp1_segments=vp_x, vp2_segments=vp_z,
        first_axis="X", second_axis="-Z",
        sensor_width_mm=_SENSOR_WIDTH_MM, origin=origin_ui,
    ))
    assert result.ok
    camera_point = result.world_to_camera_matrix.transform_point(Vector3D(0, 0, 0))
    reprojected = solver_to_ui(
        Point2D(
            -_FOCAL_PLANE * camera_point.x / camera_point.z,
            -_FOCAL_PLANE * camera_point.y / camera_point.z,
        ),
        _DIMS, result.principal_point_ui,
    )
    assert isclose(reprojected.x, origin_ui.x, abs_tol=1e-4)
    assert isclose(reprojected.y, origin_ui.y, abs_tol=1e-4)
