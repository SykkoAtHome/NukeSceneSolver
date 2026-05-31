"""Adapters that are allowed to depend on Foundry Nuke."""

from scene_solver.nuke_integration.camera_adapter import (
    CameraAdapterError,
    core_camera_to_nuke_matrix,
    create_camera,
    update_camera,
)
from scene_solver.nuke_integration.read_adapter import (
    NodeSelectionError,
    PlateInfo,
    PreviewRenderError,
    get_selected_camera,
    get_selected_read,
    render_plate_preview,
)
from scene_solver.nuke_integration.scene_helpers import (
    SceneGridNodes,
    SceneHelperError,
    create_match_box,
    create_origin_card,
    create_scene_grid,
)
from scene_solver.nuke_integration.state import load_state, save_state

__all__ = [
    "CameraAdapterError",
    "NodeSelectionError",
    "PlateInfo",
    "PreviewRenderError",
    "SceneGridNodes",
    "SceneHelperError",
    "core_camera_to_nuke_matrix",
    "create_camera",
    "create_match_box",
    "create_origin_card",
    "create_scene_grid",
    "get_selected_camera",
    "get_selected_read",
    "load_state",
    "render_plate_preview",
    "save_state",
    "update_camera",
]
