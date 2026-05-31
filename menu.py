"""Install the Scene Solver menu when Nuke starts."""

# registerWidgetAsPanel resolves this class path when the pane is constructed.
import scene_solver.ui.panel

from scene_solver.nuke_integration.panel_registration import install_menu

install_menu()
