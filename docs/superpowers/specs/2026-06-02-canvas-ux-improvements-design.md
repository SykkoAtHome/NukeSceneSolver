# Canvas UX improvements — design

Date: 2026-06-02
Branch: `ai_assist`
Status: approved (design)

## Problem

Three small canvas usability gaps:

1. **Box edges are colorless.** The match-box wireframe draws all 12 edges in
   white dashed, so the user cannot read which edge belongs to which axis.
2. **No origin snapping.** Placing the Scene Origin exactly on a marked line
   end or a box corner requires pixel-perfect dragging.
3. **Plate competes with overlay.** On busy plates the overlay (handles, lines,
   grid) is hard to see against the full-brightness image.

All three live entirely in `scene_solver/ui/canvas.py`. No core/solver change.

## Decisions

- Box mode has **no axis dropdowns** (the axis-selector row is VP-only,
  hidden in box mode — `panel.py:308`). Box always uses the fixed convention
  first = X, second = Z, height = Y. Edge colors therefore map to fixed world
  axes, not to any control.
- Dim is a **toggle + intensity slider** (darken toward black).
- Snap targets are **VP line end handles and box vertices**; only the Origin
  handle snaps.

## Design

### 1. Box edge colors by axis

`BOX_AXIS_EDGES` (in `box_match.py`) already groups the 12 edges into three
families, one per box axis, in the order first / second / height. Color each
family by its world axis, matching the existing `BOX_TRIAD` and the Nuke gizmo
convention:

| Box axis family | World axis | Color     |
|-----------------|------------|-----------|
| `BOX_AXIS_EDGES[0]` (first)  | X | red `#ff5c5c`   |
| `BOX_AXIS_EDGES[1]` (second) | Z | blue `#5ca8ff`  |
| `BOX_AXIS_EDGES[2]` (height) | Y | green `#5cff5c` |

- A single source map `AXIS_COLORS` (index → hex) added to `canvas.py`; the
  same map drives box edges (and is available for the later VP-color work).
- The per-edge pen is built from the family color at creation time
  (`canvas.py:313` loop). Edges stay **dashed**; only the pen color changes.
- Dashed extension lines (`_make_extension_line`) for box edges take the same
  family color (currently white `(255,255,255,90)`), so a prolonged edge keeps
  its axis color.
- Box vertex handles are unchanged (anchor `box_v000` stays yellow).

### 2. Grid Snap (HUD toggle)

- New checkable HUD button **"Snap"** next to "Extend", styled with
  `_hud_style`, default off, stored as `self._snap_enabled`.
- Snapping applies **only to the Origin handle**, evaluated live while it moves.
  Implementation point: the Origin handle's position-change path. The clamp
  already runs in `_HandleItem.itemChange` (`ItemPositionChange`); snapping is a
  second, canvas-level adjustment because it needs the *other* handles'
  positions. Approach: connect to the Origin handle's `moved`/position change
  and, when `self._snap_enabled`, compute the nearest target in scene space and
  call `set_relative_position` on the Origin handle if within threshold.
  - To avoid feedback loops, the snap adjustment is guarded by an
    `self._is_internal_update`-style flag (the canvas already uses one).
- **Targets** (scene coordinates of each candidate handle):
  - VP line end handles: `vp1_a/b_start|end`, `vp2_*`, `vp3_*` for the
    currently active VP groups.
  - The 8 box vertex handles, only when box handles are visible.
- **Threshold:** 15 screen pixels. Because handles ignore view transforms
  (`ItemIgnoresTransformations`) and snapping compares scene positions, convert
  the 15px threshold through the current view scale so it stays ~15px on screen
  at any zoom.
- Nearest target within threshold wins; ties broken by smallest distance. If no
  target is within threshold, the Origin moves freely.

### 3. Dim (HUD toggle + slider)

- New checkable HUD button **"Dim"** (`self._dim_enabled`, default off) plus a
  compact `QSlider` (horizontal, 0–100, default ~30) enabled only while Dim is
  on. Both styled to match the HUD.
- A full-plate semi-transparent **black** overlay rect (`QGraphicsRectItem`)
  sized to the plate, z-ordered **above the plate pixmap but below all overlay
  items** (plate is z≈0; overlay items are z≥1.5). Its alpha = `slider/100`
  scaled to a max (e.g. `0.85`) so the plate never fully disappears.
- Toggling Dim shows/hides the rect; moving the slider updates its alpha. The
  rect is resized whenever the plate size changes (`set_plate`).

## Components touched

- `scene_solver/ui/canvas.py`
  - `AXIS_COLORS` map; box edge + extension pens colored per axis family.
  - HUD: add "Snap" button, "Dim" button, dim slider; wire toggles.
  - Origin-handle snap logic (canvas-level, threshold in screen px).
  - Dim overlay rect: create, size to plate, alpha from slider.

No changes to `panel.py`, the solver, or the Nuke export.

## State / persistence

Snap, Dim, and the dim slider are **session HUD state**, not persisted to
`SceneSolver_state` — consistent with Grid / Horizon / Extend toggles, which are
also non-persistent.

## Testing

- The canvas needs PySide2, which is not in the dev shell, so canvas behavior is
  verified by `compileall` + manual test in Nuke.
- Pure helper extracted where practical for a unit test without Qt:
  - **`nearest_snap_target(point, targets, threshold)`** — returns the closest
    target within threshold or `None`. Unit-tested with: no targets, all
    outside threshold, one inside, two inside (closest wins), tie. Pure
    function on plain `(x, y)` tuples / `Point2D`, no Qt.
- Manual in Nuke: box edges show red/blue/green per axis; Snap on → Origin grabs
  line ends and box corners within ~15px at multiple zooms; Snap off → free.
  Dim on → plate darkens by slider amount, overlay stays bright; off → normal.

## Out of scope

VP-group color reactivity and arrow readout (covered by the separate
`2026-06-02-vp-axis-orientation-color` spec), persistence of HUD state, snapping
of handles other than the Origin.
