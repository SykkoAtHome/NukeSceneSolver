"""Editable perspective-line canvas for the Scene Solver panel."""

from __future__ import annotations

from PySide2 import QtCore, QtGui, QtWidgets

from scene_solver.core import (
    BOX_CORNER_NAMES,
    BOX_EDGES,
    GeometryError,
    SolveResult,
    box_axis_segments,
)
from scene_solver.core.coordinates import solver_to_ui
from scene_solver.core.models import Point2D, Segment2D
from scene_solver.core.projection import world_plane_horizon_solver_line
from scene_solver.ui.axis_display import AXIS_COLORS, axis_arrow_heading, axis_color
from scene_solver.ui.snapping import nearest_snap_target


HANDLE_RADIUS = 8.0

# Box edges always use the fixed convention first=X, second=Z, height=Y. Map
# each of the three BOX_AXIS_EDGES families (in that order) to its world-axis
# colour in the shared Nuke-gizmo palette (AXIS_COLORS is indexed X=0, Y=1, Z=2).
BOX_FAMILY_WORLD_AXIS = (0, 2, 1)  # first->X, second->Z, height->Y

# Origin snap: target radius in screen pixels and the darkest the Dim overlay
# may push the plate (kept below 1.0 so the plate never fully disappears).
SNAP_THRESHOLD_PX = 15.0
DIM_MAX_ALPHA = 0.85


def _clip_segment_to_rect(
    start: QtCore.QPointF,
    end: QtCore.QPointF,
    rect: QtCore.QRectF,
) -> tuple[QtCore.QPointF, QtCore.QPointF] | None:
    """Clip the finite segment start->end to ``rect`` (Liang-Barsky).

    Returns the retained sub-segment, or None if the segment lies wholly
    outside the rectangle. Unlike _clip_infinite_line_to_canvas this keeps the
    segment's own extent rather than extending it to an infinite line.
    """
    x0, y0 = start.x(), start.y()
    dx, dy = end.x() - x0, end.y() - y0
    edges = (-dx, dx, -dy, dy)
    distances = (
        x0 - rect.left(),
        rect.right() - x0,
        y0 - rect.top(),
        rect.bottom() - y0,
    )
    enter, leave = 0.0, 1.0
    for edge, distance in zip(edges, distances):
        if abs(edge) < 1e-12:
            if distance < 0.0:
                return None  # parallel to this edge and outside it
            continue
        crossing = distance / edge
        if edge < 0.0:
            if crossing > leave:
                return None
            enter = max(enter, crossing)
        else:
            if crossing < enter:
                return None
            leave = min(leave, crossing)
    if enter > leave:
        return None
    return (
        QtCore.QPointF(x0 + enter * dx, y0 + enter * dy),
        QtCore.QPointF(x0 + leave * dx, y0 + leave * dy),
    )


# Axis-direction triad drawn from the box origin corner in Box mode:
# (arrow key, origin corner, destination corner, color matching the dest corner).
BOX_TRIAD = (
    ("box_triad_x", "box_v000", "box_v100", "#ff5c5c"),
    ("box_triad_z", "box_v000", "box_v010", "#5ca8ff"),
    ("box_triad_y", "box_v000", "box_v001", "#5cff5c"),
)

