# VP-mode axis orientation & color consistency — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In Vanishing-Point mode, make the signed axis dropdown the single source of truth for axis direction, turn the VP-line arrows into a passive +axis readout, and color each VP group by its world-axis letter (Nuke gizmo convention) reactively.

**Architecture:** Pure, Qt-free helpers (`scene_solver/ui/axis_display.py`) own the colour rule and the arrow heading rule so they are unit-testable without Qt. `canvas.py` consumes them. The arrow-driven sign orientation is removed from `solver_2vp.py`, so the dropdown sign flows straight into the solve.

**Tech Stack:** Python 3, PySide2 (Qt) for the panel/canvas, pytest for the pure helpers. Note: PySide2 is NOT installed in the dev shell, so canvas/panel changes are verified by `compileall` + manual test in Nuke; only the Qt-free helpers and the solver get automated tests.

**Reference spec:** `docs/superpowers/specs/2026-06-02-vp-axis-orientation-color-design.md`

---

## File Structure

- **Create** `scene_solver/ui/axis_display.py` — Qt-free helpers: `AXIS_COLORS`, `axis_color()`, `axis_arrow_heading()`. One responsibility: the rules that map an axis string to a colour and a VP line to its +axis arrow.
- **Create** `tests/test_axis_display.py` — unit tests for the helpers.
- **Create** `tests/test_solver_2vp_sign.py` — regression test: solve ignores drawn segment direction.
- **Modify** `scene_solver/core/solver_2vp.py` — remove arrow-driven orientation (field, function, constant, warnings, unused import).
- **Modify** `scene_solver/ui/panel.py` — stop passing `orient_axes_by_segments`; the axis dropdowns already drive `set_axis_labels`, which now also recolors.
- **Modify** `scene_solver/ui/canvas.py` — `_HandleItem.set_color`; per-group recolor; arrow readout driven by stored VP + sign instead of drawn direction.

---

## Task 1: Qt-free axis-display helpers (colour + arrow heading)

**Files:**
- Create: `scene_solver/ui/axis_display.py`
- Test: `tests/test_axis_display.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_axis_display.py`:

```python
"""Tests for the Qt-free axis-display helpers."""

from __future__ import annotations

from scene_solver.core.models import Point2D
from scene_solver.ui.axis_display import axis_arrow_heading, axis_color


def test_axis_color_maps_letter_to_nuke_gizmo_color():
    assert axis_color("+X") == "#ff5c5c"  # X red
    assert axis_color("-X") == "#ff5c5c"
    assert axis_color("+Y") == "#5cff5c"  # Y green
    assert axis_color("-y") == "#5cff5c"
    assert axis_color("Z") == "#5ca8ff"   # Z blue


def test_positive_arrow_points_toward_vp_on_near_end():
    # Line 0->10 on x; VP far to the right. +axis runs toward the VP.
    start, end = Point2D(0.0, 0.0), Point2D(10.0, 0.0)
    vp = Point2D(100.0, 0.0)
    base, heading = axis_arrow_heading(start, end, vp, positive=True)
    assert base == end
    assert heading.x > 0.9 and abs(heading.y) < 1e-9


def test_negative_arrow_points_away_from_vp_on_far_end():
    start, end = Point2D(0.0, 0.0), Point2D(10.0, 0.0)
    vp = Point2D(100.0, 0.0)
    base, heading = axis_arrow_heading(start, end, vp, positive=False)
    assert base == start
    assert heading.x < -0.9 and abs(heading.y) < 1e-9


def test_heading_follows_vp_on_the_other_side():
    # VP to the LEFT: +axis runs left, so positive arrow sits on the start end.
    start, end = Point2D(0.0, 0.0), Point2D(10.0, 0.0)
    vp = Point2D(-100.0, 0.0)
    base, heading = axis_arrow_heading(start, end, vp, positive=True)
    assert base == start
    assert heading.x < -0.9


def test_degenerate_zero_length_line_returns_none():
    p = Point2D(5.0, 5.0)
    assert axis_arrow_heading(p, p, Point2D(9.0, 9.0), positive=True) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_axis_display.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'scene_solver.ui.axis_display'`

- [ ] **Step 3: Create the helper module**

Create `scene_solver/ui/axis_display.py`:

