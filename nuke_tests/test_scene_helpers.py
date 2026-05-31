"""Integration test for Scene Solver scene helpers.

Run with:

    Nuke15.1.exe --safe -t -V 0 nuke_tests/test_scene_helpers.py
"""

from __future__ import annotations

from math import isclose
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nuke

from scene_solver.core import MatchBox, Vector3D
from scene_solver.nuke_integration import (
    create_match_box,
    create_origin_card,
    create_scene_grid,
)


def assert_close(actual: float, expected: float) -> None:
    if not isclose(actual, expected, abs_tol=1e-6):
        raise AssertionError(f"{actual!r} != {expected!r}")


def assert_vector_knob(node, knob_name: str, expected: Vector3D) -> None:
    knob = node[knob_name]
    assert_close(knob.value(0), expected.x)
    assert_close(knob.value(1), expected.y)
    assert_close(knob.value(2), expected.z)


def main() -> None:
    scene_grid = create_scene_grid(size=12.0)
    if scene_grid.texture.Class() != "Grid":
        raise AssertionError(scene_grid.texture.Class())
    if scene_grid.card.Class() != "Card2":
        raise AssertionError(scene_grid.card.Class())
    if scene_grid.card.input(0) is not scene_grid.texture:
        raise AssertionError("Grid texture was not connected to Card2.")
    assert_vector_knob(scene_grid.card, "translate", Vector3D(0.0, 0.0, 0.0))
    assert_vector_knob(scene_grid.card, "rotate", Vector3D(-90.0, 0.0, 0.0))
    assert_vector_knob(scene_grid.card, "scaling", Vector3D(12.0, 12.0, 12.0))

    origin_card = create_origin_card(size=0.5)
    if origin_card.Class() != "Card2":
        raise AssertionError(origin_card.Class())
    assert_vector_knob(origin_card, "translate", Vector3D(0.0, 0.0, 0.0))
    assert_vector_knob(origin_card, "rotate", Vector3D(-90.0, 0.0, 0.0))
    assert_vector_knob(origin_card, "scaling", Vector3D(0.5, 0.5, 0.5))

    match_box = create_match_box(
        MatchBox(
            center=Vector3D(1.0, 2.0, 3.0),
            size=Vector3D(4.0, 5.0, 6.0),
        )
    )
    if match_box.Class() != "Cube":
        raise AssertionError(match_box.Class())
    assert_vector_knob(match_box, "translate", Vector3D(1.0, 2.0, 3.0))
    assert_vector_knob(match_box, "scaling", Vector3D(4.0, 5.0, 6.0))

    print("scene-helpers-test passed", flush=True)
    nuke.scriptClear()


if __name__ == "__main__":
    main()
