"""Register and open the dockable Scene Solver panel in Nuke."""

from __future__ import annotations

from typing import Any


PANEL_CLASS = "scene_solver.ui.panel.SceneSolverPanel"
PANEL_TITLE = "Scene Solver"
PANEL_ID = "com.rafal.nukeSceneSolver"
TOOLBAR_COMMAND = "Scene Solver/Open Scene Solver"


def show_panel() -> Any:
    """Create and dock a Scene Solver panel in the Properties pane."""

    import nuke
    from nukescripts import panels

    panel = panels.registerWidgetAsPanel(PANEL_CLASS, PANEL_TITLE, PANEL_ID, True)
    pane = nuke.getPaneFor("Properties.1")
    panel.addToPane(pane)
    return panel


def install_menu() -> None:
    """Register the dockable panel and install its Nodes toolbar launcher."""

    import nuke
    from nukescripts import panels

    panels.registerWidgetAsPanel(PANEL_CLASS, PANEL_TITLE, PANEL_ID)
    nuke.menu("Nodes").addCommand(TOOLBAR_COMMAND, show_panel)
