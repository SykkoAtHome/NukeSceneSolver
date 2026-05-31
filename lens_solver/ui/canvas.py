"""Editable perspective-line canvas for the Lens Solver panel."""

from __future__ import annotations

from collections.abc import Iterable

from PySide2 import QtCore, QtGui, QtWidgets

from lens_solver.core import SolveResult
from lens_solver.core.models import Point2D, Segment2D


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
}


class _HandleSignals(QtCore.QObject):
    moved = QtCore.Signal()


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


class LensSolverCanvas(QtWidgets.QGraphicsView):
    """QGraphicsView canvas that exposes four VP segments and one origin."""

    changed = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor("#202225")))
        
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

        self._handles: dict[str, _HandleItem] = {}
        self._lines: dict[str, QtWidgets.QGraphicsLineItem] = {}
        self._labels: dict[str, QtWidgets.QGraphicsSimpleTextItem] = {}
        self._grid_lines: list[QtWidgets.QGraphicsLineItem] = []
        self._grid_visible = True
        self._undo_buffer: dict[str, Point2D] | None = None
        self._is_internal_update = False
        
        self._create_segment("vp1_a", Point2D(0.12, 0.23), Point2D(0.77, 0.34), "#ff5c5c")
        self._create_segment("vp1_b", Point2D(0.20, 0.70), Point2D(0.95, 0.59), "#ff5c5c")
        self._create_segment("vp2_a", Point2D(0.30, 0.40), Point2D(0.25, 0.14), "#5ca8ff")
        self._create_segment("vp2_b", Point2D(0.80, 0.80), Point2D(0.61, 0.21), "#5ca8ff")
        self._handles["origin"] = self._create_handle(Point2D(0.5, 0.5), "#ffd45c")
        
        self._setup_hud()
        self.set_plate(1920, 1080)

    def set_axis_labels(self, axis1: str, axis2: str) -> None:
        """Update labels to reflect assigned world axes."""
        for name in ("vp1_a", "vp1_b"):
            self._labels[name].setText(f"{axis1.strip('+-')} Axis")
        for name in ("vp2_a", "vp2_b"):
            self._labels[name].setText(f"{axis2.strip('+-')} Axis")
        self._update_lines()

    def update_grid(self, result: SolveResult | None) -> None:
        """Draw a perspective grid on the ground plane if the solve is valid."""
        # Clear existing grid
        while self._grid_lines:
            self._scene.removeItem(self._grid_lines.pop())

        if not self._grid_visible or not result or not result.ok or not result.projection_matrix:
            return

        # Simple grid: 10x10 units on the ground plane (Z=0 if Y is up, or Y=0 if Z is up)
        # We need to know which axis is "up".
        # For simplicity, let's assume world plane formed by axis1 and axis2.
        
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 80), 1.0)
        pen.setCosmetic(True)
        
        proj = result.projection_matrix
        w, h = self._plate_rect.width(), self._plate_rect.height()

        def project(xw: float, yw: float, zw: float) -> QtCore.QPointF | None:
            # result.projection_matrix.rows is a tuple of tuples
            p = (xw, yw, zw, 1.0)
            out = [0.0, 0.0, 0.0, 0.0]
            for i in range(4):
                row = proj.rows[i]
                for j in range(4):
                    out[i] += row[j] * p[j]
            
            if abs(out[3]) < 1e-6: return None
            
            nx = out[0] / out[3]
            ny = out[1] / out[3]
            
            return QtCore.QPointF(
                self._plate_rect.left() + (nx + 1.0) * 0.5 * w,
                self._plate_rect.top() + (1.0 - (ny + 1.0) * 0.5) * h
            )

        steps = 10
        size = 5.0
        for i in range(steps + 1):
            val = -size + (i * size * 2.0 / steps)
            # Lines along Axis 1
            p_start = project(val, -size, 0)
            p_end = project(val, size, 0)
            if p_start and p_end:
                line = self._scene.addLine(QtCore.QLineF(p_start, p_end), pen)
                line.setZValue(0.5)
                self._grid_lines.append(line)
                
            # Lines along Axis 2
            p_start = project(-size, val, 0)
            p_end = project(size, val, 0)
            if p_start and p_end:
                line = self._scene.addLine(QtCore.QLineF(p_start, p_end), pen)
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
        
        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._reset_btn.setStyleSheet(self._hud_style)
        self._reset_btn.clicked.connect(self.reset_handles)
        
        hud_layout.addWidget(self._fit_btn)
        hud_layout.addWidget(self._100_btn)
        hud_layout.addWidget(self._grid_btn)
        hud_layout.addWidget(self._reset_btn)

    def toggle_grid(self) -> None:
        """Toggle perspective grid visibility."""
        self._grid_visible = not self._grid_visible
        self._grid_btn.setChecked(self._grid_visible)
        for line in self._grid_lines:
            line.setVisible(self._grid_visible)

    def reset_handles(self) -> None:
        """Reset handles to defaults or undo the last reset."""
        self._is_internal_update = True
        try:
            if self._undo_buffer is None:
                # First click: Store current state and reset to defaults
                self._undo_buffer = {
                    name: h.relative_position() for name, h in self._handles.items()
                }
                for name, pos in DEFAULT_POSITIONS.items():
                    self._handles[name].set_relative_position(pos)
                self._reset_btn.setText("Undo Reset")
                self._reset_btn.setStyleSheet(
                    self._hud_style + " QPushButton { color: #ffcc66; }"
                )
            else:
                # Second click: Restore from buffer
                for name, pos in self._undo_buffer.items():
                    self._handles[name].set_relative_position(pos)
                self._undo_buffer = None
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
                handle.set_relative_position(relative_positions[name])
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

    def vp1_segments(self) -> tuple[Segment2D, Segment2D]:
        return self._segments("vp1_a", "vp1_b")

    def vp2_segments(self) -> tuple[Segment2D, Segment2D]:
        return self._segments("vp2_a", "vp2_b")

    def origin(self) -> Point2D:
        return self._handles["origin"].relative_position()

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
        
        # Add label
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
        if not self._is_internal_update and self._undo_buffer is not None:
            # User moved something after a reset: invalidate undo
            self._undo_buffer = None
            self._reset_btn.setText("Reset")
            self._reset_btn.setStyleSheet(self._hud_style)

        self._update_lines()
        self.changed.emit()

    def _update_lines(self) -> None:
        for name, line in self._lines.items():
            start_handle = self._handles[f"{name}_start"]
            end_handle = self._handles[f"{name}_end"]
            label = self._labels[name]
            
            p1 = start_handle.pos()
            p2 = end_handle.pos()
            
            # Vector from start to end
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = (dx*dx + dy*dy)**0.5
            
            # Update label position (center of segment)
            center = QtCore.QPointF(p1.x() + dx * 0.5, p1.y() + dy * 0.5)
            # Offset label so it's centered on the point
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
