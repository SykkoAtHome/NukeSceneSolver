"""Create lightweight Nuke 3D helper nodes for a Scene Solver scene."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from scene_solver.core.models import Vector3D
from scene_solver.core.scene_reconstruction import MatchBox


GROUND_PLANE_ROTATION = Vector3D(-90.0, 0.0, 0.0)


class SceneHelperError(ValueError):
    """Raised when scene helper nodes cannot be created."""


@dataclass(frozen=True, slots=True)
class SceneGridNodes:
    texture: Any
    card: Any


def create_scene_grid(
    *,
    name: str = "SceneSolverSceneGrid",
    size: float = 10.0,
    nuke_module: Any | None = None,
) -> SceneGridNodes:
    """Create a 2D Grid texture connected to a Card2 at world origin."""

    _validate_size(size)
    nuke = nuke_module or _import_nuke()
    texture = nuke.nodes.Grid(name=f"{name}Texture")
    card = nuke.nodes.Card2(name=name)
    card.setInput(0, texture)
    _configure_ground_card(card, size)
    return SceneGridNodes(texture=texture, card=card)


def create_origin_card(
    *,
    name: str = "SceneSolverOriginCard",
    size: float = 0.25,
    nuke_module: Any | None = None,
) -> Any:
    """Create a small Card2 centered at scene origin."""

    _validate_size(size)
    nuke = nuke_module or _import_nuke()
    card = nuke.nodes.Card2(name=name)
    _configure_ground_card(card, size)
    return card


def _configure_ground_card(card: Any, size: float) -> None:
    _set_vector_knob(card, "translate", Vector3D(0.0, 0.0, 0.0))
    _set_vector_knob(card, "rotate", GROUND_PLANE_ROTATION)
    _set_vector_knob(card, "scaling", Vector3D(size, size, size))


def create_match_box(
    match_box: MatchBox,
    *,
    name: str = "SceneSolverMatchBox",
    nuke_module: Any | None = None,
) -> Any:
    """Create a Cube matching the coarse box reconstruction."""

    nuke = nuke_module or _import_nuke()
    cube = nuke.nodes.Cube(name=name)
    _set_vector_knob(cube, "translate", match_box.center)
    _set_vector_knob(cube, "scaling", match_box.size)
    return cube


def _set_vector_knob(node: Any, name: str, value: Vector3D) -> None:
    knob = node.knob(name) if hasattr(node, "knob") else node[name]
    if knob is None:
        raise SceneHelperError(f"{node.Class()} node is missing required knob {name!r}.")
    knob.setValue(value.x, 0)
    knob.setValue(value.y, 1)
    knob.setValue(value.z, 2)


def _validate_size(size: float) -> None:
    if not isfinite(size) or size <= 0.0:
        raise SceneHelperError("Scene helper size must be a finite positive value.")


def _import_nuke() -> Any:
    try:
        import nuke
    except ImportError as error:
        raise SceneHelperError("The nuke module is only available inside Nuke.") from error
    return nuke
