"""Dockable Lens Solver panel for Nuke 15.1."""

from __future__ import annotations

from math import degrees

from PySide2 import QtCore, QtGui, QtWidgets

from lens_solver.core import (
    GeometryError,
    ReferenceDistanceInput,
    SolveInput,
    SolveResult,
    reconstruct_match_box,
    solve_2vp,
    solve_box_match,
)
from lens_solver.nuke_integration import (
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
    render_plate_preview,
    update_camera,
)
from lens_solver.ui.canvas import LensSolverCanvas


AXES = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")


class LensSolverPanel(QtWidgets.QWidget):
    """Interactive 2VP camera-matching panel."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._plate: PlateInfo | None = None
        self._last_result: SolveResult | None = None
        self._build_ui()
        self._connect_signals()
        self._refresh_solution()

    def _build_ui(self) -> None:
        self.setWindowTitle("Lens Solver")
        layout = QtWidgets.QVBoxLayout(self)

        plate_row = QtWidgets.QHBoxLayout()
        self._plate_label = QtWidgets.QLabel("No Read selected")
        self._use_read_button = QtWidgets.QPushButton("Use Selected Read")
        plate_row.addWidget(self._plate_label, 1)
        plate_row.addWidget(self._use_read_button)
        layout.addLayout(plate_row)

        self._canvas = LensSolverCanvas()
        layout.addWidget(self._canvas, 1)

        options = QtWidgets.QFormLayout()
        self._mode_combo = QtWidgets.QComboBox()
        self._mode_combo.addItems(["Lines", "Box"])
        self._first_axis = QtWidgets.QComboBox()
        self._first_axis.addItems(AXES)
        self._second_axis = QtWidgets.QComboBox()
        self._second_axis.addItems(AXES)
        self._second_axis.setCurrentText("+Z")
        self._sensor_width = QtWidgets.QDoubleSpinBox()
        self._sensor_width.setRange(1.0, 200.0)
        self._sensor_width.setDecimals(3)
        self._sensor_width.setValue(36.0)
        self._sensor_width.setSuffix(" mm")
        self._camera_distance = QtWidgets.QDoubleSpinBox()
        self._camera_distance.setRange(0.01, 1000000.0)
        self._camera_distance.setDecimals(3)
        self._camera_distance.setValue(10.0)
        self._reference_enabled = QtWidgets.QCheckBox()
        self._reference_axis = QtWidgets.QComboBox()
        self._reference_axis.addItems(AXES)
        self._reference_length = QtWidgets.QDoubleSpinBox()
        self._reference_length.setRange(0.001, 1000000.0)
        self._reference_length.setDecimals(3)
        self._reference_length.setValue(1.0)
        self._match_box_base_offset = QtWidgets.QDoubleSpinBox()
        self._match_box_base_offset.setRange(-1000000.0, 1000000.0)
        self._match_box_base_offset.setDecimals(3)
        self._match_box_base_offset.setValue(0.0)
        self._match_box_base_offset.setToolTip(
            "Coordinate of the match-box base plane along the derived third axis. "
            "For the default +X/+Z ground axes this is the base Y coordinate."
        )
        options.addRow("Matching Mode", self._mode_combo)
        options.addRow("First VP axis", self._first_axis)
        options.addRow("Second VP axis", self._second_axis)
        options.addRow("Sensor width", self._sensor_width)
        options.addRow("Camera distance", self._camera_distance)
        options.addRow("Use reference distance", self._reference_enabled)
        options.addRow("Reference axis", self._reference_axis)
        options.addRow("Reference length", self._reference_length)
        options.addRow("Match box base offset", self._match_box_base_offset)
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
        self._mode_combo.currentTextChanged.connect(self._on_mode_changed)
        self._canvas.changed.connect(self._refresh_solution)
        self._first_axis.currentTextChanged.connect(self._refresh_solution)
        self._second_axis.currentTextChanged.connect(self._refresh_solution)
        self._sensor_width.valueChanged.connect(self._refresh_solution)
        self._camera_distance.valueChanged.connect(self._refresh_solution)
        self._reference_enabled.toggled.connect(self._on_reference_enabled_changed)
        self._reference_axis.currentTextChanged.connect(self._refresh_solution)
        self._reference_length.valueChanged.connect(self._refresh_solution)
        self._create_button.clicked.connect(self._create_camera)
        self._update_button.clicked.connect(self._update_camera)
        self._grid_button.clicked.connect(self._create_scene_grid)
        self._origin_card_button.clicked.connect(self._create_origin_card)
        self._match_box_button.clicked.connect(self._create_match_box)
        self._canvas.set_reference_visible(self._reference_enabled.isChecked())

    def _on_mode_changed(self, mode_str: str) -> None:
        self._canvas.set_mode(mode_str.lower())
        self._refresh_solution()

    def _on_reference_enabled_changed(self, enabled: bool) -> None:
        self._canvas.set_reference_visible(enabled)
        self._refresh_solution()

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

    def _refresh_solution(self, *args) -> SolveResult:
        dimensions = self._plate or PlateInfo(None, "", 1920, 1080, "")

        # Update canvas labels based on current axis selection
        axis1 = self._first_axis.currentText()
        axis2 = self._second_axis.currentText()
        self._canvas.set_axis_labels(axis1, axis2)
        reference_distance = None
        if self._reference_enabled.isChecked():
            reference_distance = ReferenceDistanceInput(
                segment_ui=self._canvas.reference_segment(),
                axis=self._reference_axis.currentText(),
                distance=self._reference_length.value(),
            )

        solve_input = SolveInput(
            image_width=dimensions.width,
            image_height=dimensions.height,
            vp1_segments=self._canvas.vp1_segments(),
            vp2_segments=self._canvas.vp2_segments(),
            origin=self._canvas.origin(),
            first_axis=axis1,
            second_axis=axis2,
            sensor_width_mm=self._sensor_width.value(),
            camera_distance=self._camera_distance.value(),
            reference_distance=reference_distance,
        )
        if self._canvas.mode() == "box":
            self._last_result = solve_box_match(solve_input, self._canvas.match_box_corners())
        else:
            self._last_result = solve_2vp(solve_input)
        if self._last_result.ok:
            assert self._last_result.focal_length_mm is not None
            assert self._last_result.horizontal_fov_radians is not None
            warnings = " ".join(self._last_result.warnings)
            scale_status = ""
            if self._last_result.reference_distance is not None:
                scale_status = (
                    f" Scale: {self._last_result.reference_distance.scale_factor:.4f}x."
                )
            self._message.setText(
                f"Ready. Focal: {self._last_result.focal_length_mm:.3f} mm, "
                f"horizontal FOV: {degrees(self._last_result.horizontal_fov_radians):.2f} deg. "
                f"{scale_status} {warnings}"
            )
            self._message.setStyleSheet("color: #c6e6c6;")
        else:
            self._show_error(" ".join(self._last_result.errors))

        # Draw perspective grid on canvas
        self._canvas.update_grid(self._last_result, axis1, axis2)
        
        return self._last_result

    def _create_camera(self) -> None:
        try:
            result = self._refresh_solution()
            camera = create_camera(result)
            self._message.setText(f"Created Camera2 node: {camera.name()}")
            self._message.setStyleSheet("color: #c6e6c6;")
        except CameraAdapterError as error:
            self._show_error(str(error))

    def _update_camera(self) -> None:
        try:
            result = self._refresh_solution()
            camera = get_selected_camera()
            update_camera(camera, result)
            self._message.setText(f"Updated Camera2 node: {camera.name()}")
            self._message.setStyleSheet("color: #c6e6c6;")
        except (CameraAdapterError, NodeSelectionError) as error:
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
