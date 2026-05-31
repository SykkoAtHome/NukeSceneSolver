"""Install the Lens Solver menu when Nuke starts."""

# registerWidgetAsPanel resolves this class path when the pane is constructed.
import lens_solver.ui.panel

from lens_solver.nuke_integration.panel_registration import install_menu

install_menu()