DEFAULT_POSITIONS = {
    "vp1_a_start": Point2D(0.12, 0.23),
    "vp1_a_end": Point2D(0.77, 0.34),
    "vp1_b_start": Point2D(0.20, 0.70),
    "vp1_b_end": Point2D(0.95, 0.59),
    "vp2_a_start": Point2D(0.25, 0.14),
    "vp2_a_end": Point2D(0.30, 0.40),
    "vp2_b_start": Point2D(0.61, 0.21),
    "vp2_b_end": Point2D(0.80, 0.80),
    "vp3_a_start": Point2D(0.35, 0.70),
    "vp3_a_end": Point2D(0.4964, 0.3765),
    "vp3_b_start": Point2D(0.55, 0.80),
    "vp3_b_end": Point2D(0.7464, 0.5015),
    "origin": Point2D(0.5, 0.5),
    "principal_point": Point2D(0.5, 0.5),
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
        movement_rect: QtCore.QRectF,
    ) -> None:
        super().__init__(-HANDLE_RADIUS, -HANDLE_RADIUS, HANDLE_RADIUS * 2.0, HANDLE_RADIUS * 2.0)
        self.signals = _HandleSignals()
        self._plate_rect = plate_rect
        self._movement_rect = movement_rect
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

    def set_color(self, color: QtGui.QColor) -> None:
        """Recolor the handle outline and centre dot."""
        self._color = color
        pen = QtGui.QPen(color, 1.5)
        pen.setCosmetic(True)
        self.setPen(pen)
        self._dot.setBrush(QtGui.QBrush(color))

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.signals.pressed.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:  # noqa: N802
        self.signals.released.emit()
        super().mouseReleaseEvent(event)

    def set_plate_rect(self, plate_rect: QtCore.QRectF, movement_rect: QtCore.QRectF) -> None:
        relative = self.relative_position()
        self._plate_rect = plate_rect
        self._movement_rect = movement_rect
        self.set_relative_position(relative)

    def set_movement_rect(self, movement_rect: QtCore.QRectF) -> None:
        """Update the visible area that bounds interactive dragging."""
        self._movement_rect = movement_rect

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
                min(max(point.x(), self._movement_rect.left()), self._movement_rect.right()),
                min(max(point.y(), self._movement_rect.top()), self._movement_rect.bottom()),
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
        self._extend_visible = False
        self._reference_visible = False
        self._snap_enabled = False
        self._dim_enabled = False
        self._mode = "lines"
        self._last_grid_result: SolveResult | None = None
        self._last_grid_axes = ("X", "Z")
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
        self._extend_btn = None
        self._snap_btn = None
        self._dim_btn = None
        self._dim_slider = None
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
        self._canvas_rect = self._plate_rect
        self._plate_item = QtWidgets.QGraphicsPixmapItem()
        self._plate_item.setZValue(0.0)
        self._scene.addItem(self._plate_item)
        # Dim overlay: semi-transparent black rect above the plate (z=0) but
        # below every overlay item (z>=1.0) so handles/lines stay full bright.
        self._dim_rect = QtWidgets.QGraphicsRectItem(self._plate_rect)
        self._dim_rect.setPen(QtCore.Qt.NoPen)
        self._dim_rect.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, 0)))
        self._dim_rect.setZValue(0.2)
        self._dim_rect.setVisible(False)
        self._scene.addItem(self._dim_rect)
        self._placeholder = self._scene.addText("Select a Read node to load a plate")
        self._placeholder.setDefaultTextColor(QtGui.QColor("#b8bcc2"))
        self._placeholder.setZValue(1.0)

        # Labels and Lines containers
        self._handles: dict[str, _HandleItem] = {}
        self._lines: dict[str, QtWidgets.QGraphicsLineItem] = {}
        self._extension_lines: dict[str, QtWidgets.QGraphicsLineItem] = {}
        self._arrows: dict[str, QtWidgets.QGraphicsPolygonItem] = {}
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
            self._create_segment("vp3_a", DEFAULT_POSITIONS["vp3_a_start"], DEFAULT_POSITIONS["vp3_a_end"], "#5cff5c")
            self._create_segment("vp3_b", DEFAULT_POSITIONS["vp3_b_start"], DEFAULT_POSITIONS["vp3_b_end"], "#5cff5c")
            self._labels["vp3_a"].setVisible(False)
            self._labels["vp3_b"].setVisible(False)
            for name in ("vp3_a_start", "vp3_a_end", "vp3_b_start", "vp3_b_end"):
                self._handles[name].setVisible(False)
            for name in ("vp3_a", "vp3_b"):
                self._lines[name].setVisible(False)

            self._handles["origin"] = self._create_handle(DEFAULT_POSITIONS["origin"], "#ffd45c")
            # Origin-only snap: runs after the shared _handle_moved slot, so a
            # snap reposition lands on the already-updated label/lines.
            self._handles["origin"].signals.moved.connect(self._snap_origin_if_enabled)
            self._handles["principal_point"] = self._create_handle(
                DEFAULT_POSITIONS["principal_point"], "#ffffff"
            )
            self._handles["principal_point"].setToolTip("Principal Point (Optical Center)")
            self._create_principal_point_crosshair()

            self._create_segment(
                "reference",
                DEFAULT_POSITIONS["reference_start"],
                DEFAULT_POSITIONS["reference_end"],
                "#ff9f5c",
            )
            self._labels["reference"].setText("Reference")
            self.set_reference_visible(False)

            # Create 8 box handles
            for name in BOX_CORNER_NAMES:
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
            
            # Create lines for the 2D user polygon (dashed). Each edge takes its
            # axis-family colour (first=X red, second=Z blue, height=Y green) so
            # the wireframe reads per axis; alpha is preserved from the prior
            # neutral pens so the box stays subtle against the plate.
            for i, (v1, v2) in enumerate(BOX_EDGES):
                name = f"box_edge_{i}"
                family_hex = AXIS_COLORS[BOX_FAMILY_WORLD_AXIS[i // 4]]
                edge_color = QtGui.QColor(family_hex)
                edge_color.setAlpha(60)
                pen = QtGui.QPen(edge_color, 1.0, QtCore.Qt.DashLine)
                pen.setCosmetic(True)
                line = self._scene.addLine(QtCore.QLineF(), pen)
                line.setZValue(1.5)
                line.setVisible(False)
                self._lines[name] = line
                ext_color = QtGui.QColor(family_hex)
                ext_color.setAlpha(90)
                self._extension_lines[name] = self._make_extension_line(ext_color)

            # Box origin-corner axis triad arrowheads (informational orientation
            # gizmo; Box mode resolves the actual sign internally).
            for key, _origin, _dest, color in BOX_TRIAD:
                arrow = QtWidgets.QGraphicsPolygonItem()
                arrow.setBrush(QtGui.QBrush(QtGui.QColor(color)))
                arrow.setPen(QtCore.Qt.NoPen)
                arrow.setZValue(2.5)
                arrow.setVisible(False)
                self._scene.addItem(arrow)
                self._arrows[key] = arrow
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
        
        # Add Principal Point label
        self._pp_label = QtWidgets.QGraphicsSimpleTextItem("Principal Point")
        self._pp_label.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
        self._pp_label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
        self._pp_label.setZValue(4.0)
        self._pp_label.setFont(font)
        self._scene.addItem(self._pp_label)
        
        self._setup_hud()
        self.set_plate(1920, 1080)
        self._update_lines() # Force initial positions

    def _create_principal_point_crosshair(self) -> None:
        pen = QtGui.QPen(QtGui.QColor("#ffffff"), 1.0)
        pen.setCosmetic(True)
        self._pp_lines = []
        for _ in range(2):
            line = self._scene.addLine(QtCore.QLineF(), pen)
            line.setZValue(1.5)
            line.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations)
            self._pp_lines.append(line)

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        is_box = (mode == "box")
        is_1vp = (mode == "1vp")
        is_3vp = (mode == "3vp")
        
        # Standard VP handles and labels (Origin always visible)
        for name in ("vp1_a_start", "vp1_a_end", "vp1_b_start", "vp1_b_end",
                     "vp2_a_start", "vp2_a_end", "vp2_b_start", "vp2_b_end",
                     "vp3_a_start", "vp3_a_end", "vp3_b_start", "vp3_b_end"):
            if name in self._handles:
                if name.startswith("vp3"):
                    self._handles[name].setVisible(is_3vp)
                elif name.startswith("vp2_b"):
                    self._handles[name].setVisible(not is_box and not is_1vp)
                else:
                    self._handles[name].setVisible(not is_box)
        
        if "origin" in self._handles:
            self._handles["origin"].setVisible(True)

        for name in ("vp1_a", "vp1_b", "vp2_a", "vp2_b", "vp3_a", "vp3_b"):
            if name in self._labels:
                if name.startswith("vp3"):
                    self._labels[name].setVisible(is_3vp)
                elif name.startswith("vp2_b"):
                    self._labels[name].setVisible(not is_box and not is_1vp)
                else:
                    self._labels[name].setVisible(not is_box)
            if name in self._lines:
                if not name.startswith("box_edge"):
                    if name.startswith("vp3"):
                        self._lines[name].setVisible(is_3vp)
                    elif name.startswith("vp2_b"):
                        self._lines[name].setVisible(not is_box and not is_1vp)
                    else:
                        self._lines[name].setVisible(not is_box)
                
        # Box handles
        for name in BOX_CORNER_NAMES:
            if name in self._handles:
                self._handles[name].setVisible(is_box)
        
        if is_box:
            self._box_is_default = True
            # Store current positions of ALL handles to detect deltas
            self._last_box_positions = {
                name: self._handles[name].relative_position() for name in BOX_CORNER_NAMES
            }
                
        if hasattr(self, "_origin_label"):
            self._origin_label.setVisible(True)
        
        self._update_lines()
        self.changed.emit()

    def _on_box_pressed(self) -> None:
        if self._mode == "box" and self._box_is_default:
            self._is_dragging_box = True
            # Update cache before drag starts
            for name in BOX_CORNER_NAMES:
                self._last_box_positions[name] = self._handles[name].relative_position()

    def _on_box_released(self) -> None:
        if self._is_dragging_box:
            self._is_dragging_box = False
            self._box_is_default = False

    def set_axis_labels(self, axis1: str, axis2: str, axis3: str = "Y") -> None:
        """Update labels and colours to reflect assigned world axes."""
        for group, axis in (("vp1", axis1), ("vp2", axis2), ("vp3", axis3)):
            for name in (f"{group}_a", f"{group}_b"):
                if name in self._labels:
                    self._labels[name].setText(f"{axis.strip('+-')} Axis")
            self._recolor_group(group, axis_color(axis))
        if self._mode == "1vp":
            self._labels["vp2_a"].setText("Horizon")
            self._recolor_group("vp2", "#ffcc66")
        self._update_lines()

    def _recolor_group(self, group: str, color: str) -> None:
        """Recolor every item of a VP group (lines, handles, label, arrow)."""
        qcolor = QtGui.QColor(color)
        for suffix in ("_a", "_b"):
            name = f"{group}{suffix}"
            if name in self._lines:
                pen = self._lines[name].pen()
                pen.setColor(qcolor)
                self._lines[name].setPen(pen)
            if name in self._extension_lines:
                pen = self._extension_lines[name].pen()
                pen.setColor(qcolor)
                self._extension_lines[name].setPen(pen)
            if name in self._arrows:
                self._arrows[name].setBrush(QtGui.QBrush(qcolor))
            if name in self._labels:
                self._labels[name].setBrush(QtGui.QBrush(qcolor))
            for end in ("_start", "_end"):
                handle = self._handles.get(f"{name}{end}")
                if handle is not None:
                    handle.set_color(qcolor)

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

    def set_principal_point_visible(self, visible: bool) -> None:
        """Show/hide the principal point handle and crosshair."""
        if "principal_point" in self._handles:
            self._handles["principal_point"].setVisible(visible)
        if hasattr(self, "_pp_label"):
            self._pp_label.setVisible(visible)
        if hasattr(self, "_pp_lines"):
            for line in self._pp_lines:
                line.setVisible(visible)

    def set_principal_point(self, point: Point2D) -> None:
        """Update the principal-point handle without emitting an intermediate solve."""

        self._is_internal_update = True
        try:
            self._handles["principal_point"].set_relative_position(point)
        finally:
            self._is_internal_update = False

    def update_grid(self, result: SolveResult | None, axis1: str = "X", axis2: str = "Z") -> None:
        """Draw a perspective grid on the ground plane if the solve is valid."""
        self._last_grid_result = result
        self._last_grid_axes = (axis1, axis2)
        self._refresh_canvas_rect()
        self._update_lines()

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
            # out[3] is the camera-space z of the world point. The camera looks
            # down -Z, so points in front are strictly negative; cull anything
            # at or behind the image plane to avoid mirrored grid lines.
            if out[3] > -1e-6: return None
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

        # Strictly in front of project()'s cull plane (-1e-6) so a clipped
        # endpoint still projects (its z stays clear of zero).
        near_plane_z = -1e-4

        def camera_z(point: tuple[float, float, float]) -> float:
            row = proj.rows[3]
            return row[0] * point[0] + row[1] * point[1] + row[2] * point[2] + row[3]

        def near_clip(first, second):
            """Clip world segment first->second to the half-space in front of the camera.

            A grid line straddling the camera plane would otherwise vanish
            entirely: project() culls the behind endpoint and add_grid_line drops
            any segment missing an endpoint. Cutting it at the near plane keeps
            the visible front portion instead of losing the whole line.
            """
            z1, z2 = camera_z(first), camera_z(second)
            first_front, second_front = z1 < near_plane_z, z2 < near_plane_z
            if not first_front and not second_front:
                return None
            if first_front and second_front:
                return first, second
            ratio = (near_plane_z - z1) / (z2 - z1)
            crossing = (
                first[0] + ratio * (second[0] - first[0]),
                first[1] + ratio * (second[1] - first[1]),
                first[2] + ratio * (second[2] - first[2]),
            )
            return (first, crossing) if first_front else (crossing, second)

        def add_grid_line(first, second) -> None:
            clipped = near_clip(first, second)
            if clipped is None:
                return
            start = project(*clipped[0])
            end = project(*clipped[1])
            if start is None or end is None:
                return
            # Projection diverges toward the near plane, so a clipped endpoint can
            # land astronomically far away; bound the drawn span to the visible
            # canvas to keep Qt's cosmetic pen well-conditioned.
            bounded = _clip_segment_to_rect(start, end, self._canvas_rect)
            if bounded is None:
                return
            line = self._scene.addLine(QtCore.QLineF(*bounded), pen)
            line.setZValue(0.5)
            self._grid_lines.append(line)

        # The overlay is always Nuke's horizontal ground plane: X/Z. The VP
        # dropdowns describe marked scene directions and may include world-up Y.
        ax1_idx, ax2_idx = 0, 2

        steps = 10
        size = 5.0
        for i in range(steps + 1):
            val = -size + (i * size * 2.0 / steps)
            # Lines along ax1
            p3s, p3e = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            p3s[ax1_idx] = val; p3s[ax2_idx] = -size
            p3e[ax1_idx] = val; p3e[ax2_idx] = size
            add_grid_line(p3s, p3e)
            # Lines along ax2
            p3s, p3e = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            p3s[ax2_idx] = val; p3s[ax1_idx] = -size
            p3e[ax2_idx] = val; p3e[ax1_idx] = size
            add_grid_line(p3s, p3e)

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

        self._extend_btn = QtWidgets.QPushButton("Extend")
        self._extend_btn.setCheckable(True)
        self._extend_btn.setChecked(self._extend_visible)
        self._extend_btn.setToolTip(
            "Extend visible VP lines and box edges to the image borders "
            "(dashed prolongation beyond the handles)."
        )
        self._extend_btn.setStyleSheet(self._hud_style)
        self._extend_btn.clicked.connect(self.toggle_extend)

        self._snap_btn = QtWidgets.QPushButton("Snap")
        self._snap_btn.setCheckable(True)
        self._snap_btn.setChecked(self._snap_enabled)
        self._snap_btn.setToolTip(
            "Snap the Scene Origin to nearby VP line ends and box corners "
            "(within ~15px) while dragging it."
        )
        self._snap_btn.setStyleSheet(self._hud_style)
        self._snap_btn.clicked.connect(self.toggle_snap)

        self._dim_btn = QtWidgets.QPushButton("Dim")
        self._dim_btn.setCheckable(True)
        self._dim_btn.setChecked(self._dim_enabled)
        self._dim_btn.setToolTip("Darken the plate so the overlay reads clearly on busy footage.")
        self._dim_btn.setStyleSheet(self._hud_style)
        self._dim_btn.clicked.connect(self.toggle_dim)

        self._dim_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self._dim_slider.setRange(0, 100)
        self._dim_slider.setValue(30)
        self._dim_slider.setFixedWidth(80)
        # A horizontal slider defaults to an Expanding size policy; left as-is it
        # makes the whole HUD row report horizontal growth and AlignRight stops
        # clustering the controls to the right. Pin it to Fixed.
        self._dim_slider.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._dim_slider.setEnabled(self._dim_enabled)
        self._dim_slider.setToolTip("Dim amount.")
        self._dim_slider.setStyleSheet(self._hud_slider_style())
        self._dim_slider.valueChanged.connect(self._update_dim)

        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._reset_btn.setStyleSheet(self._hud_style)
        self._reset_btn.clicked.connect(self.reset_handles)

        hud_layout.addWidget(self._fit_btn)
        hud_layout.addWidget(self._100_btn)
        hud_layout.addWidget(self._grid_btn)
        hud_layout.addWidget(self._horizon_btn)
        hud_layout.addWidget(self._extend_btn)
        hud_layout.addWidget(self._snap_btn)
        hud_layout.addWidget(self._dim_btn)
        hud_layout.addWidget(self._dim_slider)
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

    def toggle_extend(self) -> None:
        """Toggle dashed extension of visible VP lines and box edges."""
        self._extend_visible = not self._extend_visible
        if self._extend_btn:
            self._extend_btn.setChecked(self._extend_visible)
        self._update_lines()

    def toggle_snap(self) -> None:
        """Toggle Origin-handle snapping to nearby VP ends and box corners."""
        self._snap_enabled = not self._snap_enabled
        if self._snap_btn:
            self._snap_btn.setChecked(self._snap_enabled)

    def toggle_dim(self) -> None:
        """Toggle the plate-darkening overlay."""
        self._dim_enabled = not self._dim_enabled
        if self._dim_btn:
            self._dim_btn.setChecked(self._dim_enabled)
        if self._dim_slider:
            self._dim_slider.setEnabled(self._dim_enabled)
        self._update_dim()

    def _update_dim(self) -> None:
        """Refresh the dim overlay's size, alpha, and visibility from the slider."""
        if self._dim_slider is None:
            return
        if not self._dim_enabled:
            self._dim_rect.setVisible(False)
            return
        fraction = self._dim_slider.value() / 100.0
        alpha = int(round(fraction * DIM_MAX_ALPHA * 255.0))
        self._dim_rect.setRect(self._plate_rect)
        self._dim_rect.setBrush(QtGui.QBrush(QtGui.QColor(0, 0, 0, alpha)))
        self._dim_rect.setVisible(True)

    def _collect_snap_targets(self) -> list[tuple[float, float]]:
        """Scene positions of currently visible VP line ends and box corners."""
        names = [
            "vp1_a_start", "vp1_a_end", "vp1_b_start", "vp1_b_end",
            "vp2_a_start", "vp2_a_end", "vp2_b_start", "vp2_b_end",
            "vp3_a_start", "vp3_a_end", "vp3_b_start", "vp3_b_end",
        ]
        names.extend(BOX_CORNER_NAMES)
        targets: list[tuple[float, float]] = []
        for name in names:
            handle = self._handles.get(name)
            if handle is not None and handle.isVisible():
                pos = handle.pos()
                targets.append((pos.x(), pos.y()))
        return targets

    def _snap_origin_if_enabled(self) -> None:
        """Pull the Origin onto the nearest target within the screen threshold."""
        if self._is_internal_update or not self._snap_enabled:
            return
        targets = self._collect_snap_targets()
        if not targets:
            return
        origin = self._handles["origin"]
        pos = origin.pos()
        # Handles ignore the view transform, so convert the screen-pixel
        # threshold into scene units to keep the grab radius ~15px at any zoom.
        scale = self.transform().m11()
        threshold_scene = SNAP_THRESHOLD_PX / scale if scale else SNAP_THRESHOLD_PX
        target = nearest_snap_target((pos.x(), pos.y()), targets, threshold_scene)
        if target is None:
            return
        self._is_internal_update = True
        try:
            origin.setPos(target[0], target[1])
        finally:
            self._is_internal_update = False

    def _hud_slider_style(self) -> str:
        """Compact horizontal slider styled to match the HUD buttons."""
        return """
            QSlider {
                min-height: 18px;
            }
            QSlider:disabled {
                opacity: 0.4;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: rgba(45, 45, 45, 180);
                border: 1px solid #555555;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 10px;
                margin: -5px 0;
                background: #cccccc;
                border: 1px solid #888888;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: rgba(100, 150, 255, 150);
                border-radius: 2px;
            }
        """

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
        self.update_grid(self._last_grid_result, *self._last_grid_axes)

    def reset_zoom(self) -> None:
        """Reset zoom to 1:1 pixel ratio."""
        self.resetTransform()
        self.centerOn(self._plate_rect.center())
        self.update_grid(self._last_grid_result, *self._last_grid_axes)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:  # noqa: N802 - Qt API name
        zoom_in_factor = 1.25
        zoom_out_factor = 1.0 / zoom_in_factor
        if event.angleDelta().y() > 0:
            self.scale(zoom_in_factor, zoom_in_factor)
        else:
            self.scale(zoom_out_factor, zoom_out_factor)
        self.update_grid(self._last_grid_result, *self._last_grid_axes)

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
            self.update_grid(self._last_grid_result, *self._last_grid_axes)
        else:
            super().mouseReleaseEvent(event)

    def scrollContentsBy(self, dx: int, dy: int) -> None:  # noqa: N802 - Qt API name
        """Trigger line update on zoom/pan to keep handle-clipping accurate."""
        super().scrollContentsBy(dx, dy)
        self._refresh_canvas_rect()
        self._update_lines()
        self._update_horizon(self._last_grid_result)

    def set_plate(self, width: int, height: int, pixmap: QtGui.QPixmap | None = None) -> None:
        self._is_internal_update = True
        try:
            relative_positions = {
                name: handle.relative_position() for name, handle in self._handles.items()
            }
            self._plate_rect = QtCore.QRectF(0.0, 0.0, float(width), float(height))
            # Keep Qt's scroll/layout extent tied to the plate. Items may still
            # draw and move through the visible canvas when the user zooms out.
            self._scene.setSceneRect(self._plate_rect)
            self._dim_rect.setRect(self._plate_rect)
            self._refresh_canvas_rect()
            for name, handle in self._handles.items():
                handle.set_plate_rect(self._plate_rect, self._canvas_rect)
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

    def principal_point(self) -> Point2D:
        return self._handles["principal_point"].relative_position()

    def match_box_corners(self) -> dict[str, Point2D]:
        return {
            name: self._handles[name].relative_position()
            for name in BOX_CORNER_NAMES
        }

    def mode(self) -> str:
        return self._mode

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API name
        super().resizeEvent(event)
        self.fitInView(self._plate_rect, QtCore.Qt.KeepAspectRatio)
        self.update_grid(self._last_grid_result, *self._last_grid_axes)

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
        self._extension_lines[name] = self._make_extension_line(QtGui.QColor(color))

        # Direction arrowhead above the line but below the handles. Filled
        # triangle, sized in scene units so it stays a constant size on screen
        # regardless of zoom (see _set_arrow_head).
        arrow = QtWidgets.QGraphicsPolygonItem()
        arrow.setBrush(QtGui.QBrush(QtGui.QColor(color)))
        arrow.setPen(QtCore.Qt.NoPen)
        arrow.setZValue(2.5)
        arrow.setVisible(False)
        self._scene.addItem(arrow)
        self._arrows[name] = arrow

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
        handle = _HandleItem(point, QtGui.QColor(color), self._plate_rect, self._canvas_rect)
        handle.signals.moved.connect(self._handle_moved)
        self._scene.addItem(handle)
        return handle

    def _make_extension_line(self, color: QtGui.QColor) -> QtWidgets.QGraphicsLineItem:
        """Create a hidden dashed line that prolongs a construction line.

        Drawn just below the solid line (zValue 1.8 < 2.0) so the solid segment
        between the handles masks the middle, leaving only the dashed extension
        beyond the handles visible when "Extend" is enabled.
        """
        pen = QtGui.QPen(color, 1.0, QtCore.Qt.DashLine)
        pen.setCosmetic(True)
        line = self._scene.addLine(QtCore.QLineF(), pen)
        line.setZValue(1.8)
        line.setVisible(False)
        return line

    def _set_extension(
        self,
        name: str,
        first: QtCore.QPointF,
        second: QtCore.QPointF,
        base_visible: bool,
    ) -> None:
        """Update one dashed extension, clipped to the extended canvas edges."""
        item = self._extension_lines.get(name)
        if item is None:
            return
        if not (self._extend_visible and base_visible):
            item.setVisible(False)
            return
        clipped = self._clip_infinite_line_to_canvas(first, second)
        if clipped is None:
            item.setVisible(False)
            return
        item.setLine(QtCore.QLineF(*clipped))
        item.setVisible(True)

    def _hide_arrow(self, name: str) -> None:
        item = self._arrows.get(name)
        if item is not None:
            item.setVisible(False)

    def _set_arrow_head(
        self,
        name: str,
        tip: QtCore.QPointF,
        dx: float,
        dy: float,
        length: float,
        inv_scale: float,
    ) -> None:
        """Point a constant-size filled arrowhead from start -> end at ``tip``."""
        item = self._arrows.get(name)
        if item is None:
            return
        if length <= 1e-9:
            item.setVisible(False)
            return
        unit_x, unit_y = dx / length, dy / length
        size = 12.0 * inv_scale
        half_width = size * 0.5
        base_x = tip.x() - unit_x * size
        base_y = tip.y() - unit_y * size
        normal_x, normal_y = -unit_y, unit_x
        barb1 = QtCore.QPointF(base_x + normal_x * half_width, base_y + normal_y * half_width)
        barb2 = QtCore.QPointF(base_x - normal_x * half_width, base_y - normal_y * half_width)
        item.setPolygon(QtGui.QPolygonF([QtCore.QPointF(tip), barb1, barb2]))
        item.setVisible(True)

    def _set_axis_arrow(
        self,
        name: str,
        second_tip: QtCore.QPointF,
        p1: QtCore.QPointF,
        p2: QtCore.QPointF,
        inv_scale: float,
    ) -> None:
        """Point the arrow from the line's start handle toward its end handle."""
        start = Point2D(p1.x(), p1.y())
        end = Point2D(p2.x(), p2.y())
        heading = axis_arrow_heading(start, end)
        if heading is None:
            self._hide_arrow(name)
            return
        self._set_arrow_head(name, second_tip, heading.x, heading.y, 1.0, inv_scale)

    def _handle_moved(self) -> None:
        if not self._is_internal_update:
            if self._undo_buffer is not None:
                self._undo_buffer = None
                if self._reset_btn:
                    self._reset_btn.setText("Reset")
                    self._reset_btn.setStyleSheet(self._hud_style)

            # Box interaction logic
            if self._mode == "box" and hasattr(self, "_last_box_positions"):
                # Find which handle moved
                moved_name = None
                dx, dy = 0.0, 0.0
                for name in BOX_CORNER_NAMES:
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
                            for name in BOX_CORNER_NAMES:
                                if name == moved_name: continue
                                p = self._handles[name].relative_position()
                                self._handles[name].set_relative_position(Point2D(p.x + dx, p.y + dy))
                        finally:
                            self._is_internal_update = False
                    
                    # Update cache for next incremental move
                    for name in BOX_CORNER_NAMES:
                        self._last_box_positions[name] = self._handles[name].relative_position()

        # Update Origin label position
        if hasattr(self, "_origin_label") and "origin" in self._handles:
            origin_pos = self._handles["origin"].pos()
            self._origin_label.setPos(origin_pos.x() + 10, origin_pos.y() + 10)

        # Update Principal Point label and crosshair
        if hasattr(self, "_pp_label") and "principal_point" in self._handles:
            pp_pos = self._handles["principal_point"].pos()
            self._pp_label.setPos(pp_pos.x() + 10, pp_pos.y() - 20)
            
            size = 20.0
            self._pp_lines[0].setLine(QtCore.QLineF(pp_pos.x() - size, pp_pos.y(), pp_pos.x() + size, pp_pos.y()))
            self._pp_lines[1].setLine(QtCore.QLineF(pp_pos.x(), pp_pos.y() - size, pp_pos.x(), pp_pos.y() + size))

        self._update_lines()
        self.changed.emit()

    def _update_lines(self) -> None:
        is_box = (getattr(self, "_mode", "lines") == "box")
        
        # 1. Update Box Edges visibility and positions
        for i, (v1, v2) in enumerate(BOX_EDGES):
            name = f"box_edge_{i}"
            if name in self._lines:
                if is_box and v1 in self._handles and v2 in self._handles:
                    p1 = self._handles[v1].pos()
                    p2 = self._handles[v2].pos()
                    self._lines[name].setLine(QtCore.QLineF(p1, p2))
                    self._lines[name].setVisible(True)
                    self._set_extension(name, p1, p2, True)
                else:
                    self._lines[name].setVisible(False)
                    self._set_extension(name, QtCore.QPointF(), QtCore.QPointF(), False)

        # 1b. Box origin-corner axis triad (3 direction arrows, Box mode only)
        inv_scale = 1.0 / self.transform().m11()
        for key, origin_name, dest_name, _color in BOX_TRIAD:
            if is_box and origin_name in self._handles and dest_name in self._handles:
                origin_pos = self._handles[origin_name].pos()
                dest_pos = self._handles[dest_name].pos()
                dx = dest_pos.x() - origin_pos.x()
                dy = dest_pos.y() - origin_pos.y()
                length = (dx * dx + dy * dy) ** 0.5
                scene_offset = HANDLE_RADIUS * inv_scale
                if length > scene_offset * 2.0:
                    unit_x, unit_y = dx / length, dy / length
                    tip = QtCore.QPointF(
                        dest_pos.x() - unit_x * scene_offset,
                        dest_pos.y() - unit_y * scene_offset,
                    )
                    self._set_arrow_head(key, tip, dx, dy, length, inv_scale)
                else:
                    self._hide_arrow(key)
            else:
                self._hide_arrow(key)

        # 2. Update Standard VP Lines visibility and positions
        is_1vp = (getattr(self, "_mode", "2vp") == "1vp")
        is_3vp = (getattr(self, "_mode", "2vp") == "3vp")
        for name, line in self._lines.items():
            if name.startswith("box_edge_"):
                continue
            if name == "reference" and not self._reference_visible:
                line.setVisible(False)
                self._set_extension(name, QtCore.QPointF(), QtCore.QPointF(), False)
                self._hide_arrow(name)
                continue
            # Hide manual VP lines entirely in box mode. Reference line remains editable.
            if is_box and name in ("vp1_a", "vp1_b", "vp2_a", "vp2_b", "vp3_a", "vp3_b"):
                line.setVisible(False)
                self._set_extension(name, QtCore.QPointF(), QtCore.QPointF(), False)
                self._hide_arrow(name)
                continue

            # VP3 lines only visible in 3VP mode
            if name.startswith("vp3") and not is_3vp:
                line.setVisible(False)
                self._set_extension(name, QtCore.QPointF(), QtCore.QPointF(), False)
                self._hide_arrow(name)
                continue
            if name == "vp2_b" and is_1vp:
                line.setVisible(False)
                self._set_extension(name, QtCore.QPointF(), QtCore.QPointF(), False)
                self._hide_arrow(name)
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
            
            visible = False
            if length > HANDLE_RADIUS * 2.0:
                inv_scale = 1.0 / self.transform().m11()
                scene_offset = HANDLE_RADIUS * inv_scale
                if length > scene_offset * 2.0:
                    ratio = scene_offset / length
                    p1_offset = QtCore.QPointF(p1.x() + dx * ratio, p1.y() + dy * ratio)
                    p2_offset = QtCore.QPointF(p2.x() - dx * ratio, p2.y() - dy * ratio)
                    line.setLine(QtCore.QLineF(p1_offset, p2_offset))
                    line.setVisible(True)
                    visible = True
                    if is_1vp and name == "vp2_a":
                        self._hide_arrow(name)
                    elif name.startswith("vp"):
                        self._set_axis_arrow(name, p2_offset, p1, p2, inv_scale)
                    else:
                        self._set_arrow_head(name, p2_offset, dx, dy, length, inv_scale)
                else:
                    line.setVisible(False)
            else:
                line.setVisible(False)
            if not visible:
                self._hide_arrow(name)
            self._set_extension(name, p1, p2, visible)

    def _segments(self, *names: str) -> tuple[Segment2D, Segment2D]:
        return tuple(self._segment(name) for name in names)  # type: ignore[return-value]

    def _segment(self, name: str) -> Segment2D:
        return Segment2D(
            self._handles[f"{name}_start"].relative_position(),
            self._handles[f"{name}_end"].relative_position(),
        )

    def get_state(self) -> dict[str, dict[str, float]]:
        """Return a dictionary of all handle relative positions."""
        return {
            name: {"x": handle.relative_position().x, "y": handle.relative_position().y}
            for name, handle in self._handles.items()
        }

    def set_state(self, state: dict[str, dict[str, float]]) -> None:
        """Restore handle positions from a dictionary."""
        self._is_internal_update = True
        try:
            for name, pos_dict in state.items():
                if name in self._handles:
                    self._handles[name].set_relative_position(
                        Point2D(pos_dict["x"], pos_dict["y"])
                    )
            # Make sure to update the box layout state
            if self._mode == "box":
                self._box_is_default = False
                for name in BOX_CORNER_NAMES:
                    if name in self._handles:
                        self._last_box_positions[name] = self._handles[name].relative_position()
        finally:
            self._is_internal_update = False
        self._update_lines()
        self.changed.emit()

    def vp1_segments(self) -> tuple[Segment2D, ...]:
        if getattr(self, "_mode", "lines") == "box":
            return box_axis_segments(self.match_box_corners(), 0)
        return self._segments("vp1_a", "vp1_b")

    def vp2_segments(self) -> tuple[Segment2D, ...]:
        if getattr(self, "_mode", "lines") == "box":
            return box_axis_segments(self.match_box_corners(), 1)
        if getattr(self, "_mode", "lines") == "1vp":
            return (self._segment("vp2_a"),)
        return self._segments("vp2_a", "vp2_b")

    def vp3_segments(self) -> tuple[Segment2D, ...]:
        if getattr(self, "_mode", "lines") == "box":
            return box_axis_segments(self.match_box_corners(), 2)
        return self._segments("vp3_a", "vp3_b")

    def _update_horizon(self, result: SolveResult | None) -> None:
        if (
            not result
            or not result.ok
            or result.projection_matrix is None
            or result.image_dimensions is None
        ):
            self._horizon_line.setVisible(False)
            return
        try:
            a, b, c = world_plane_horizon_solver_line(result.projection_matrix, 0, 2)
            if abs(b) >= abs(a):
                first_solver = Point2D(-0.5, -(-0.5 * a + c) / b)
                second_solver = Point2D(0.5, -(0.5 * a + c) / b)
            else:
                first_solver = Point2D(-(-0.5 * b + c) / a, -0.5)
                second_solver = Point2D(-(0.5 * b + c) / a, 0.5)
        except (GeometryError, ZeroDivisionError):
            self._horizon_line.setVisible(False)
            return

        width = self._plate_rect.width()
        height = self._plate_rect.height()
        first = solver_to_ui(first_solver, result.image_dimensions, result.principal_point_ui)
        second = solver_to_ui(second_solver, result.image_dimensions, result.principal_point_ui)
        first_point = QtCore.QPointF(
            self._plate_rect.left() + first.x * width,
            self._plate_rect.top() + first.y * height,
        )
        second_point = QtCore.QPointF(
            self._plate_rect.left() + second.x * width,
            self._plate_rect.top() + second.y * height,
        )
        clipped = self._clip_infinite_line_to_canvas(first_point, second_point)
        if clipped is None:
            self._horizon_line.setVisible(False)
            return
        self._horizon_line.setLine(QtCore.QLineF(*clipped))
        self._horizon_line.setVisible(self._horizon_visible)

    def _refresh_canvas_rect(self) -> None:
        """Use the currently visible viewport as the overlay and drag boundary."""
        canvas_rect = self.mapToScene(self.viewport().rect()).boundingRect()
        if canvas_rect.width() <= 0.0 or canvas_rect.height() <= 0.0:
            canvas_rect = self._plate_rect
        self._canvas_rect = canvas_rect
        for handle in getattr(self, "_handles", {}).values():
            handle.set_movement_rect(canvas_rect)

    def _clip_infinite_line_to_canvas(
        self,
        first: QtCore.QPointF,
        second: QtCore.QPointF,
    ) -> tuple[QtCore.QPointF, QtCore.QPointF] | None:
        dx = second.x() - first.x()
        dy = second.y() - first.y()
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return None

        left, right = self._canvas_rect.left(), self._canvas_rect.right()
        top, bottom = self._canvas_rect.top(), self._canvas_rect.bottom()
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
