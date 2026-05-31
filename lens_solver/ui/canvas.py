"""Editable perspective-line canvas for the Lens Solver panel."""

from __future__ import annotations

from collections.abc import Iterable

from PySide2 import QtCore, QtGui, QtWidgets

from lens_solver.core.models import Point2D, Segment2D


HANDLE_RADIUS = 8.0


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
        self.setMinimumHeight(320)
        
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
        self._create_segment("vp1_a", Point2D(0.12, 0.23), Point2D(0.77, 0.34), "#ff5c5c")
        self._create_segment("vp1_b", Point2D(0.20, 0.70), Point2D(0.95, 0.59), "#ff5c5c")
        self._create_segment("vp2_a", Point2D(0.30, 0.40), Point2D(0.25, 0.14), "#5ca8ff")
        self._create_segment("vp2_b", Point2D(0.80, 0.80), Point2D(0.61, 0.21), "#5ca8ff")
        self._handles["origin"] = self._create_handle(Point2D(0.5, 0.5), "#ffd45c")
        self.set_plate(1920, 1080)

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
        self.fitInView(self._plate_rect, QtCore.Qt.KeepAspectRatio)

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
        self._handles[f"{name}_start"] = self._create_handle(start, color)
        self._handles[f"{name}_end"] = self._create_handle(end, color)

    def _create_handle(self, point: Point2D, color: str) -> _HandleItem:
        handle = _HandleItem(point, QtGui.QColor(color), self._plate_rect)
        handle.signals.moved.connect(self._handle_moved)
        self._scene.addItem(handle)
        return handle

    def _handle_moved(self) -> None:
        self._update_lines()
        self.changed.emit()

    def _update_lines(self) -> None:
        for name, line in self._lines.items():
            start_handle = self._handles[f"{name}_start"]
            end_handle = self._handles[f"{name}_end"]
            
            p1 = start_handle.pos()
            p2 = end_handle.pos()
            
            # Vector from start to end
            dx = p2.x() - p1.x()
            dy = p2.y() - p1.y()
            length = (dx*dx + dy*dy)**0.5
            
            if length > HANDLE_RADIUS * 2.0:
                # Offset points by handle radius along the segment direction
                # Note: We need to account for current view scale if we want
                # the gap to perfectly match the non-scaling handle circle.
                # Since handles ignore transformations, HANDLE_RADIUS is in screen pixels.
                # We need to map screen distance back to scene distance.
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