```python
"""Qt-free helpers for axis-consistent colours and the +axis readout arrow.

Kept free of any Qt import so the colour and geometry rules are unit-testable
without a running Qt. canvas.py converts the returned plain points/vectors into
Qt graphics items.
"""

from __future__ import annotations

from scene_solver.core import world_axis_index
from scene_solver.core.models import Point2D, Vector2D

# Nuke gizmo convention, indexed by world axis (X=0, Y=1, Z=2).
AXIS_COLORS = ("#ff5c5c", "#5cff5c", "#5ca8ff")


def axis_color(axis: str) -> str:
    """Hex colour for an axis string like '+X', '-y', or 'Z'."""
    return AXIS_COLORS[world_axis_index(axis)]


def axis_arrow_heading(
    start: Point2D,
    end: Point2D,
    vanishing_point: Point2D,
    positive: bool,
) -> tuple[Point2D, Vector2D] | None:
    """Resolve a +axis readout arrow for one VP line.

    All points are in scene coordinates. Moving along the +axis moves the image
    point toward the vanishing point, so for ``positive`` the arrow sits on the
    toward-VP endpoint pointing at the VP; for a negative sign it sits on the
    other endpoint pointing away. Returns ``(base, heading_unit)`` or None when
    the line is degenerate (zero length).
    """
    direction = end - start
    if direction.length() <= 1e-9:
        return None
    unit = direction.normalized()
    heads_to_end = unit.dot(vanishing_point - end) >= 0.0
    if heads_to_end:
        toward_base, toward_heading = end, unit
    else:
        toward_base, toward_heading = start, Vector2D(-unit.x, -unit.y)
    if positive:
        return toward_base, toward_heading
    away_base = start if heads_to_end else end
    return away_base, Vector2D(-toward_heading.x, -toward_heading.y)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_axis_display.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add scene_solver/ui/axis_display.py tests/test_axis_display.py
git commit -m "Add Qt-free axis colour and +axis arrow-heading helpers"
```

---

## Task 2: Remove arrow-driven sign orientation (dropdown becomes truth)

**Files:**
- Modify: `scene_solver/core/solver_2vp.py`
- Modify: `scene_solver/ui/panel.py`
- Test: `tests/test_solver_2vp_sign.py`

- [ ] **Step 1: Write the failing regression test**

Create `tests/test_solver_2vp_sign.py`:

```python
"""Solve must depend on the dropdown sign, not the drawn segment direction."""

from __future__ import annotations

import dataclasses

from scene_solver.core.models import Point2D, Segment2D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp


def _segment(ax, ay, bx, by):
    return Segment2D(Point2D(ax, ay), Point2D(bx, by))


def _base_input(vp1, vp2):
    return SolveInput(
        image_width=1920,
        image_height=1080,
        vp1_segments=vp1,
        vp2_segments=vp2,
        first_axis="+X",
        second_axis="+Z",
    )


def test_reversing_drawn_direction_does_not_change_solve():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    forward = solve_2vp(_base_input(vp1, vp2))
    reversed_vp1 = tuple(Segment2D(s.end, s.start) for s in vp1)
    flipped = solve_2vp(_base_input(reversed_vp1, vp2))
    assert forward.ok and flipped.ok
    assert abs(forward.focal_length_mm - flipped.focal_length_mm) < 1e-9
    assert forward.camera_position == flipped.camera_position


def test_solve_input_has_no_orient_axes_field():
    names = {f.name for f in dataclasses.fields(SolveInput)}
    assert "orient_axes_by_segments" not in names
```

- [ ] **Step 2: Run tests to verify the second one fails**

Run: `python -m pytest tests/test_solver_2vp_sign.py -q`
Expected: `test_solve_input_has_no_orient_axes_field` FAILS (field still present); the reversal test already passes.

- [ ] **Step 3: Remove the orientation field from `SolveInput`**

In `scene_solver/core/solver_2vp.py`, delete this line from the `SolveInput` dataclass:

```python
    orient_axes_by_segments: bool = False
```

- [ ] **Step 4: Remove the orientation block from `solve_2vp`**

In `scene_solver/core/solver_2vp.py`, delete the whole block (it sits between the `second_vp_solver = _intersect_ui_segments(...)` assignment and the `focal_plane_squared = -(` line):

```python
        if solve_input.orient_axes_by_segments:
            first_axis, first_ambiguous = _orient_axis_by_segments(
                solve_input.first_axis,
                solve_input.vp1_segments,
                solver_to_ui(first_vp_solver, dimensions, principal_point),
            )
            second_axis, second_ambiguous = _orient_axis_by_segments(
                solve_input.second_axis,
                solve_input.vp2_segments,
                solver_to_ui(second_vp_solver, dimensions, principal_point),
            )
            if first_ambiguous:
                warnings.append(
                    f"Arrow directions for the {solve_input.first_axis.strip('+-').upper()} "
                    "axis are inconsistent; using the selected sign."
                )
            if second_ambiguous:
                warnings.append(
                    f"Arrow directions for the {solve_input.second_axis.strip('+-').upper()} "
                    "axis are inconsistent; using the selected sign."
                )

```

