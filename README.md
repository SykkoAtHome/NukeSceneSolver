# Nuke Lens Solver

Native Python tool for Foundry Nuke 15.1 that matches a `Camera2` node to
perspective lines marked on a single image.

The project is under active development. The current implementation contains
the Nuke-independent geometry, a tested 2VP camera solver, a verified `Camera2`
adapter, and a dockable PySide2 panel. See `PRD.md` and `PLAN.md` for scope and
milestones.

## Requirements

- Foundry Nuke 15.1 for Nuke integration and UI work
- Python 3.10 or newer for core development
- `pytest` for unit tests

Nuke 15.1v4 ships with Python 3.10.10 and PySide2. The core package deliberately
does not import either `nuke` or Qt, so it can be tested with a regular Python
interpreter.

## Development

Run the unit tests from the repository root:

```powershell
python -m pytest
```

For development inside Nuke, add the repository plugin path once in
`C:\Users\<user>\.nuke\init.py`:

```python
import nuke
nuke.pluginAddPath(r"D:/code/nuke_LensSolver")
```

Nuke then loads this repository's `init.py` and `menu.py` through its normal
plugin discovery. No Lens Solver import is required in the user's `.nuke/menu.py`.
After restarting Nuke normally, open `Lens Solver > Open Lens Solver` from the
Nodes toolbar on the left side.
Select one `Read` node and click `Use Selected Read`. Common Qt-supported image
formats display directly in the panel. For formats such as EXR, the panel asks
Nuke to render a small temporary PNG proxy of the current frame. The proxy
render is limited to `1280 px` on its longest side and its temporary nodes and
file are removed immediately after the preview is loaded.

The current `QGraphicsView` handle editor inside the panel is a stage 6
prototype. Stage 6 remains open until VP lines and origin are edited directly
over the active Nuke Viewer image. The dockable panel should remain focused on
settings, solver messages, and camera actions.

The panel prototype also contains `Box Match`: a wireframe cuboid for fitting
buildings and interiors by dragging control corners over the plate. Manual VP
lines remain available as the baseline and diagnostic mode.

Stage 8 reference-distance work is complete. Enable `Use reference distance`,
choose the world axis, enter the known length, and place the orange reference
line on the corresponding scene edge through `Scene Origin`. The solver
rescales camera translation without changing perspective. The canvas also
exposes a `Horizon` HUD toggle and the panel can create a scene grid, origin
card, or coarse match-box cuboid as a scaled Nuke `Cube` node. Box Match does
not assume equal side lengths.

Nuke uses `+Y` as world up. The panel therefore defaults to `+X` and `+Z` for
the two ground-plane vanishing points. Scene-grid and origin-marker cards are
rotated onto the `X/Z` ground plane, while the exported match-box height is
reconstructed along `+Y`. Scene grid is always anchored at the independent
yellow `Scene Origin`. `Match box base offset` supplies the independent base
plane constraint needed for absolute match-box placement; with the default
`+X`/`+Z` ground axes it is the base Y coordinate. It does not move the scene
grid. When a Box Match admits an equivalent floor-reflected solution, the
solver prefers the Nuke camera placement above the `X/Z` floor in the `+Y`
half-space.

Run the Nuke integration checks from the repository root:

```powershell
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe -t -V 0 ".\nuke_tests\test_camera2_projection.py"
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe -t -V 0 ".\nuke_tests\test_read_preview.py"
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe --tg -V 0 ".\nuke_tests\test_panel_smoke.py"
```

Menu registration requires an interactive Nuke GUI session. The registration
logic is covered by the regular unit tests.

## Core conventions

- UI points use relative image coordinates: top-left is `(0, 0)` and
  bottom-right is `(1, 1)`.
- Solver-plane points use the principal point as origin, Y points upward, and
  full image width is `1.0`.
- `relative_focal_length` follows
  `focal_mm = 0.5 * sensor_width_mm * relative_focal_length`.
- Matrices are row-major and transform column vectors.
- `camera_to_world_matrix` maps Nuke-compatible camera-space points into world
  space. Local `-Z` points forward, while local `+X` and `+Y` point right and
  up.
- Without a reference distance, camera position and scene scale are arbitrary.

## Current limitations

- The `Camera2` adapter currently accepts the MVP principal point `(0.5, 0.5)`.
- Off-center principal points and `win_translate` mapping remain deferred to
  the explicit lens-shift milestone.
- Updating a parented `Camera2` node is rejected to avoid silently applying a
  local matrix where a world matrix was intended.
