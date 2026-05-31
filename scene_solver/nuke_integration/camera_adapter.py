"""Create or update a Nuke 15.1 Camera2 node from a core solve result.

The core solver uses Nuke's classic local camera convention directly: local
``-Z`` points forward, while local ``+X`` and ``+Y`` point right and up.
"""

from __future__ import annotations

from math import isclose
from typing import Any

from scene_solver.core.models import Matrix4, Vector3D
from scene_solver.core.solver_2vp import SolveResult


class CameraAdapterError(ValueError):
    """Raised when a solve result cannot be applied to a Camera2 node."""


CORE_TO_NUKE_CAMERA_BASIS = Matrix4.identity()


def core_camera_to_nuke_matrix(camera_to_world_matrix: Matrix4) -> Matrix4:
    """Convert a core camera-to-world matrix into Camera2 local-axis convention."""

    return camera_to_world_matrix @ CORE_TO_NUKE_CAMERA_BASIS


def create_camera(
    result: SolveResult,
    *,
    name: str = "SceneSolverCamera",
    nuke_module: Any | None = None,
) -> Any:
    """Create an unparented Camera2 node and apply a successful solve result."""

    nuke = nuke_module or _import_nuke()
    camera = nuke.nodes.Camera2(name=name)
    update_camera(camera, result)
    return camera


def update_camera(camera: Any, result: SolveResult) -> Any:
    """Apply a successful solve result to an unparented Camera2 node."""

    _validate_camera(camera)
    _validate_result(result)
    assert result.camera_to_world_matrix is not None
    assert result.focal_length_mm is not None
    assert result.sensor_width_mm is not None
    assert result.sensor_height_mm is not None
    assert result.image_dimensions is not None

    matrix = core_camera_to_nuke_matrix(result.camera_to_world_matrix)
    camera["projection_mode"].setValue(0)
    camera["focal"].setValue(result.focal_length_mm)
    camera["haperture"].setValue(result.sensor_width_mm)
    camera["vaperture"].setValue(result.sensor_height_mm)
    camera["winroll"].setValue(0.0)
    camera["win_scale"].setValue(1.0, 0)
    camera["win_scale"].setValue(1.0, 1)
    camera["win_translate"].setValue(0.0, 0)
    camera["win_translate"].setValue(0.0, 1)
    camera["useMatrix"].setValue(True)
    for index, value in enumerate(_flatten_rows(matrix)):
        camera["matrix"].setValue(value, index)
    return camera


def _validate_camera(camera: Any) -> None:
    if camera is None or not hasattr(camera, "Class") or camera.Class() != "Camera2":
        raise CameraAdapterError("Expected a Nuke Camera2 node.")
    if hasattr(camera, "inputs") and hasattr(camera, "input"):
        if any(camera.input(index) is not None for index in range(camera.inputs())):
            raise CameraAdapterError("Cannot update a parented Camera2 node.")


def _validate_result(result: SolveResult) -> None:
    if not result.ok:
        raise CameraAdapterError("Cannot create a camera from an unsuccessful solve result.")
    required_values = (
        result.camera_to_world_matrix,
        result.focal_length_mm,
        result.sensor_width_mm,
        result.sensor_height_mm,
        result.image_dimensions,
    )
    if any(value is None for value in required_values):
        raise CameraAdapterError("Solve result is missing required camera data.")
    if not (
        isclose(result.principal_point_ui.x, 0.5, abs_tol=1e-12)
        and isclose(result.principal_point_ui.y, 0.5, abs_tol=1e-12)
    ):
        raise CameraAdapterError(
            "Off-center principal points are not supported by the Camera2 adapter yet."
        )


def _flatten_rows(matrix: Matrix4) -> tuple[float, ...]:
    return tuple(value for row in matrix.rows for value in row)


def _import_nuke() -> Any:
    try:
        import nuke
    except ImportError as error:
        raise CameraAdapterError("The nuke module is only available inside Nuke.") from error
    return nuke
