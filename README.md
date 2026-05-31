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

The next milestone after the Viewer overlay is `Box Match`: a constrained
wireframe cuboid for fitting buildings and interiors by dragging control
corners over the Viewer image. Manual VP lines remain available as the baseline
and diagnostic mode.

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
- `camera_to_world_matrix` maps solver camera-space points into world space.
- Without a reference distance, camera position and scene scale are arbitrary.

## Current limitations

- The `Camera2` adapter currently accepts the MVP principal point `(0.5, 0.5)`.
- Off-center principal points and `win_translate` mapping remain deferred to
  the explicit lens-shift milestone.
- Updating a parented `Camera2` node is rejected to avoid silently applying a
  local matrix where a world matrix was intended.
