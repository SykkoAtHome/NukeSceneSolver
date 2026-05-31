"""Register the Lens Solver panel and menu command in Nuke's Qt runtime."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import nuke

from lens_solver.nuke_integration.panel_registration import install_menu


def main() -> None:
    if not nuke.GUI:
        print("menu-registration-test skipped: interactive GUI required", flush=True)
        return
    install_menu()
    if nuke.menu("Nodes").findItem("Lens Solver/Open Lens Solver") is None:
        raise AssertionError("Lens Solver toolbar command was not installed.")
    print("menu-registration-test passed", flush=True)


if __name__ == "__main__":
    main()
