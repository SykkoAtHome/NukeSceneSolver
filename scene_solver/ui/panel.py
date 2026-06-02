"""Dockable Scene Solver panel for Nuke 15.1."""

from __future__ import annotations

from math import degrees

from PySide2 import QtCore, QtGui, QtWidgets

from scene_solver.core import (
    BoxDimensionCalibration,
    BoxDimensionInput,
    DEFAULT_PRINCIPAL_POINT,
    GeometryError,
    Point2D,
    SolveInput,
    SolveResult,
    reconstruct_match_box,
    solve_2vp,
    solve_box_match,
    solve_box_match_with_dimension,
)
from scene_solver.nuke_integration import (
    CameraAdapterError,
    NodeSelectionError,
    PlateInfo,
    PreviewRenderError,
    SceneHelperError,
    create_camera,
    create_match_box,
    create_origin_card,
    create_scene_grid,
    get_selected_camera,
    get_selected_read,
    load_state,
    render_plate_preview,
    save_state,
    update_camera,
)
from scene_solver.ui.axis_display import axis_letter
from scene_solver.ui.canvas import SceneSolverCanvas
from scene_solver.ui.state_migration import migrate_legacy_canvas_directions


AXES = ("X", "Y", "Z")
ARBITRARY_SCALE_MODE = "Arbitrary camera distance"
BOX_DIMENSION_SCALE_MODE = "Estimated match-box dimension"
DIRECTED_VP_LINES_STATE_VERSION = 1


