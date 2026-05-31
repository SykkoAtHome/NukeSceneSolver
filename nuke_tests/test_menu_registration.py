"""Register the Scene Solver panel and menu command in Nuke's Qt runtime."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nuke

from scene_solver.nuke_integration.panel_registration import install_menu


def main() -> None:
    if not nuke.GUI:
        print("menu-registration-test skipped: interactive GUI required", flush=True)
        return
    install_menu()
    if nuke.menu("Nodes").findItem("Scene Solver/Open Scene Solver") is None:
        raise AssertionError("Scene Solver toolbar command was not installed.")
    print("menu-registration-test passed", flush=True)


if __name__ == "__main__":
    main()
