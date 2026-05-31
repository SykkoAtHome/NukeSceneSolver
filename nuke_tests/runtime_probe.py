"""Print the Camera2 runtime surface from a terminal Nuke session."""

from __future__ import annotations

import nuke


def main() -> None:
    print("nuke-version", nuke.NUKE_VERSION_STRING, flush=True)
    camera = nuke.nodes.Camera2(name="LensSolverRuntimeProbe")
    print("camera-class", camera.Class(), flush=True)
    for name in ("focal", "haperture", "vaperture", "win_translate", "useMatrix", "matrix"):
        knob = camera.knob(name)
        print(
            "knob",
            name,
            "present" if knob is not None else "missing",
            knob.Class() if knob is not None else "",
            flush=True,
        )
    nuke.scriptClear()


if __name__ == "__main__":
    main()

