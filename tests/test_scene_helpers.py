import pytest

from lens_solver.core.models import Vector3D
from lens_solver.core.scene_reconstruction import MatchBox
from lens_solver.nuke_integration.scene_helpers import (
    SceneHelperError,
    create_match_box,
    create_origin_card,
    create_scene_grid,
)


class FakeKnob:
    def __init__(self) -> None:
        self.values: dict[int, float] = {}

    def setValue(self, value: float, index: int = 0) -> None:
        self.values[index] = value


class FakeNode:
    def __init__(self, node_class: str, name: str) -> None:
        self.node_class = node_class
        self.name = name
        self.inputs: dict[int, FakeNode] = {}
        self.knobs = {
            "translate": FakeKnob(),
            "rotate": FakeKnob(),
            "scaling": FakeKnob(),
        }

    def Class(self) -> str:
        return self.node_class

    def knob(self, name: str) -> FakeKnob | None:
        return self.knobs.get(name)

    def setInput(self, index: int, node: "FakeNode") -> None:
        self.inputs[index] = node


class FakeNodes:
    def Grid(self, *, name: str) -> FakeNode:
        return FakeNode("Grid", name)

    def Card2(self, *, name: str) -> FakeNode:
        return FakeNode("Card2", name)

    def Cube(self, *, name: str) -> FakeNode:
        return FakeNode("Cube", name)


class FakeNuke:
    nodes = FakeNodes()


def test_create_scene_grid_connects_texture_to_scaled_card() -> None:
    grid = create_scene_grid(size=12.0, nuke_module=FakeNuke())

    assert grid.texture.Class() == "Grid"
    assert grid.card.Class() == "Card2"
    assert grid.card.inputs == {0: grid.texture}
    assert grid.card.knob("translate").values == {0: 0.0, 1: 0.0, 2: 0.0}
    assert grid.card.knob("rotate").values == {0: -90.0, 1: 0.0, 2: 0.0}
    assert grid.card.knob("scaling").values == {0: 12.0, 1: 12.0, 2: 12.0}


def test_create_origin_card_places_small_card_at_world_origin() -> None:
    card = create_origin_card(size=0.5, nuke_module=FakeNuke())

    assert card.Class() == "Card2"
    assert card.knob("translate").values == {0: 0.0, 1: 0.0, 2: 0.0}
    assert card.knob("rotate").values == {0: -90.0, 1: 0.0, 2: 0.0}
    assert card.knob("scaling").values == {0: 0.5, 1: 0.5, 2: 0.5}


def test_create_match_box_sets_cube_transform() -> None:
    cube = create_match_box(
        MatchBox(
            center=Vector3D(1.0, 2.0, 3.0),
            size=Vector3D(4.0, 5.0, 6.0),
        ),
        nuke_module=FakeNuke(),
    )

    assert cube.Class() == "Cube"
    assert cube.knob("translate").values == {0: 1.0, 1: 2.0, 2: 3.0}
    assert cube.knob("scaling").values == {0: 4.0, 1: 5.0, 2: 6.0}


def test_scene_helper_size_must_be_positive() -> None:
    with pytest.raises(SceneHelperError, match="positive"):
        create_origin_card(size=0.0, nuke_module=FakeNuke())
