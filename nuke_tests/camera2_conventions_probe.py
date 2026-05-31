"""Probe Camera2 matrix and projection conventions in terminal Nuke."""

from __future__ import annotations

import nuke
from nukescripts import snap3d


IDENTITY = (
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
    0.0,
    0.0,
    0.0,
    0.0,
    1.0,
)


def set_matrix(camera, values) -> None:
    camera["useMatrix"].setValue(True)
    for index, value in enumerate(values):
        camera["matrix"].setValue(value, index)


def knob_values(camera, knob_name: str) -> list[float]:
    return [camera[knob_name].valueAt(nuke.frame(), index) for index in range(16)]


def project(camera, point) -> tuple[float, float]:
    projected = snap3d.projectPoint(camera, point)
    return projected.x, projected.y


def main() -> None:
    nuke.root()["format"].setValue("HD_1080")
    camera = nuke.nodes.Camera2(name="SceneSolverConventionsProbe")
    camera["focal"].setValue(18.0)
    camera["haperture"].setValue(36.0)
    camera["vaperture"].setValue(20.25)
    set_matrix(camera, IDENTITY)

    print("root-format", nuke.root()["format"].value().name(), flush=True)
    print("local-matrix", knob_values(camera, "matrix"), flush=True)
    print("world-matrix", knob_values(camera, "world_matrix"), flush=True)
    print("project-center", project(camera, (0.0, 0.0, 1.0)), flush=True)
    print("project-right", project(camera, (0.5, 0.0, 1.0)), flush=True)
    print("project-up", project(camera, (0.0, 0.5, 1.0)), flush=True)

    translated = list(IDENTITY)
    translated[3] = 1.0
    translated[7] = 2.0
    translated[11] = 3.0
    set_matrix(camera, translated)
    print("translated-world-matrix", knob_values(camera, "world_matrix"), flush=True)
    print("translated-transform", [camera["transform"].value()[index] for index in range(16)], flush=True)

    set_matrix(camera, IDENTITY)
    camera["win_translate"].setValue(0.2, 0)
    camera["win_translate"].setValue(-0.3, 1)
    print("window-translate", camera["win_translate"].getValue(), flush=True)
    print("project-shifted-center", project(camera, (0.0, 0.0, 1.0)), flush=True)
    nuke.scriptClear()


if __name__ == "__main__":
    main()