class SceneSolverPanel(QtWidgets.QWidget):
    """Interactive 2VP camera-matching panel."""

    # Idle delay after the last live change before the expensive full solve
    # (scale calibration) and Nuke state write run. Coalesces a burst of
    # per-pixel drag updates into a single heavy refresh.
    _REFRESH_DEBOUNCE_MS = 150

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plate: PlateInfo | None = None
        self._last_result: SolveResult | None = None
        self._last_box_dimension: BoxDimensionCalibration | None = None
        self._is_loading_state = True
        self._build_ui()
        self._refresh_timer = QtCore.QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(self._REFRESH_DEBOUNCE_MS)
        self._refresh_timer.timeout.connect(self._on_refresh_timeout)
        self._connect_signals()
        try:
            self._load_state_from_nuke()
        finally:
            self._is_loading_state = False
        self._refresh_solution()

    def _build_ui(self) -> None:
        self.setWindowTitle("Scene Solver")
        layout = QtWidgets.QVBoxLayout(self)

        plate_row = QtWidgets.QHBoxLayout()
        self._plate_label = QtWidgets.QLabel("No Read selected")
        self._use_read_button = QtWidgets.QPushButton("Use Selected Read")
        plate_row.addWidget(self._plate_label, 1)
        plate_row.addWidget(self._use_read_button)
        layout.addLayout(plate_row)

        self._canvas = SceneSolverCanvas()
        layout.addWidget(self._canvas, 1)

        self._options_layout = QtWidgets.QFormLayout()
        options = self._options_layout
        self._match_type_combo = QtWidgets.QComboBox()
        self._match_type_combo.addItems(["Box Match", "Vanishing Points"])
        self._match_type_combo.setCurrentText("Vanishing Points")
        
        self._vp1_enable = QtWidgets.QCheckBox("First VP axis")
        self._vp1_enable.setChecked(True)
        self._vp1_enable.setEnabled(False) # Always at least 1 VP
        self._first_axis = QtWidgets.QComboBox()
        self._first_axis.addItems(AXES)
        
        self._vp2_enable = QtWidgets.QCheckBox("Second VP axis")
        self._vp2_enable.setChecked(True)
        self._second_axis = QtWidgets.QComboBox()
        self._second_axis.addItems(AXES)
        self._second_axis.setCurrentText("Z")
        
        self._vp3_enable = QtWidgets.QCheckBox("Third VP axis")
        self._vp3_enable.setChecked(False)
        self._third_axis = QtWidgets.QComboBox()
        self._third_axis.addItems(AXES)
        self._third_axis.setCurrentText("Y")
        
        self._auto_pp = QtWidgets.QCheckBox("Auto Principal Point (3VP only)")
        self._auto_pp.setChecked(True)
        
        self._use_pp_offset = QtWidgets.QCheckBox("Adjust Principal Point")
        self._use_pp_offset.setToolTip("Allow the optical center to be off-center (Lens Shift).")
        self._use_pp_offset.setChecked(False)

        self._flip_world_up = QtWidgets.QCheckBox("Flip world up (1VP only)")
        self._flip_world_up.setToolTip(
            "Use the inverted world-up solution for rolled or upside-down 1VP shots."
        )
        self._flip_world_up.setChecked(False)
        self._flip_world_up.setVisible(False)
        
        self._sensor_width = QtWidgets.QDoubleSpinBox()
        self._sensor_width.setRange(1.0, 200.0)
        self._sensor_width.setDecimals(3)
        self._sensor_width.setValue(36.0)
        
        self._focal_length = QtWidgets.QDoubleSpinBox()
        self._focal_length.setRange(1.0, 2000.0)
        self._focal_length.setDecimals(3)
        self._focal_length.setValue(50.0)
        
        self._camera_distance = QtWidgets.QDoubleSpinBox()
        self._camera_distance.setRange(0.01, 1000000.0)
        self._camera_distance.setDecimals(3)
        self._camera_distance.setValue(10.0)
        self._camera_distance.setToolTip(
            "Arbitrary scene scale used only when match-box dimension calibration is disabled."
        )
        self._scale_mode = QtWidgets.QComboBox()
        self._scale_mode.addItems([ARBITRARY_SCALE_MODE, BOX_DIMENSION_SCALE_MODE])
        self._box_dimension_axis = QtWidgets.QComboBox()
        self._box_dimension_axis.addItems(["X", "Y", "Z"])
        self._box_dimension_axis.setToolTip(
            "World-space match-box dimension used to estimate scene scale."
        )
        self._box_dimension_length = QtWidgets.QDoubleSpinBox()
        self._box_dimension_length.setRange(0.001, 1000000.0)
        self._box_dimension_length.setDecimals(3)
        self._box_dimension_length.setValue(1.0)
        self._box_dimension_length.setToolTip(
            "Estimated world-space size of the selected match-box dimension."
        )
        self._match_box_base_offset = QtWidgets.QDoubleSpinBox()
        self._match_box_base_offset.setRange(-1000000.0, 1000000.0)
        self._match_box_base_offset.setDecimals(3)
        self._match_box_base_offset.setValue(0.0)
        self._match_box_base_offset.setToolTip(
            "Coordinate of the match-box base plane along the derived third axis. "
            "For the default X/Z ground axes this is the base Y coordinate."
        )
        
        self._vp_axes_row = QtWidgets.QWidget()
        vp_axes_layout = QtWidgets.QHBoxLayout(self._vp_axes_row)
        vp_axes_layout.setContentsMargins(0, 0, 0, 0)
        vp_axes_layout.addWidget(self._vp1_enable)
        vp_axes_layout.addWidget(self._first_axis)
        vp_axes_layout.addSpacing(10)
        vp_axes_layout.addWidget(self._vp2_enable)
        vp_axes_layout.addWidget(self._second_axis)
        vp_axes_layout.addSpacing(10)
        vp_axes_layout.addWidget(self._vp3_enable)
        vp_axes_layout.addWidget(self._third_axis)
        vp_axes_layout.addStretch(1)

        options.addRow("Matching Mode", self._match_type_combo)
        options.addRow("VP Axes", self._vp_axes_row)
        options.addRow("", self._auto_pp)
        options.addRow("", self._use_pp_offset)
        options.addRow("", self._flip_world_up)

        self._sensor_width_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._sensor_width_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._sensor_width)
        row_layout.addWidget(QtWidgets.QLabel("mm"))
        row_layout.addStretch(1)
        options.addRow("Sensor width", self._sensor_width_row)

        self._focal_length_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._focal_length_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._focal_length)
        row_layout.addWidget(QtWidgets.QLabel("mm"))
        row_layout.addStretch(1)
        options.addRow("Focal length", self._focal_length_row)

        options.addRow("Scene scale mode", self._scale_mode)

        self._camera_dist_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._camera_dist_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._camera_distance)
        row_layout.addWidget(QtWidgets.QLabel("world units"))
        row_layout.addStretch(1)
        options.addRow("Camera distance", self._camera_dist_row)

        options.addRow("Box dimension axis", self._box_dimension_axis)

        self._box_dim_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._box_dim_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._box_dimension_length)
        row_layout.addWidget(QtWidgets.QLabel("world units"))
        row_layout.addStretch(1)
        options.addRow("Estimated box dimension", self._box_dim_row)

        self._base_offset_row = QtWidgets.QWidget()
        row_layout = QtWidgets.QHBoxLayout(self._base_offset_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self._match_box_base_offset)
        row_layout.addWidget(QtWidgets.QLabel("world units"))
        row_layout.addStretch(1)
        options.addRow("Match box base offset", self._base_offset_row)

        layout.addLayout(options)

        self._message = QtWidgets.QLabel()
        self._message.setWordWrap(True)
        self._message.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        layout.addWidget(self._message)

        actions = QtWidgets.QHBoxLayout()
        self._create_button = QtWidgets.QPushButton("Create Camera")
        self._update_button = QtWidgets.QPushButton("Update Selected Camera")
        actions.addWidget(self._create_button)
        actions.addWidget(self._update_button)
        layout.addLayout(actions)

        helper_actions = QtWidgets.QHBoxLayout()
        self._grid_button = QtWidgets.QPushButton("Create Scene Grid")
        self._origin_card_button = QtWidgets.QPushButton("Create Origin Card")
        self._match_box_button = QtWidgets.QPushButton("Create Match Box")
        helper_actions.addWidget(self._grid_button)
        helper_actions.addWidget(self._origin_card_button)
        helper_actions.addWidget(self._match_box_button)
        layout.addLayout(helper_actions)

    def _connect_signals(self) -> None:
        self._use_read_button.clicked.connect(self._use_selected_read)
        self._match_type_combo.currentTextChanged.connect(self._on_mode_changed)
        self._vp2_enable.toggled.connect(self._on_vp_check_toggled)
        self._vp3_enable.toggled.connect(self._on_vp_check_toggled)
        # Continuous sources (handle drags, spin-box scrubbing) take the
        # debounced path: a cheap live preview now, the heavy solve later.
        # Discrete sources (combos, check boxes) refresh fully right away.
        self._canvas.changed.connect(self._on_live_change)
        self._first_axis.currentTextChanged.connect(self._refresh_solution)
        self._second_axis.currentTextChanged.connect(self._refresh_solution)
        self._third_axis.currentTextChanged.connect(self._refresh_solution)
        self._auto_pp.toggled.connect(self._refresh_solution)
        self._use_pp_offset.toggled.connect(self._on_pp_offset_toggled)
        self._flip_world_up.toggled.connect(self._refresh_solution)
        self._sensor_width.valueChanged.connect(self._on_live_change)
        self._focal_length.valueChanged.connect(self._on_live_change)
        self._camera_distance.valueChanged.connect(self._on_live_change)
        self._scale_mode.currentTextChanged.connect(self._on_scale_mode_changed)
        self._box_dimension_axis.currentTextChanged.connect(self._refresh_solution)
        self._box_dimension_length.valueChanged.connect(self._on_live_change)
        self._match_box_base_offset.valueChanged.connect(self._on_live_change)
        self._create_button.clicked.connect(self._create_camera)
        self._update_button.clicked.connect(self._update_camera)
        self._grid_button.clicked.connect(self._create_scene_grid)
        self._origin_card_button.clicked.connect(self._create_origin_card)
        self._match_box_button.clicked.connect(self._create_match_box)
        self._focal_length.setEnabled(False)
        self._on_pp_offset_toggled() # Sync initial state
        self._update_scale_controls()

    def _on_vp_check_toggled(self) -> None:
        sender = self.sender()
        if sender == self._vp2_enable:
            if not self._vp2_enable.isChecked():
                self._vp3_enable.setChecked(False)
        elif sender == self._vp3_enable:
            if self._vp3_enable.isChecked():
                self._vp2_enable.setChecked(True)
        self._on_mode_changed()

    def _get_current_mode(self) -> str:
        if self._match_type_combo.currentText() == "Box Match":
            return "box"
        if self._vp3_enable.isChecked():
            return "3vp"
        if self._vp2_enable.isChecked():
            return "2vp"
        return "1vp"

    def _on_mode_changed(self, *args) -> None:
        mode = self._get_current_mode()
        self._canvas.set_mode(mode)
        
        if mode != "box" and self._uses_box_dimension():
            self._scale_mode.setCurrentText(ARBITRARY_SCALE_MODE)
        
        # Visibility logic
        is_vp = self._match_type_combo.currentText() == "Vanishing Points"
        is_1vp = (mode == "1vp")
        is_3vp = (mode == "3vp")
        is_box = (mode == "box")
        
        # Axis selectors
        self._set_row_visible(self._vp_axes_row, is_vp)
        self._vp1_enable.setEnabled(False) # Always checked and disabled in VP mode
        self._vp2_enable.setEnabled(is_vp)
        self._second_axis.setEnabled(not is_1vp)
        self._vp3_enable.setEnabled(is_vp)
        self._third_axis.setEnabled(is_3vp)
        
        # PP controls
        self._set_row_visible(self._auto_pp, is_3vp)
        self._auto_pp.setEnabled(is_3vp)
        
        # Focal length
        self._set_row_visible(self._focal_length_row, is_1vp)
        self._focal_length.setEnabled(is_1vp)
        self._set_row_visible(self._flip_world_up, is_1vp)
        self._flip_world_up.setEnabled(is_1vp)
        
        # Box specific
        self._set_row_visible(self._base_offset_row, is_box)
        self._match_box_button.setVisible(is_box)
        
        self._on_pp_offset_toggled()
        self._update_scale_controls()
        self._refresh_solution()

    def _set_row_visible(self, widget: QtWidgets.QWidget, visible: bool) -> None:
        widget.setVisible(visible)
        label = self._options_layout.labelForField(widget)
        if label:
            label.setVisible(visible)

    def _on_pp_offset_toggled(self) -> None:
        mode = self._get_current_mode()
        show_pp = self._use_pp_offset.isChecked()
        # Hide PP crosshair if it's being auto-calculated so the user isn't confused
        if mode == "3vp" and self._auto_pp.isChecked():
            show_pp = False
        self._canvas.set_principal_point_visible(show_pp)
        self._refresh_solution()

    def _on_scale_mode_changed(self, *args) -> None:
        if self._uses_box_dimension() and self._canvas.mode() != "box":
            self._match_type_combo.setCurrentText("Box Match")
        self._update_scale_controls()
        self._refresh_solution()

    def _uses_box_dimension(self) -> bool:
        return self._scale_mode.currentText() == BOX_DIMENSION_SCALE_MODE

    def _update_scale_controls(self) -> None:
        uses_box_dimension = self._uses_box_dimension()
        mode = self._get_current_mode()
        
        # Distance only enabled in arbitrary mode
        self._set_row_visible(self._camera_dist_row, not uses_box_dimension)
        self._camera_distance.setEnabled(not uses_box_dimension)
        
        # Box calibration controls only visible in box mode AND box scale mode
        show_box_scale = uses_box_dimension and mode == "box"
        self._set_row_visible(self._box_dimension_axis, show_box_scale)
        self._box_dimension_axis.setEnabled(show_box_scale)
        self._set_row_visible(self._box_dim_row, show_box_scale)
        self._box_dimension_length.setEnabled(show_box_scale)
        
        # Only show Box Scale mode in the combo if we are in Box mode? 
        # Actually, let's keep it visible but maybe warn if selected in other modes.
        # The existing _on_scale_mode_changed already forces mode to "Box" if box scale is selected.
        
        self._canvas.set_reference_visible(False)

    def _use_selected_read(self) -> None:
        try:
            self._plate = get_selected_read()
            pixmap = self._load_plate_pixmap(self._plate)
            self._canvas.set_plate(self._plate.width, self._plate.height, pixmap)
            suffix = "" if not pixmap.isNull() else " (preview unavailable)"
            self._plate_label.setText(
                f"{self._plate.node_name}: {self._plate.width}x{self._plate.height}{suffix}"
            )
            self._refresh_solution()
        except NodeSelectionError as error:
            self._show_error(str(error))

    def _load_plate_pixmap(self, plate: PlateInfo) -> QtGui.QPixmap:
        pixmap = QtGui.QPixmap(plate.file_path) if plate.file_path else QtGui.QPixmap()
        if not pixmap.isNull():
            self._plate_label.setToolTip("")
            return pixmap
        try:
            image = QtGui.QImage.fromData(render_plate_preview(plate), "PNG")
            if image.isNull():
                raise PreviewRenderError("Qt could not decode the rendered PNG preview.")
            self._plate_label.setToolTip("")
            return QtGui.QPixmap.fromImage(image)
        except PreviewRenderError as error:
            self._plate_label.setToolTip(str(error))
            return QtGui.QPixmap()

    def _on_live_change(self, *args) -> None:
        """React to a continuous edit: cheap preview now, heavy solve later.

        Runs a lightweight solve immediately so the overlay tracks the drag,
        then (re)arms the debounce timer. The expensive scale calibration and
        the Nuke state write only happen once the user pauses (see
        ``_on_refresh_timeout``), instead of on every dragged pixel.
        """
        self._refresh_solution(full=False)
        self._refresh_timer.start()

    def _on_refresh_timeout(self) -> None:
        self._refresh_solution(full=True)

    def _flush_pending_refresh(self) -> None:
        """Run any debounced full refresh now instead of waiting for the timer.

        The cheap live path defers the heavy solve and the Nuke state write to
        the debounce timeout. If the panel is closed inside that window the
        timer is destroyed and the last edit would never be persisted, leaving
        the saved knob (and the cached scale calibration) stale. Flush on close.
        """
        if self._refresh_timer.isActive():
            self._refresh_solution(full=True)

    def closeEvent(self, event) -> None:
        self._flush_pending_refresh()
        super().closeEvent(event)

    def _refresh_solution(self, *args, full: bool = True) -> SolveResult:
        if full:
            # A synchronous full refresh supersedes any pending debounced one.
            self._refresh_timer.stop()

        dimensions = self._plate or PlateInfo(None, "", 1920, 1080, "")

        # Update canvas labels based on current axis selection
        axis1 = self._first_axis.currentText()
        axis2 = self._second_axis.currentText()
        axis3 = self._third_axis.currentText()
        self._canvas.set_axis_labels(axis1, axis2, axis3)

        mode_str = self._get_current_mode()

        # Determine Principal Point input
        principal_point: Point2D | None
        if mode_str == "3vp" and self._auto_pp.isChecked():
            principal_point = None # Triggers auto-calculation
        elif self._use_pp_offset.isChecked():
            principal_point = self._canvas.principal_point()
        else:
            principal_point = DEFAULT_PRINCIPAL_POINT # Force centered

        mode = self._canvas.mode()
        uses_box_dimension = (mode == "box" and self._uses_box_dimension())

        # On the cheap path we skip recalibration and reuse the last solved
        # camera distance, so the grid holds its scale while the box is dragged.
        if uses_box_dimension and not full and self._last_box_dimension is not None:
            effective_distance = self._last_box_dimension.camera_distance
        else:
            effective_distance = self._camera_distance.value()

        solve_input = SolveInput(
            image_width=dimensions.width,
            image_height=dimensions.height,
            vp1_segments=self._canvas.vp1_segments(),
            vp2_segments=self._canvas.vp2_segments(),
            vp3_segments=self._canvas.vp3_segments(),
            principal_point=principal_point,
            origin=self._canvas.origin(),
            first_axis=axis1,
            second_axis=axis2,
            third_axis=axis3,
            sensor_width_mm=self._sensor_width.value(),
            known_focal_length_mm=self._focal_length.value() if mode_str == "1vp" else None,
            flip_world_up=self._flip_world_up.isChecked(),
            camera_distance=effective_distance,
            mode=mode_str,
        )
        scale_error = None
        if mode == "box":
            corners = self._canvas.match_box_corners()
            if uses_box_dimension:
                if full:
                    try:
                        self._last_result, self._last_box_dimension = (
                            solve_box_match_with_dimension(
                                solve_input,
                                corners,
                                BoxDimensionInput(
                                    axis=self._box_dimension_axis.currentText(),
                                    length=self._box_dimension_length.value(),
                                ),
                                base_plane_offset=self._match_box_base_offset.value(),
                            )
                        )
                    except GeometryError as error:
                        self._last_result = solve_box_match(solve_input, corners)
                        self._last_box_dimension = None
                        scale_error = str(error)
                else:
                    # Cheap preview at the cached scale; no recalibration. Keep
                    # the previous calibration so the message stays consistent.
                    self._last_result = solve_box_match(solve_input, corners)
            else:
                self._last_result = solve_box_match(solve_input, corners)
                self._last_box_dimension = None
        else:
            self._last_result = solve_2vp(solve_input)
            self._last_box_dimension = None

        if self._last_result.ok:
            # Update canvas principal point if it was auto-calculated
            if principal_point is None:
                self._canvas.set_principal_point(self._last_result.principal_point_ui)
        
        if scale_error is not None:
            self._show_error(scale_error)
        elif self._last_result.ok:
            assert self._last_result.focal_length_mm is not None
            assert self._last_result.horizontal_fov_radians is not None
            parts = [
                f"Ready. Focal: {self._last_result.focal_length_mm:.3f} mm, "
                f"horizontal FOV: {degrees(self._last_result.horizontal_fov_radians):.2f} deg."
            ]
            if self._last_box_dimension is not None:
                parts.append(
                    "Scene scale: estimated from match-box "
                    f"{self._last_box_dimension.axis} = "
                    f"{self._last_box_dimension.length:g} world units."
                )
            warnings = " ".join(self._last_result.warnings)
            if warnings:
                parts.append(warnings)
            self._message.setText(" ".join(parts))
            self._message.setStyleSheet("color: #c6e6c6;")
        else:
            self._show_error(" ".join(self._last_result.errors))

        # Draw perspective grid on canvas
        self._canvas.update_grid(self._last_result, axis1, axis2, refresh_lines=False)

        # Persisting on the cheap path would write the Nuke knob (and mark the
        # script modified) on every dragged pixel; defer it to the full refresh.
        if full:
            self._save_state_to_nuke()
        return self._last_result

    def _load_state_from_nuke(self) -> None:
        state = load_state()
        if not state:
            return
        
        try:
            # Restore UI controls
            if "match_type" in state:
                self._match_type_combo.setCurrentText(state["match_type"])
            if "vp2_enable" in state:
                self._vp2_enable.setChecked(state["vp2_enable"])
            if "vp3_enable" in state:
                self._vp3_enable.setChecked(state["vp3_enable"])
                
            # Legacy state migration
            if "vp_count" in state and "vp2_enable" not in state:
                vp_count = state["vp_count"]
                if vp_count == "1 VP":
                    self._vp2_enable.setChecked(False)
                    self._vp3_enable.setChecked(False)
                elif vp_count == "2 VPs":
                    self._vp2_enable.setChecked(True)
                    self._vp3_enable.setChecked(False)
                elif vp_count == "3 VPs":
                    self._vp2_enable.setChecked(True)
                    self._vp3_enable.setChecked(True)

            if "mode" in state and "match_type" not in state:
                old_mode = state["mode"].lower()
                if old_mode == "box":
                    self._match_type_combo.setCurrentText("Box Match")
                elif old_mode == "1vp":
                    self._match_type_combo.setCurrentText("Vanishing Points")
                    self._vp2_enable.setChecked(False)
                    self._vp3_enable.setChecked(False)
                elif old_mode == "2vp":
                    self._match_type_combo.setCurrentText("Vanishing Points")
                    self._vp2_enable.setChecked(True)
                    self._vp3_enable.setChecked(False)
                elif old_mode == "3vp":
                    self._match_type_combo.setCurrentText("Vanishing Points")
                    self._vp2_enable.setChecked(True)
                    self._vp3_enable.setChecked(True)

            if "first_axis" in state:
                self._first_axis.setCurrentText(axis_letter(state["first_axis"]))
            if "second_axis" in state:
                self._second_axis.setCurrentText(axis_letter(state["second_axis"]))
            if "third_axis" in state:
                self._third_axis.setCurrentText(axis_letter(state["third_axis"]))
            if "auto_pp" in state:
                self._auto_pp.setChecked(state["auto_pp"])
            if "use_pp_offset" in state:
                self._use_pp_offset.setChecked(state["use_pp_offset"])
            if "flip_world_up" in state:
                self._flip_world_up.setChecked(state["flip_world_up"])
            if "sensor_width" in state:
                self._sensor_width.setValue(state["sensor_width"])
            if "focal_length" in state:
                self._focal_length.setValue(state["focal_length"])
            if "scale_mode" in state:
                self._scale_mode.setCurrentText(state["scale_mode"])
            if "camera_distance" in state:
                self._camera_distance.setValue(state["camera_distance"])
            if "box_dimension_axis" in state:
                self._box_dimension_axis.setCurrentText(state["box_dimension_axis"])
            if "box_dimension_length" in state:
                self._box_dimension_length.setValue(state["box_dimension_length"])
            if "match_box_base_offset" in state:
                self._match_box_base_offset.setValue(state["match_box_base_offset"])
            
            # Restore Canvas state
            if "canvas" in state:
                canvas_state = state["canvas"]
                if state.get("directed_vp_lines_version") != DIRECTED_VP_LINES_STATE_VERSION:
                    principal_point = None
                    if not state.get("auto_pp", True):
                        principal_point = DEFAULT_PRINCIPAL_POINT
                        if state.get("use_pp_offset"):
                            values = canvas_state.get("principal_point")
                            if values is not None:
                                principal_point = Point2D(values["x"], values["y"])
                    canvas_state = migrate_legacy_canvas_directions(
                        canvas_state,
                        first_axis=state.get("first_axis", "+X"),
                        second_axis=state.get("second_axis", "+Z"),
                        third_axis=state.get("third_axis", "+Y"),
                        mode=self._get_current_mode(),
                        principal_point=principal_point,
                    )
                self._canvas.set_state(canvas_state)
        except (KeyError, TypeError, ValueError):
            return

    def _save_state_to_nuke(self) -> None:
        if self._is_loading_state:
            return
            
        state = {
            "match_type": self._match_type_combo.currentText(),
            "vp2_enable": self._vp2_enable.isChecked(),
            "vp3_enable": self._vp3_enable.isChecked(),
            "first_axis": self._first_axis.currentText(),
            "second_axis": self._second_axis.currentText(),
            "third_axis": self._third_axis.currentText(),
            "auto_pp": self._auto_pp.isChecked(),
            "use_pp_offset": self._use_pp_offset.isChecked(),
            "flip_world_up": self._flip_world_up.isChecked(),
            "sensor_width": self._sensor_width.value(),
            "focal_length": self._focal_length.value(),
            "scale_mode": self._scale_mode.currentText(),
            "camera_distance": self._camera_distance.value(),
            "box_dimension_axis": self._box_dimension_axis.currentText(),
            "box_dimension_length": self._box_dimension_length.value(),
            "match_box_base_offset": self._match_box_base_offset.value(),
            "directed_vp_lines_version": DIRECTED_VP_LINES_STATE_VERSION,
            "canvas": self._canvas.get_state(),
        }
        save_state(state)

    def _create_camera(self) -> None:
        try:
            result = self._refresh_solution()
            self._require_scene_scale()
            camera = create_camera(result)
            self._message.setText(f"Created Camera2 node: {camera.name()}")
            self._message.setStyleSheet("color: #c6e6c6;")
        except (CameraAdapterError, GeometryError) as error:
            self._show_error(str(error))

    def _update_camera(self) -> None:
        try:
            result = self._refresh_solution()
            self._require_scene_scale()
            camera = get_selected_camera()
            update_camera(camera, result)
            self._message.setText(f"Updated Camera2 node: {camera.name()}")
            self._message.setStyleSheet("color: #c6e6c6;")
        except (CameraAdapterError, GeometryError, NodeSelectionError) as error:
            self._show_error(str(error))

    def _create_scene_grid(self) -> None:
        try:
            grid = create_scene_grid()
            self._show_success(f"Created scene grid: {grid.card.name()}")
        except SceneHelperError as error:
            self._show_error(str(error))

    def _create_origin_card(self) -> None:
        try:
            card = create_origin_card()
            self._show_success(f"Created origin card: {card.name()}")
        except SceneHelperError as error:
            self._show_error(str(error))

    def _create_match_box(self) -> None:
        try:
            if self._canvas.mode() != "box":
                raise SceneHelperError("Switch Matching Mode to Box before creating a match box.")
            result = self._refresh_solution()
            self._require_scene_scale()
            match_box = reconstruct_match_box(
                result,
                self._canvas.match_box_corners(),
                self._first_axis.currentText(),
                self._second_axis.currentText(),
                base_plane_offset=self._match_box_base_offset.value(),
            )
            cube = create_match_box(match_box)
            warning = f" {' '.join(match_box.warnings)}" if match_box.warnings else ""
            self._show_success(f"Created match box: {cube.name()}.{warning}")
        except (GeometryError, SceneHelperError) as error:
            self._show_error(str(error))

    def _show_success(self, message: str) -> None:
        self._message.setText(message)
        self._message.setStyleSheet("color: #c6e6c6;")

    def _show_error(self, message: str) -> None:
        self._message.setText(message)
        self._message.setStyleSheet("color: #ff9999;")

    def _require_scene_scale(self) -> None:
        if self._uses_box_dimension() and self._last_box_dimension is None:
            raise GeometryError("Could not estimate scene scale from the current match box.")