- [ ] **Step 5: Remove the now-dead helper and constant**

In `scene_solver/core/solver_2vp.py`, delete the constant `_AXIS_VOTE_CONFIDENCE` (with its comment) and the entire `_orient_axis_by_segments(...)` function (from its `# A vote is cos(angle)...` comment block through `return parse_world_axis(chosen), False`).

- [ ] **Step 6: Drop the now-unused import**

In `scene_solver/core/solver_2vp.py`, change:

```python
from scene_solver.core.axes import flipped_world_axis, parse_world_axis
```

to:

```python
from scene_solver.core.axes import parse_world_axis
```

(Leave `parse_world_axis`; it is still used. `flipped_world_axis` is only used by `box_match.py`, which has its own import.)

- [ ] **Step 7: Stop passing the kwarg from the panel**

In `scene_solver/ui/panel.py`, inside `_refresh_solution`, delete these lines from the `SolveInput(...)` construction:

```python
            # In VP mode the drawn arrow directions resolve each axis sign (and
            # the mirror ambiguity). Box mode runs its own orientation plus an
            # above-ground correction, so it must not be re-oriented here.
            orient_axes_by_segments=(mode_str != "box"),
```

- [ ] **Step 8: Run all affected tests + compile**

Run:
```bash
python -m pytest tests/test_solver_2vp_sign.py tests/test_geometry_determinant.py -q
python -m compileall -q scene_solver
```
Expected: tests PASS (4 passed), compile prints nothing (success).

- [ ] **Step 9: Commit**

```bash
git add scene_solver/core/solver_2vp.py scene_solver/ui/panel.py tests/test_solver_2vp_sign.py
git commit -m "Make dropdown sign the source of truth; drop arrow-driven orientation"
```

---

## Task 3: Reactive per-axis colours in the canvas

**Files:**
- Modify: `scene_solver/ui/canvas.py`

No automated test (Qt not importable in the dev shell); verified by `compileall` + manual Nuke test.

- [ ] **Step 1: Add a `set_color` method to `_HandleItem`**

In `scene_solver/ui/canvas.py`, inside `class _HandleItem`, add this method (after `__init__`, before `mousePressEvent`):

```python
    def set_color(self, color: QtGui.QColor) -> None:
        """Recolor the handle outline and centre dot."""
        self._color = color
        pen = QtGui.QPen(color, 1.5)
        pen.setCosmetic(True)
        self.setPen(pen)
        self._dot.setBrush(QtGui.QBrush(color))
```

- [ ] **Step 2: Import the colour helper**

In `scene_solver/ui/canvas.py`, add near the existing `from scene_solver.core.models import ...` import:

```python
from scene_solver.ui.axis_display import axis_arrow_heading, axis_color
```

(`axis_arrow_heading` is used in Task 4; import both now.)

- [ ] **Step 3: Add a per-group recolor method on the canvas**

In `scene_solver/ui/canvas.py`, add this method to `SceneSolverCanvas` (next to `set_axis_labels`):

```python
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
```

- [ ] **Step 4: Recolor on axis change inside `set_axis_labels`**

In `scene_solver/ui/canvas.py`, in `set_axis_labels`, store the axes and recolor each group. Replace the current body:

```python
    def set_axis_labels(self, axis1: str, axis2: str, axis3: str = "+Y") -> None:
        """Update labels to reflect assigned world axes."""
        for name in ("vp1_a", "vp1_b"):
            if name in self._labels:
                self._labels[name].setText(f"{axis1.strip('+-')} Axis")
        for name in ("vp2_a", "vp2_b"):
            if name in self._labels:
                self._labels[name].setText(f"{axis2.strip('+-')} Axis")
        for name in ("vp3_a", "vp3_b"):
            if name in self._labels:
                self._labels[name].setText(f"{axis3.strip('+-')} Axis")
        self._update_lines()
```

with:

```python
    def set_axis_labels(self, axis1: str, axis2: str, axis3: str = "+Y") -> None:
        """Update labels and colours to reflect assigned world axes."""
        self._axes = (axis1, axis2, axis3)
        for group, axis in (("vp1", axis1), ("vp2", axis2), ("vp3", axis3)):
            for name in (f"{group}_a", f"{group}_b"):
                if name in self._labels:
                    self._labels[name].setText(f"{axis.strip('+-')} Axis")
            self._recolor_group(group, axis_color(axis))
        self._update_lines()
```

