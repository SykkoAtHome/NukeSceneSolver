"""Register and open the dockable Lens Solver panel in Nuke."""

from __future__ import annotations

from typing import Any


PANEL_CLASS = "lens_solver.ui.panel.LensSolverPanel"
PANEL_TITLE = "Lens Solver"
PANEL_ID = "com.rafal.nukeLensSolver"
TOOLBAR_COMMAND = "Lens Solver/Open Lens Solver"


def show_panel() -> Any:
    """Create and dock a Lens Solver panel in the Properties pane."""

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
