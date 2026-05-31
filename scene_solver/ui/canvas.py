"""Editable perspective-line canvas for the Scene Solver panel."""

from __future__ import annotations

from collections.abc import Iterable

from PySide2 import QtCore, QtGui, QtWidgets

from scene_solver.core import BOX_EDGES, SolveResult, box_axis_segments
from scene_solver.core.models import Point2D, Segment2D, Vector3D
from scene_solver.core.coordinates import ui_to_solver
from scene_solver.core.projection import solver_point_to_camera_ray


HANDLE_RADIUS = 8.0

DEFAULT_POSITIONS = {
    "vp1_a_start": Point2D(0.12, 0.23),
    "vp1_a_end": Point2D(0.77, 0.34),
    "vp1_b_start": Point2D(0.20, 0.70),
    "vp1_b_end": Point2D(0.95, 0.59),
    "vp2_a_start": Point2D(0.30, 0.40),
    "vp2_a_end": Point2D(0.25, 0.14),
    "vp2_b_start": Point2D(0.80, 0.80),
    "vp2_b_end": Point2D(0.61, 0.21),
    "origin": Point2D(0.5, 0.5),
    "reference_start": Point2D(0.50, 0.50),
    "reference_end": Point2D(0.65, 0.50),
    # 8 box vertices: v[x][y][z]
    "box_v000": Point2D(0.20, 0.80),
    "box_v100": Point2D(0.40, 0.80),
    "box_v010": Point2D(0.15, 0.70),
    "box_v110": Point2D(0.35, 0.70),
    "box_v001": Point2D(0.20, 0.60),
    "box_v101": Point2D(0.40, 0.60),
    "box_v011": Point2D(0.15, 0.50),
    "box_v111": Point2D(0.35, 0.50),
}


class _HandleSignals(QtCore.QObject):
    moved = QtCore.Signal()
    pressed = QtCore.Signal()
    released = QtCore.Signal()


class _HandleItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(
        self,
        relative_position: Point2D,
        color: QtGui.QColor,
        plate_rect: QtCore.QRectF,
    ) -> None:
        super().__init__(-HANDLE_RADIUS, -HANDLE_RADIUS, HANDLE_RADIUS * 2.0, HANDLE_RADIUS * 2.0)
        self.signals = _HandleSignals()
        self._plate_rect = plate_rect
        self._color = color
        
        # Style: Transparent body, thin cosmetic outline
        self.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
        pen = QtGui.QPen(color, 1.5)
        pen.setCosmetic(True)
        self.setPen(pen)
        
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self.setZValue(3.0)
        
        # Add a small dot in the middle (also ignores transformations)
        dot_radius = 1.5
        self._dot = QtWidgets.QGraphicsEllipseItem(
            -dot_radius, -dot_radius, dot_radius * 2.0, dot_radius * 2.0, self
        )
        self._dot.setBrush(QtGui.QBrush(color))
        self._dot.setPen(QtCore.Qt.NoPen)
        self._dot.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        
        self.set_relative_position(relative_position)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.signals.pressed.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.signals.released.emit()
        super().mouseReleaseEvent(event)

    def set_plate_rect(self, plate_rect: QtCore.QRectF) -> None:
        relative = self.relative_position()
        self._plate_rect = plate_rect
        self.set_relative_position(relative)

    def relative_position(self) -> Point2D:
        if self._plate_rect.width() == 0.0 or self._plate_rect.height() == 0.0:
            return Point2D(0.5, 0.5)
        return Point2D(
            (self.pos().x() - self._plate_rect.left()) / self._plate_rect.width(),
            (self.pos().y() - self._plate_rect.top()) / self._plate_rect.height(),
        )

    def set_relative_position(self, point: Point2D) -> None:
        self.setPos(
            self._plate_rect.left() + point.x * self._plate_rect.width(),
            self._plate_rect.top() + point.y * self._plate_rect.height(),
        )

    def itemChange(self, change, value):  # noqa: N802 - Qt API name
        if change == QtWidgets.QGraphicsItem.ItemPositionChange:
            point = value
            return QtCore.QPointF(
                min(max(point.x(), self._plate_rect.left()), self._plate_rect.right()),
                min(max(point.y(), self._plate_rect.top()), self._plate_rect.bottom()),
            )
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.signals.moved.emit()
        return super().itemChange(change, value)


