"""VP-mode floor-reflection canonicalization.

A vanishing point is identical for an axis and its reverse, so a single
mis-drawn ground line silently mirrors the camera through the X/Z floor. Like
box mode, the line solver must prefer the camera in Nuke's ``+Y`` half-space.
"""

from __future__ import annotations

from scene_solver.core.coordinates import ImageDimensions, solver_to_ui
from scene_solver.core.models import Matrix4, Point2D, Segment2D, Vector3D
from scene_solver.core.projection import camera_direction_to_solver_point
from scene_solver.core.solver_2vp import SolveInput, solve_2vp

_W, _H = 1920, 1080
_DIMS = ImageDimensions(_W, _H)
_FOCAL_PLANE = 1.5
_PP = Point2D(0.5, 0.5)
_CAM_POS = Vector3D(5.0, 3.0, 8.0)  # above the X/Z floor, yawed off-axis


def _ground_truth_rotation() -> Matrix4:
    forward = (Vector3D(0, 0, 0) - _CAM_POS).normalized()
    cam_z = forward * -1.0
    cam_x = Vector3D(0.0, 1.0, 0.0).cross(cam_z).normalized()
    cam_y = cam_z.cross(cam_x).normalized()
    return Matrix4.from_rows((
        (cam_x.x, cam_y.x, cam_z.x, 0.0),
        (cam_x.y, cam_y.y, cam_z.y, 0.0),
        (cam_x.z, cam_y.z, cam_z.z, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    ))


_ROTATION = _ground_truth_rotation()
_WORLD_TO_CAMERA = _ROTATION.transposed()


def _project(point: Vector3D) -> Point2D:
    camera = _WORLD_TO_CAMERA.transform_direction(point - _CAM_POS)
    solver_point = camera_direction_to_solver_point(camera, _FOCAL_PLANE)
    return solver_to_ui(solver_point, _DIMS, _PP)


def _segment(start: Vector3D, end: Vector3D) -> Segment2D:
    return Segment2D(_project(start), _project(end))


def _reversed(segments):
    return tuple(Segment2D(s.end, s.start) for s in segments)


def _x_segments():
    return (
        _segment(Vector3D(-1, 0, 0), Vector3D(2, 0, 0)),
        _segment(Vector3D(-1, 0, 3), Vector3D(2, 0, 3)),
    )


def _z_segments():
    return (
        _segment(Vector3D(0, 0, -1), Vector3D(0, 0, 2)),
        _segment(Vector3D(3, 0, -1), Vector3D(3, 0, 2)),
    )


def _solve(vp1, vp2):
    return solve_2vp(SolveInput(
        image_width=_W, image_height=_H,
        vp1_segments=vp1, vp2_segments=vp2,
        first_axis="X", second_axis="Z",
        camera_distance=_CAM_POS.length(),
    ))


def test_correctly_drawn_ground_axes_keep_camera_above_floor():
    result = _solve(_x_segments(), _z_segments())
    assert result.ok
    assert result.camera_position.y > 0.0


def test_reversed_x_axis_is_canonicalized_above_nuke_floor():
    result = _solve(_reversed(_x_segments()), _z_segments())
    assert result.ok
    assert result.camera_position.y > 0.0


def test_reversed_z_axis_is_canonicalized_above_nuke_floor():
    result = _solve(_x_segments(), _reversed(_z_segments()))
    assert result.ok
    assert result.camera_position.y > 0.0