- [ ] **Step 5: Initialise `self._axes` in `__init__`**

In `scene_solver/ui/canvas.py`, in `SceneSolverCanvas.__init__`, alongside the other state fields (near `self._mode = "lines"`), add:

```python
        self._axes: tuple[str, str, str] = ("+X", "+Z", "+Y")
        self._group_vp_scene: dict[str, Point2D | None] = {
            "vp1": None, "vp2": None, "vp3": None,
        }
```

- [ ] **Step 6: Compile**

Run: `python -m compileall -q scene_solver/ui/canvas.py`
Expected: success (no output).

- [ ] **Step 7: Commit**

```bash
git add scene_solver/ui/canvas.py
git commit -m "Color VP groups by axis letter, reactively on dropdown change"
```

---

## Task 4: Arrow readout driven by VP + sign

**Files:**
- Modify: `scene_solver/ui/canvas.py`

No automated test (Qt); the heading rule itself is covered by Task 1's tests. Verified by `compileall` + manual Nuke test.

- [ ] **Step 1: Store per-group vanishing points in `update_grid`**

In `scene_solver/ui/canvas.py`, at the very start of `update_grid` (before any early `return`), populate the scene-space VP per group and refresh the lines so arrows pick up fresh VPs:

```python
    def update_grid(self, result: SolveResult | None, axis1: str = "+X", axis2: str = "+Z") -> None:
        """Draw a perspective grid on the ground plane if the solve is valid."""
        self._store_group_vps(result)
        self._update_lines()
```

(Keep the rest of the existing `update_grid` body exactly as-is after these two lines.)

- [ ] **Step 2: Add the VP-storing helper**

In `scene_solver/ui/canvas.py`, add this method to `SceneSolverCanvas`:

```python
    def _store_group_vps(self, result: SolveResult | None) -> None:
        """Cache each VP group's vanishing point in scene coordinates."""
        groups = ("vp1", "vp2", "vp3")
        if result is None or not result.ok:
            self._group_vp_scene = {group: None for group in groups}
            return
        left, top = self._plate_rect.left(), self._plate_rect.top()
        width, height = self._plate_rect.width(), self._plate_rect.height()
        scene_vps: dict[str, Point2D | None] = {}
        for group, vp in zip(groups, result.vanishing_points_ui):
            if vp is None:
                scene_vps[group] = None
            else:
                scene_vps[group] = Point2D(left + vp.x * width, top + vp.y * height)
        self._group_vp_scene = scene_vps
```

- [ ] **Step 3: Replace the drawn-direction arrow logic in `_update_lines`**

In `scene_solver/ui/canvas.py`, in `_update_lines`, find the VP-line block that currently sets the arrow from the drawn direction:

```python
            visible = False
            if length > HANDLE_RADIUS * 2.0:
                inv_scale = 1.0 / self.transform().m11()
                scene_offset = HANDLE_RADIUS * inv_scale
                ratio = scene_offset / length
                if ratio < 0.5:
                    p1_offset = QtCore.QPointF(p1.x() + dx * ratio, p1.y() + dy * ratio)
                    p2_offset = QtCore.QPointF(p2.x() - dx * ratio, p2.y() - dy * ratio)
                    line.setLine(QtCore.QLineF(p1_offset, p2_offset))
                    line.setVisible(True)
                    visible = True
                    self._set_arrow_head(name, p2_offset, dx, dy, length, inv_scale)
                else:
                    line.setVisible(False)
            else:
                line.setVisible(False)
            if not visible:
                self._hide_arrow(name)
            self._set_extension(name, p1, p2, visible)
```

Replace it with (the only change is the arrow call: it now uses the +axis readout instead of `dx, dy`):

```python
            visible = False
            if length > HANDLE_RADIUS * 2.0:
                inv_scale = 1.0 / self.transform().m11()
                scene_offset = HANDLE_RADIUS * inv_scale
                ratio = scene_offset / length
                if ratio < 0.5:
                    p1_offset = QtCore.QPointF(p1.x() + dx * ratio, p1.y() + dy * ratio)
                    p2_offset = QtCore.QPointF(p2.x() - dx * ratio, p2.y() - dy * ratio)
                    line.setLine(QtCore.QLineF(p1_offset, p2_offset))
                    line.setVisible(True)
                    visible = True
                    self._set_axis_arrow(name, p1, p2, scene_offset, inv_scale)
                else:
                    line.setVisible(False)
            else:
                line.setVisible(False)
            if not visible:
                self._hide_arrow(name)
            self._set_extension(name, p1, p2, visible)
```

