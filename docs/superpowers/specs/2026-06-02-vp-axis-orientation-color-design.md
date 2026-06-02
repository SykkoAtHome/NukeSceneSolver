# VP-mode axis orientation & color consistency — design

Date: 2026-06-02
Branch: `ai_assist`
Status: approved (design), pending implementation plan

## Problem

In Vanishing-Point mode the axis model has redundant and inconsistent controls:

1. **Sign is encoded twice.** Each axis has a signed dropdown (`+X`, `-X`, …) *and*
   a drawn arrow on the VP line. The "direction-aware solve" (commit `14638f0`,
   refined by the P3 review fix) lets the arrow override the dropdown sign, so the
   user has two controls for one decision.
2. **Default arrow direction contradicts Nuke.** The default `vp3` segment runs
   top→bottom in screen space, so the Y-axis arrow points down while Nuke's `+Y`
   is up and the dropdown defaults to `+Y`.
3. **Colors are tied to the VP slot, not the axis.** `vp1` is always red, `vp2`
   blue, `vp3` green regardless of which world axis each dropdown selects, so a
   `vp1` set to `+Y` stays red instead of matching the green Y convention.

## Decisions (from brainstorming)

- **Sign source of truth = the signed dropdown.** Arrows do not influence the
  solve.
- **Arrows = passive readout** of the selected `+axis` direction.
- **Colors follow the axis letter**, by Nuke gizmo convention, and react to
  dropdown changes.
- **Axis-letter dropdowns stay user-editable in every mode** (including 3VP);
  no locking.
- **No 2VP "ground" auto-correction** — line mode has no ground-plane concept
  (that lives only in box mode) and always produces a right-handed frame, so
  there is nothing to correct.

## Color convention

Nuke gizmo colors, keyed by world-axis index (`world_axis_index`: X=0, Y=1, Z=2).
The hex values already exist in `canvas.py`:

| Axis | Index | Color     | Hex       |
|------|-------|-----------|-----------|
| X    | 0     | red       | `#ff5c5c` |
| Y    | 1     | green     | `#5cff5c` |
| Z    | 2     | blue      | `#5ca8ff` |

## Design

### 1. Sign = dropdown truth (remove arrow-driven orientation in VP mode)

- `panel.py`: build `SolveInput` with `orient_axes_by_segments=False` for VP mode
  (currently `mode_str != "box"`). The signed axis already flows into the solve
  through `first_axis` / `second_axis`, so the dropdown sign becomes authoritative
  with no further change to the solve path.
- `solver_2vp.py`: with `orient_axes_by_segments` never true for VP, the field and
  `_orient_axis_by_segments` (plus `_AXIS_VOTE_CONFIDENCE`, the warning emission,
  and the now-unused `flipped_world_axis` import if nothing else uses it) become
  dead code. **Remove them.** This reverts the direction-aware sign flip and its
  P3 refinement, which the new model makes obsolete.
- **Box mode is untouched.** Its internal `_axis_oriented_by_segments`
  (`box_match.py`) orients from the drawn box edges and is unrelated to the VP
  dropdown/arrow controls.

Safety: the third camera axis is always the cross product of the two chosen axes
(`_world_to_camera_columns`), so the frame is always right-handed and
`_validate_rotation` (det = +1) does not start failing. Different sign choices
rotate the frame but never reflect it.

### 2. Colors follow the axis letter, reactively

- Add an axis-index → color map (single source, e.g. `AXIS_COLORS` in `canvas.py`).
- Add a canvas method that recolors a VP group (its line, both handles, label, and
  arrow) given the group key (`vp1`/`vp2`/`vp3`) and a target color.
- `panel.py` calls it for each active group whenever an axis dropdown's text
  changes and once after loading state, mapping each group to the color of its
  current axis letter.
- Defaults (`+X` / `+Z` / `+Y`) keep the current look (vp1 red, vp2 blue, vp3
  green) but now driven by letter, not slot. Changing `first_axis` to `+Y` turns
  the vp1 group green.

### 3. Arrows = passive `+axis` readout

- After each solve, for every visible VP group, orient its arrow along the VP line:
  toward the group's vanishing point `result.vanishing_points_ui[index]` when the
  dropdown sign is `+`, away from it when `-`. Locally, moving along `+axis` moves
  the image point toward the vanishing point, so "toward VP" reads as `+`.
- The arrow no longer derives from the drawn `start → end`; dragging a handle moves
  the arrow but cannot change its meaning. The arrow is not user-editable.
- This auto-fixes the default-direction bug: `+Y` points toward the Y vanishing
  point (up under vertical convergence), matching Nuke.
- Edge cases → hide the arrow: solve failed / not `ok`, the axis vanishing point is
  `None` (at infinity), or the line is shorter than the existing minimum length
  threshold.
- Arrow drawing therefore moves from the handle-move path (`_update_lines`) to a
  solve-result-driven update (alongside `update_grid`), and also re-runs when the
  axis sign changes.

### 4. Out of scope (unchanged)

Box mode (already follows the convention and orients from edges), 1VP-specific
behavior beyond color/arrow consistency, principal point, and scale calibration.

## Components touched

- `scene_solver/ui/panel.py` — `orient_axes_by_segments=False`; recolor groups on
  axis-dropdown change and on load; trigger arrow readout refresh on sign change.
- `scene_solver/ui/canvas.py` — `AXIS_COLORS` map; per-group recolor method;
  arrow readout driven by sign + `vanishing_points_ui`.
- `scene_solver/core/solver_2vp.py` — remove `orient_axes_by_segments`,
  `_orient_axis_by_segments`, `_AXIS_VOTE_CONFIDENCE`, related warnings/imports.

## Testing

- **Unit:** axis-index → color mapping; arrow-direction sign helper (given a line,
  a vanishing point, and a sign, the arrow points toward/away correctly). Pure
  functions, no Qt.
- **Manual in Nuke:** change a dropdown letter → that group's line/handles/label
  recolor; flip `+X` ↔ `-X` → arrow flips; default `+Y` arrow points up; arrows
  never alter the solve.

## Risks / notes

- Removing arrow-driven orientation means the user sets signs manually. This is
  the intended model; the arrow readout gives immediate feedback so a wrong sign
  is obvious and one dropdown flip fixes it.
- Persisted state (`SceneSolver_state`) does not need a schema change; sign and
  axis letters already live in the dropdown values that are saved.
