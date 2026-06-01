from pathlib import Path

import pytest

from scene_solver.nuke_integration.read_adapter import (
    NodeSelectionError,
    PlateInfo,
    PreviewRenderError,
    _preview_dimensions,
    get_selected_camera,
    get_selected_read,
    render_plate_preview,
)


class FakeKnob:
    def __init__(self, value=None) -> None:
        self._value = value

    def evaluate(self):
        return self._value

    def setValue(self, value) -> None:
        self._value = value

    def value(self):
        return self._value


class FakeNode:
    def __init__(
        self,
        node_class: str,
        name: str,
        *,
        width: int = 0,
        height: int = 0,
        file_path: str = "",
    ) -> None:
        self._node_class = node_class
        self._name = name
        self._width = width
        self._height = height
        self._selected = False
        self.inputs: dict[int, FakeNode] = {}
        self.knobs = {
            "file": FakeKnob(file_path),
            "type": FakeKnob(),
            "box_width": FakeKnob(),
            "box_height": FakeKnob(),
            "box_fixed": FakeKnob(),
            "resize": FakeKnob(),
            "file_type": FakeKnob(),
            "channels": FakeKnob(),
        }

    def Class(self) -> str:
        return self._node_class

    def name(self) -> str:
        return self._name

    def width(self) -> int:
        return self._width

    def height(self) -> int:
        return self._height

    def knob(self, name: str) -> FakeKnob | None:
        return self.knobs.get(name)

    def setInput(self, index: int, node: "FakeNode") -> None:
        self.inputs[index] = node

    def setSelected(self, selected: bool) -> None:
        self._selected = selected


class FakeNodes:
    def __init__(self, nuke: "FakeNuke") -> None:
        self._nuke = nuke

    def Reformat(self, *, name: str) -> FakeNode:
        return self._nuke.create_node("Reformat", name)

    def Write(self, *, name: str) -> FakeNode:
        return self._nuke.create_node("Write", name)


class FakeNuke:
    def __init__(self, *, fail_execute: bool = False) -> None:
        self.fail_execute = fail_execute
        self._modified = False
        self.deleted: list[FakeNode] = []
        self.nodes = FakeNodes(self)
        self.read = FakeNode(
            "Read",
            "Plate",
            width=3840,
            height=2160,
            file_path="/plates/shot.exr",
        )
        self.camera = FakeNode("Camera2", "Camera")
        self._nodes = [self.read, self.camera]
        self.read.setSelected(True)

    def create_node(self, node_class: str, name: str) -> FakeNode:
        for node in self._nodes:
            node.setSelected(False)
        node = FakeNode(node_class, name)
        node.setSelected(True)
        self._nodes.append(node)
        self._modified = True
        return node

    def selectedNodes(self, node_class: str | None = None) -> list[FakeNode]:
        return [
            node
            for node in self._nodes
            if node._selected and (node_class is None or node.Class() == node_class)
        ]

    def allNodes(self) -> list[FakeNode]:
        return list(self._nodes)

    def execute(self, write: FakeNode, start: int, end: int) -> None:
        if self.fail_execute:
            raise RuntimeError("render failed")
        Path(write.knob("file").value()).write_bytes(b"png-bytes")

    def frame(self) -> int:
        return 1001

    def delete(self, node: FakeNode) -> None:
        self.deleted.append(node)
        self._nodes.remove(node)

    def modified(self, value: bool | None = None):
        if value is None:
            return self._modified
        self._modified = value


def test_get_selected_read_returns_plate_metadata() -> None:
    nuke = FakeNuke()

    plate = get_selected_read(nuke_module=nuke)

    assert plate == PlateInfo(nuke.read, "Plate", 3840, 2160, "/plates/shot.exr")


def test_get_selected_camera_requires_exactly_one_camera() -> None:
    nuke = FakeNuke()

    with pytest.raises(NodeSelectionError, match="exactly one"):
        get_selected_camera(nuke_module=nuke)

    nuke.read.setSelected(False)
    nuke.camera.setSelected(True)
    assert get_selected_camera(nuke_module=nuke) is nuke.camera


def test_render_plate_preview_cleans_up_nodes_file_selection_and_modified_flag(tmp_path) -> None:
    nuke = FakeNuke()
    plate = get_selected_read(nuke_module=nuke)

    data = render_plate_preview(plate, nuke_module=nuke, temporary_directory=tmp_path)

    assert data == b"png-bytes"
    assert [node.Class() for node in nuke.deleted] == ["Write", "Reformat"]
    assert list(tmp_path.iterdir()) == []
    assert nuke.selectedNodes() == [nuke.read]
    assert nuke.modified() is False


def test_render_plate_preview_cleans_up_after_render_failure(tmp_path) -> None:
    nuke = FakeNuke(fail_execute=True)
    plate = get_selected_read(nuke_module=nuke)

    with pytest.raises(PreviewRenderError, match="render failed"):
        render_plate_preview(plate, nuke_module=nuke, temporary_directory=tmp_path)

    assert [node.Class() for node in nuke.deleted] == ["Write", "Reformat"]
    assert list(tmp_path.iterdir()) == []
    assert nuke.selectedNodes() == [nuke.read]
    assert nuke.modified() is False


@pytest.mark.parametrize(
    ("width", "height", "maximum", "expected"),
    (
        (3840, 2160, 1280, (1280, 720)),
        (640, 480, 1280, (640, 480)),
        (1, 1000, 1, (1, 1)),
    ),
)
def test_preview_dimensions_preserve_aspect_ratio(
    width: int,
    height: int,
    maximum: int,
    expected: tuple[int, int],
) -> None:
    assert _preview_dimensions(width, height, maximum) == expected