- [ ] **Step 4: Add the `_set_axis_arrow` readout method**

In `scene_solver/ui/canvas.py`, add this method to `SceneSolverCanvas`:

```python
    def _set_axis_arrow(
        self,
        name: str,
        p1: QtCore.QPointF,
        p2: QtCore.QPointF,
        scene_offset: float,
        inv_scale: float,
    ) -> None:
        """Point the arrow along the +axis (toward VP for '+', away for '-')."""
        group = name[:3]  # "vp1" / "vp2" / "vp3"
        index = {"vp1": 0, "vp2": 1, "vp3": 2}.get(group)
        vp = self._group_vp_scene.get(group)
        if index is None or vp is None:
            self._hide_arrow(name)
            return
        positive = not self._axes[index].startswith("-")
        heading = axis_arrow_heading(
            Point2D(p1.x(), p1.y()),
            Point2D(p2.x(), p2.y()),
            vp,
            positive,
        )
        if heading is None:
            self._hide_arrow(name)
            return
        base, direction = heading
        tip = QtCore.QPointF(
            base.x - direction.x * scene_offset,
            base.y - direction.y * scene_offset,
        )
        self._set_arrow_head(name, tip, direction.x, direction.y, 1.0, inv_scale)
```

- [ ] **Step 5: Compile**

Run: `python -m compileall -q scene_solver/ui/canvas.py`
Expected: success (no output).

- [ ] **Step 6: Full package compile + run all tests**

Run:
```bash
python -m compileall -q scene_solver tests
python -m pytest tests -q
```
Expected: compile success; all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add scene_solver/ui/canvas.py
git commit -m "Drive VP arrows as a passive +axis readout from VP and sign"
```

---

## Task 5: Manual verification in Nuke

**Files:** none (verification only)

- [ ] **Step 1: Open the Scene Solver panel in Nuke**, switch to Vanishing Points mode.
- [ ] **Step 2: Color follows letter** — change `first_axis` from `+X` to `+Y`; the vp1 line, its handles, label, and arrow turn green. Set it back to `+X`; it returns to red.
- [ ] **Step 3: Arrow is a +axis readout** — flip `+X` ↔ `-X`; the vp1 arrow flips direction (toward vs away from its vanishing point) without redrawing the line.
- [ ] **Step 4: Default +Y points up** — enable the third VP axis (default `+Y`); its arrow points toward the Y vanishing point (up under vertical convergence), matching Nuke's +Y.
- [ ] **Step 5: Arrows don't affect the solve** — drag a vp line so its drawn start→end reverses; the focal length / camera readout is unchanged (only the dropdown sign matters).
- [ ] **Step 6: Box mode unaffected** — switch to Box Match; the triad arrows and box solve behave exactly as before.

---

## Self-Review

**Spec coverage:**
- Sign = dropdown truth → Task 2 (remove field/function/kwarg). ✓
- Remove `_orient_axis_by_segments` / `orient_axes_by_segments` / `_AXIS_VOTE_CONFIDENCE` → Task 2 steps 3-5. ✓
- Box mode untouched → no box_match.py changes; verified Task 5 step 6. ✓
- Colours follow axis letter, reactive, editable dropdowns → Task 3. ✓
- Default look preserved (+X red / +Z blue / +Y green) → `axis_color` map + defaults; Task 3. ✓
- Arrows = passive +axis readout, toward/away VP, hidden on infinity/failure/short line → Task 4 + Task 1 helper. ✓
- Default +Y arrow up auto-fixed → Task 5 step 4. ✓
- Testing: colour map + arrow heading unit tests (Task 1), solve sign-invariance (Task 2). ✓

**Placeholder scan:** No TBD/TODO; every code step has full code. ✓

**Type consistency:** `axis_color(str)->str`, `axis_arrow_heading(Point2D,Point2D,Point2D,bool)->tuple[Point2D,Vector2D]|None`, `_recolor_group(str,str)`, `_store_group_vps(SolveResult|None)`, `_set_axis_arrow(str,QPointF,QPointF,float,float)`, `_HandleItem.set_color(QColor)`, `self._axes: tuple[str,str,str]`, `self._group_vp_scene: dict[str,Point2D|None]` — names used consistently across Tasks 1, 3, 4. ✓