class SceneSolverCanvas(QtWidgets.QGraphicsView):
    """QGraphicsView canvas that exposes four VP segments and one origin."""

    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#202225")))
        
        # State
        self._grid_visible = True
        self._horizon_visible = True
        self._reference_visible = False
        self._mode = "lines"
        self._undo_buffer: dict[str, Point2D] | None = None
        self._is_internal_update = False
        self._box_is_default = True
        self._last_box_positions: dict[str, Point2D] = {}
        self._is_dragging_box = False
        
        # HUD Elements placeholder
        self._fit_btn = None
        self._100_btn = None
        self._grid_btn = None
        self._horizon_btn = None
        self._reset_btn = None
        self._hud_style = ""
        
        # Initial aspect ratio hint: 16:9
        self.setMinimumWidth(400)
        self.setMinimumHeight(225) 
        
        # Interactive behavior
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)

        self._plate_rect = QtCore.QRectF(0.0, 0.0, 1920.0, 1080.0)
        self._plate_item = QtWidgets.QGraphicsPixmapItem()
        self._plate_item.setZValue(0.0)
        self._scene.addItem(self._plate_item)
        self._placeholder = self._scene.addText("Select a Read node to load a plate")
        self._placeholder.setDefaultTextColor(QtGui.QColor("#b8bcc2"))
        self._placeholder.setZValue(1.0)

        # Labels and Lines containers
        self._handles: dict[str, _HandleItem] = {}
        self._lines: dict[str, QtWidgets.QGraphicsLineItem] = {}
        self._labels: dict[str, QtWidgets.QGraphicsSimpleTextItem] = {}
        self._grid_lines: list[QtWidgets.QGraphicsLineItem] = []
        self._box_lines: list[QtWidgets.QGraphicsLineItem] = []
        horizon_pen = QtGui.QPen(QtGui.QColor("#ffcc66"), 1.0, QtCore.Qt.DashLine)
        horizon_pen.setCosmetic(True)
        self._horizon_line = self._scene.addLine(QtCore.QLineF(), horizon_pen)
        self._horizon_line.setZValue(1.0)
        self._horizon_line.setVisible(False)

        # Create handles and lines (temporarily disable updates during creation)
        self._is_internal_update = True
        try:
            self._create_segment("vp1_a", DEFAULT_POSITIONS["vp1_a_start"], DEFAULT_POSITIONS["vp1_a_end"], "#ff5c5c")
            self._create_segment("vp1_b", DEFAULT_POSITIONS["vp1_b_start"], DEFAULT_POSITIONS["vp1_b_end"], "#ff5c5c")
            self._create_segment("vp2_a", DEFAULT_POSITIONS["vp2_a_start"], DEFAULT_POSITIONS["vp2_a_end"], "#5ca8ff")
            self._create_segment("vp2_b", DEFAULT_POSITIONS["vp2_b_start"], DEFAULT_POSITIONS["vp2_b_end"], "#5ca8ff")
            self._handles["origin"] = self._create_handle(DEFAULT_POSITIONS["origin"], "#ffd45c")
            self._create_segment(
                "reference",
                DEFAULT_POSITIONS["reference_start"],
                DEFAULT_POSITIONS["reference_end"],
                "#ff9f5c",
            )
            self._labels["reference"].setText("Reference")
            self.set_reference_visible(False)
            
            # Create 8 box handles
            box_vnames = ("box_v000", "box_v100", "box_v010", "box_v110",
                          "box_v001", "box_v101", "box_v011", "box_v111")
            for name in box_vnames:
                # Color code: origin yellow, X red, Y blue, Z green, mixed white
                color = "#ffffff"
                if name == "box_v100": color = "#ff5c5c"
                if name == "box_v010": color = "#5ca8ff"
                if name == "box_v001": color = "#5cff5c"
                if name == "box_v000": color = "#ffd45c"
                
                self._handles[name] = self._create_handle(DEFAULT_POSITIONS[name], color)
                self._handles[name].setVisible(False)
                self._handles[name].signals.pressed.connect(self._on_box_pressed)
                self._handles[name].signals.released.connect(self._on_box_released)
            
            # Create lines for the 2D user polygon (dashed)
            for i, (v1, v2) in enumerate(BOX_EDGES):
                name = f"box_edge_{i}"
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 60), 1.0, QtCore.Qt.DashLine)
                pen.setCosmetic(True)
                line = self._scene.addLine(QtCore.QLineF(), pen)
                line.setZValue(1.5)
                line.setVisible(False)
                self._lines[name] = line
        finally:
            self._is_internal_update = False
            
        # Add Origin label
        self._origin_label = QtWidgets.QGraphicsSimpleTextItem("Scene Origin (0,0,0)")
        self._origin_label.setBrush(QtGui.QBrush(QtGui.QColor("#ffd45c")))
        self._origin_label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self._origin_label.setZValue(4.0)
        font = self._origin_label.font()
        font.setPixelSize(10)
        font.setBold(True)
        self._origin_label.setFont(font)
        self._scene.addItem(self._origin_label)
        
        self._setup_hud()
        self.set_plate(1920, 1080)
        self._update_lines() # Force initial positions

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        is_box = (mode == "box")
        
        # Standard VP handles and labels (Origin always visible)
        for name in ("vp1_a_start", "vp1_a_end", "vp1_b_start", "vp1_b_end",
                     "vp2_a_start", "vp2_a_end", "vp2_b_start", "vp2_b_end"):
            if name in self._handles:
                self._handles[name].setVisible(not is_box)
        
        if "origin" in self._handles:
            self._handles["origin"].setVisible(True)

        for name in ("vp1_a", "vp1_b", "vp2_a", "vp2_b"):
            if name in self._labels:
                self._labels[name].setVisible(not is_box)
            if name in self._lines:
                if not name.startswith("box_edge"):
                    self._lines[name].setVisible(not is_box)
                
        # Box handles
        box_vnames = ("box_v000", "box_v100", "box_v010", "box_v110",
                      "box_v001", "box_v101", "box_v011", "box_v111")
        for name in box_vnames:
            if name in self._handles:
                self._handles[name].setVisible(is_box)
        
        if is_box:
            self._box_is_default = True
            # Store current positions of ALL handles to detect deltas
            self._last_box_positions = {
                vname: self._handles[vname].relative_position() for vname in box_vnames
            }
                
        if hasattr(self, "_origin_label"):
            self._origin_label.setVisible(True)
        
        self._update_lines()
        self.changed.emit()

    def _on_box_pressed(self) -> None:
        if self._mode == "box" and self._box_is_default:
            self._is_dragging_box = True
            # Update cache before drag starts
            box_vnames = ("box_v000", "box_v100", "box_v010", "box_v110",
                          "box_v001", "box_v101", "box_v011", "box_v111")
            for name in box_vnames:
                self._last_box_positions[name] = self._handles[name].relative_position()

    def _on_box_released(self) -> None:
        if self._is_dragging_box:
            self._is_dragging_box = False
            self._box_is_default = False

    def set_axis_labels(self, axis1: str, axis2: str) -> None:
        """Update labels to reflect assigned world axes."""
        for name in ("vp1_a", "vp1_b"):
            if name in self._labels:
                self._labels[name].setText(f"{axis1.strip('+-')} Axis")
        for name in ("vp2_a", "vp2_b"):
            if name in self._labels:
                self._labels[name].setText(f"{axis2.strip('+-')} Axis")
        self._update_lines()

    def set_reference_visible(self, visible: bool) -> None:
        """Show reference-distance handles only while scale calibration is enabled."""
        self._reference_visible = visible
        for name in ("reference_start", "reference_end"):
            if name in self._handles:
                self._handles[name].setVisible(visible)
        if "reference" in self._labels:
            self._labels["reference"].setVisible(visible)
        if "reference" in self._lines:
            self._lines["reference"].setVisible(visible)

    def _unproject_length(self, ui_point: Point2D, world_axis: Vector3D, result: SolveResult) -> float:
        solver_pt = ui_to_solver(ui_point, result.image_dimensions, result.principal_point_ui)
        focal_plane_dist = result.relative_focal_length / 2.0
        try:
            camera_ray = solver_point_to_camera_ray(solver_pt, focal_plane_dist)
        except ValueError:
            return 0.0
        world_ray = result.camera_to_world_matrix.transform_direction(camera_ray).normalized()
        
        C = result.camera_position
        C_cross_R = C.cross(world_ray)
        D_cross_R = world_axis.cross(world_ray)
        denom = D_cross_R.dot(D_cross_R)
        if denom < 1e-9:
            return 0.0
        return C_cross_R.dot(D_cross_R) / denom

    def _get_axis_vector(self, axis_str: str) -> Vector3D:
        name = axis_str.strip("+-")
        sign = -1.0 if "-" in axis_str else 1.0
        if name == "X": return Vector3D(sign, 0.0, 0.0)
        if name == "Y": return Vector3D(0.0, sign, 0.0)
        return Vector3D(0.0, 0.0, sign)

    def update_grid(self, result: SolveResult | None, axis1: str = "+X", axis2: str = "+Z") -> None:
        """Draw a perspective grid on the ground plane if the solve is valid."""
        # Clear existing grid and box lines
        while self._grid_lines:
            self._scene.removeItem(self._grid_lines.pop())
        while self._box_lines:
            self._scene.removeItem(self._box_lines.pop())

        self._update_horizon(result)
        if not result or not result.ok or not result.projection_matrix:
            return

        proj = result.projection_matrix
        w, h = self._plate_rect.width(), self._plate_rect.height()
        pp = result.principal_point_ui
        aspect = result.image_dimensions.height_relative_to_width

        def project(xw: float, yw: float, zw: float) -> QtCore.QPointF | None:
            p = (xw, yw, zw, 1.0)
            out = [0.0, 0.0, 0.0, 0.0]
            for i in range(4):
                row = proj.rows[i]
                for j in range(4):
                    out[i] += row[j] * p[j]
            if abs(out[3]) < 1e-6: return None
            nx = out[0] / out[3]
            ny = out[1] / out[3]
            
            # Map solver-space nx, ny to UI-space [0, 1]
            ui_x = nx + pp.x
            ui_y = pp.y - ny / aspect
            
            return QtCore.QPointF(
                self._plate_rect.left() + ui_x * w,
                self._plate_rect.top() + ui_y * h
            )

        if not self._grid_visible:
            return

        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 80), 1.0)
        pen.setCosmetic(True)

        # Map grid coords [u, v] to world [x, y, z] based on selected axes
        try:
            ax1_name = axis1.strip("+-")
            ax2_name = axis2.strip("+-")
            ax_map = {"X": 0, "Y": 1, "Z": 2}
            ax1_idx = ax_map[ax1_name]
            ax2_idx = ax_map[ax2_name]
        except (KeyError, AttributeError):
            return

        steps = 10
        size = 5.0
        for i in range(steps + 1):
            val = -size + (i * size * 2.0 / steps)
            # Lines along ax1
            p3s, p3e = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            p3s[ax1_idx] = val; p3s[ax2_idx] = -size
            p3e[ax1_idx] = val; p3e[ax2_idx] = size
            ps, pe = project(*p3s), project(*p3e)
            if ps and pe:
                line = self._scene.addLine(QtCore.QLineF(ps, pe), pen)
                line.setZValue(0.5)
                self._grid_lines.append(line)
            # Lines along ax2
            p3s, p3e = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            p3s[ax2_idx] = val; p3s[ax1_idx] = -size
            p3e[ax2_idx] = val; p3e[ax1_idx] = size
            ps, pe = project(*p3s), project(*p3e)
            if ps and pe:
                line = self._scene.addLine(QtCore.QLineF(ps, pe), pen)
                line.setZValue(0.5)
                self._grid_lines.append(line)

    def _setup_hud(self) -> None:
        """Create floating HUD buttons."""
        hud_layout = QtWidgets.QHBoxLayout(self)
        hud_layout.setContentsMargins(10, 10, 10, 10)
        hud_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
        
        self._hud_style = """
            QPushButton {
                background-color: rgba(45, 45, 45, 180);
                color: #eeeeee;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                min-width: 40px;
            }
            QPushButton:hover {
                background-color: rgba(70, 70, 70, 220);
                border: 1px solid #888888;
            }
            QPushButton:pressed {
                background-color: rgba(30, 30, 30, 255);
            }
            QPushButton:checked {
                background-color: rgba(100, 150, 255, 150);
            }
        """
        
        self._fit_btn = QtWidgets.QPushButton("Fit")
        self._fit_btn.setStyleSheet(self._hud_style)
        self._fit_btn.clicked.connect(self.fit_view)
        
        self._100_btn = QtWidgets.QPushButton("1:1")
        self._100_btn.setStyleSheet(self._hud_style)
        self._100_btn.clicked.connect(self.reset_zoom)
        
        self._grid_btn = QtWidgets.QPushButton("Grid")
        self._grid_btn.setCheckable(True)
        self._grid_btn.setChecked(True)
        self._grid_btn.setStyleSheet(self._hud_style)
        self._grid_btn.clicked.connect(self.toggle_grid)

        self._horizon_btn = QtWidgets.QPushButton("Horizon")
        self._horizon_btn.setCheckable(True)
        self._horizon_btn.setChecked(True)
        self._horizon_btn.setStyleSheet(self._hud_style)
        self._horizon_btn.clicked.connect(self.toggle_horizon)
        
        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._reset_btn.setStyleSheet(self._hud_style)
        self._reset_btn.clicked.connect(self.reset_handles)
        
        hud_layout.addWidget(self._fit_btn)
        hud_layout.addWidget(self._100_btn)
        hud_layout.addWidget(self._grid_btn)
        hud_layout.addWidget(self._horizon_btn)
        hud_layout.addWidget(self._reset_btn)

    def toggle_grid(self) -> None:
        """Toggle perspective grid visibility."""
        self._grid_visible = not self._grid_visible
        if self._grid_btn:
            self._grid_btn.setChecked(self._grid_visible)
        for line in self._grid_lines:
            line.setVisible(self._grid_visible)

    def toggle_horizon(self) -> None:
        """Toggle the horizon overlay calculated from the first two VPs."""
        self._horizon_visible = not self._horizon_visible
        if self._horizon_btn:
            self._horizon_btn.setChecked(self._horizon_visible)
        self._horizon_line.setVisible(
            self._horizon_visible and not self._horizon_line.line().isNull()
        )

    def reset_handles(self) -> None:
        """Reset handles to defaults or undo the last reset."""
        self._is_internal_update = True
        try:
            if self._undo_buffer is None:
                self._undo_buffer = {
                    name: h.relative_position() for name, h in self._handles.items()
                }
                for name, pos in DEFAULT_POSITIONS.items():
                    self._handles[name].set_relative_position(pos)
                if self._reset_btn:
                    self._reset_btn.setText("Undo Reset")
                    self._reset_btn.setStyleSheet(
                        self._hud_style + " QPushButton { color: #ffcc66; }"
                    )
                self._box_is_default = True
            else:
                for name, pos in self._undo_buffer.items():
                    self._handles[name].set_relative_position(pos)
                self._undo_buffer = None
                if self._reset_btn:
                    self._reset_btn.setText("Reset")
                    self._reset_btn.setStyleSheet(self._hud_style)
        finally:
            self._is_internal_update = False

        self._update_lines()
        self.changed.emit()

    def fit_view(self) -> None:
        """Fit the entire plate into the current view."""
        self.fitInView(self._plate_rect, QtCore.Qt.KeepAspectRatio)

    def reset_zoom(self) -> None:
        """Reset zoom to 1:1 pixel ratio."""
        self.resetTransform()
        self.centerOn(self._plate_rect.center())

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802 - Qt API name
        zoom_in_factor = 1.25
        zoom_out_factor = 1.0 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 - Qt API name
        if event.button() == QtCore.Qt.MiddleButton:
            self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
            fake_event = QtGui.QMouseEvent(
                event.type(), event.pos(), QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton, event.modifiers()
            )
            super().mousePressEvent(fake_event)
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802 - Qt API name
        if event.button() == QtCore.Qt.MiddleButton:
            self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
            fake_event = QtGui.QMouseEvent(
                event.type(), event.pos(), QtCore.Qt.LeftButton,
                QtCore.Qt.LeftButton, event.modifiers()
            )
            super().mouseReleaseEvent(fake_event)
        else:
            super().mouseReleaseEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - Qt API name
        """Trigger line update on zoom/pan to keep handle-clipping accurate."""
        super().scrollContentsBy(dx, dy)
        self._update_lines()

    def set_plate(self, width: int, height: int, pixmap: QtGui.QPixmap | None = None) -> None:
        self._is_internal_update = True
        try:
            relative_positions = {
                name: handle.relative_position() for name, handle in self._handles.items()
            }
            self._plate_rect = QtCore.QRectF(0.0, 0.0, float(width), float(height))
            self._scene.setSceneRect(self._plate_rect)
            for name, handle in self._handles.items():
                handle.set_plate_rect(self._plate_rect)
                handle.set_relative_position(relative_positions.get(name, Point2D(0.5, 0.5)))
            if pixmap is not None and not pixmap.isNull():
                scaled = pixmap.scaled(
                    width,
                    height,
                    QtCore.Qt.IgnoreAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
                self._plate_item.setPixmap(scaled)
                self._placeholder.hide()
            else:
                self._plate_item.setPixmap(QtGui.QPixmap())
                self._placeholder.setPlainText("Plate preview unavailable - handles remain editable")
                self._placeholder.setPos(width * 0.03, height * 0.05)
                self._placeholder.show()
            self._update_lines()
            self.fit_view()
        finally:
            self._is_internal_update = False

    def origin(self) -> Point2D:
        return self._handles["origin"].relative_position()

    def reference_segment(self) -> Segment2D:
        return self._segment("reference")

    def match_box_corners(self) -> dict[str, Point2D]:
        return {
            name: self._handles[name].relative_position()
            for name in (
                "box_v000", "box_v100", "box_v010", "box_v110",
                "box_v001", "box_v101", "box_v011", "box_v111",
            )
        }

    def mode(self) -> str:
        return self._mode

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self.fitInView(self._plate_rect, QtCore.Qt.KeepAspectRatio)

    def _create_segment(
        self,
        name: str,
        start: Point2D,
        end: Point2D,
        color: str,
    ) -> None:
        pen = QtGui.QPen(QtGui.QColor(color), 1.5)
        pen.setCosmetic(True)
        line = self._scene.addLine(QtCore.QLineF(), pen)
        line.setZValue(2.0)
        self._lines[name] = line
        
        label = QtWidgets.QGraphicsSimpleTextItem("?")
        label.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        label.setZValue(4.0)
        font = label.font()
        font.setBold(True)
        font.setPixelSize(12)
        label.setFont(font)
        self._scene.addItem(label)
        self._labels[name] = label
        
        self._handles[f"{name}_start"] = self._create_handle(start, color)
        self._handles[f"{name}_end"] = self._create_handle(end, color)

    def _create_handle(self, point: Point2D, color: str) -> _HandleItem:
        handle = _HandleItem(point, QtGui.QColor(color), self._plate_rect)
        handle.signals.moved.connect(self._handle_moved)
        self._scene.addItem(handle)
        return handle

    def _handle_moved(self) -> None:
        if not self._is_internal_update:
            if self._undo_buffer is not None:
                self._undo_buffer = None
                if self._reset_btn:
                    self._reset_btn.setText("Reset")
                    self._reset_btn.setStyleSheet(self._hud_style)

            # Box interaction logic
            if self._mode == "box" and hasattr(self, "_last_box_positions"):
                box_vnames = ("box_v000", "box_v100", "box_v010", "box_v110",
                              "box_v001", "box_v101", "box_v011", "box_v111")
                
                # Find which handle moved
                moved_name = None
                dx, dy = 0.0, 0.0
                for name in box_vnames:
                    p = self._handles[name].relative_position()
                    last_p = self._last_box_positions.get(name)
                    if not last_p: continue
                    if abs(p.x - last_p.x) > 1e-7 or abs(p.y - last_p.y) > 1e-7:
                        moved_name = name
                        dx = p.x - last_p.x
                        dy = p.y - last_p.y
                        break
                
                if moved_name:
                    if self._is_dragging_box and self._box_is_default:
                        # Translate WHOLE box during the whole drag
                        self._is_internal_update = True
                        try:
                            for name in box_vnames:
                                if name == moved_name: continue
                                p = self._handles[name].relative_position()
                                self._handles[name].set_relative_position(Point2D(p.x + dx, p.y + dy))
                        finally:
                            self._is_internal_update = False
                    
                    # Update cache for next incremental move
                    for name in box_vnames:
                        self._last_box_positions[name] = self._handles[name].relative_position()

        # Update Origin label position
        if hasattr(self, "_origin_label") and "origin" in self._handles:
            origin_pos = self._handles["origin"].pos()
            self._origin_label.setPos(origin_pos.x() + 10, origin_pos.y() + 10)

        self._update_lines()
        self.changed.emit()

    def _update_lines(self) -> None:
        is_box = (getattr(self, "_mode", "lines") == "box")
        
        # 1. Update Box Edges visibility and positions
        for i, (v1, v2) in enumerate(BOX_EDGES):
            name = f"box_edge_{i}"
            if name in self._lines:
                if is_box:
                    if v1 in self._handles and v2 in self._handles:
                        self._lines[name].setLine(QtCore.QLineF(self._handles[v1].pos(), self._handles[v2].pos()))
                        self._lines[name].setVisible(True)
                else:
                    self._lines[name].setVisible(False)

        # 2. Update Standard VP Lines visibility and positions
        for name, line in self._lines.items():
            if name.startswith("box_edge_"):
                continue
            if name == "reference" and not self._reference_visible:
                line.setVisible(False)
                continue
            
            # Hide manual VP lines entirely in box mode. Reference line remains editable.
            if is_box and name in ("vp1_a", "vp1_b", "vp2_a", "vp2_b"):
                line.setVisible(False)
                continue

            if f"{name}_start" not in self._handles or f"{name}_end" not in self._handles:
                continue
            
            start_handle = self._handles[f"{name}_start"]
            end_handle = self._handles[f"{name}_end"]
            label = self._labels.get(name)
            
            p1 = start_handle.pos()
            p2 = end_handle.pos()
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = (dx*dx + dy*dy)**0.5
            
            if label:
                center = QtCore.QPointF(p1.x() + dx * 0.5, p1.y() + dy * 0.5)
                rect = label.boundingRect()
                label.setPos(center.x() - rect.width() * 0.5, center.y() - rect.height() * 0.5)
            
            if length > HANDLE_RADIUS * 2.0:
                inv_scale = 1.0 / self.transform().m11()
                scene_offset = HANDLE_RADIUS * inv_scale
                if length > scene_offset * 2.0:
                    ratio = scene_offset / length
                    p1_offset = QtCore.QPointF(p1.x() + dx * ratio, p1.y() + dy * ratio)
                    p2_offset = QtCore.QPointF(p2.x() - dx * ratio, p2.y() - dy * ratio)
                    line.setLine(QtCore.QLineF(p1_offset, p2_offset))
                    line.setVisible(True)
                else:
                    line.setVisible(False)
            else:
                line.setVisible(False)

    def _segments(self, *names: str) -> tuple[Segment2D, Segment2D]:
        return tuple(self._segment(name) for name in names)  # type: ignore[return-value]

    def _segment(self, name: str) -> Segment2D:
        return Segment2D(
            self._handles[f"{name}_start"].relative_position(),
            self._handles[f"{name}_end"].relative_position(),
        )

    def vp1_segments(self) -> tuple[Segment2D, ...]:
        if getattr(self, "_mode", "lines") == "box":
            return box_axis_segments(self.match_box_corners(), 0)
        return self._segments("vp1_a", "vp1_b")

    def vp2_segments(self) -> tuple[Segment2D, ...]:
        if getattr(self, "_mode", "lines") == "box":
            return box_axis_segments(self.match_box_corners(), 1)
        return self._segments("vp2_a", "vp2_b")

    def _update_horizon(self, result: SolveResult | None) -> None:
        if not result or not result.ok:
            self._horizon_line.setVisible(False)
            return
        first, second, _ = result.vanishing_points_ui
        if first is None or second is None:
            self._horizon_line.setVisible(False)
            return

        width = self._plate_rect.width()
        height = self._plate_rect.height()
        first_point = QtCore.QPointF(
            self._plate_rect.left() + first.x * width,
            self._plate_rect.top() + first.y * height,
        )
        second_point = QtCore.QPointF(
            self._plate_rect.left() + second.x * width,
            self._plate_rect.top() + second.y * height,
        )
        clipped = self._clip_infinite_line_to_plate(first_point, second_point)
        if clipped is None:
            self._horizon_line.setVisible(False)
            return
        self._horizon_line.setLine(QtCore.QLineF(*clipped))
        self._horizon_line.setVisible(self._horizon_visible)

    def _clip_infinite_line_to_plate(
        self,
        first: QtCore.QPointF,
        second: QtCore.QPointF,
    ) -> tuple[QtCore.QPointF, QtCore.QPointF] | None:
        dx = second.x() - first.x()
        dy = second.y() - first.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None

        left, right = self._plate_rect.left(), self._plate_rect.right()
        top, bottom = self._plate_rect.top(), self._plate_rect.bottom()
        candidates: list[QtCore.QPointF] = []

        if abs(dx) >= 1e-9:
            for x in (left, right):
                y = first.y() + (x - first.x()) * dy / dx
                if top - 1e-6 <= y <= bottom + 1e-6:
                    candidates.append(QtCore.QPointF(x, y))
        if abs(dy) >= 1e-9:
            for y in (top, bottom):
                x = first.x() + (y - first.y()) * dx / dy
                if left - 1e-6 <= x <= right + 1e-6:
                    candidates.append(QtCore.QPointF(x, y))

        unique: list[QtCore.QPointF] = []
        for point in candidates:
            if not any(
                abs(point.x() - existing.x()) < 1e-6
                and abs(point.y() - existing.y()) < 1e-6
                for existing in unique
            ):
                unique.append(point)
        if len(unique) < 2:
            return None
        return max(
            ((first_point, second_point) for first_point in unique for second_point in unique),
            key=lambda pair: QtCore.QLineF(*pair).length(),
        )
