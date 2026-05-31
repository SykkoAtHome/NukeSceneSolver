# Nuke Lens Solver - session handoff

Updated: 2026-05-31
Workspace: `D:\code\nuke_LensSolver`

## Read first

Read `PRD.md`, `PLAN.md`, and `README.md` before editing.

The project target is **Foundry Nuke 15.1**, not Nuke 16.
Local installation:

```text
C:\Program Files\Nuke15.1v4
Nuke 15.1v4
Python 3.10.10
PySide2 / Qt5
```

Do not describe the current state as a working MVP. It is a tested backend with
a prototype UI and a runtime-tested EXR preview path. Interactive end-to-end
validation in the Nuke GUI is still required.

## Current implementation

Implemented:

- Git repository initialized locally, but no commits exist yet.
- `lens_solver.core`:
  - immutable geometry value types,
  - guarded line intersection,
  - vector and matrix operations,
  - explicit UI/pixel/solver-plane coordinate conversions,
  - independent pinhole projection helpers,
  - tested `2VP` solver,
  - arbitrary-scale camera translation placing the selected image `origin` on
    world origin.
- `lens_solver.nuke_integration`:
  - `Camera2` adapter,
  - selected `Read` and `Camera2` helpers,
  - temporary Nuke `Reformat` + `Write` PNG proxy render for EXR previews,
  - panel registration and menu installation.
- `lens_solver.ui`:
  - PySide2 `QGraphicsView` canvas,
  - four draggable VP segments,
  - draggable origin,
  - axis selection,
  - sensor width and camera distance controls,
  - create/update camera buttons,
  - direct `QPixmap` plate preview with a Nuke-backed fallback for EXR and
    other formats unsupported by Qt.
- Nuke plugin entrypoints:
  - `init.py`
  - `menu.py`

## Verified behavior

Regular test suite:

```powershell
python -m pytest -q
```

Last result:

```text
56 passed
```

Python 3.10 compatibility was checked with:

```powershell
& "C:\Program Files\Nuke15.1v4\python.exe" -m compileall -q lens_solver nuke_tests init.py menu.py
```

Nuke runtime checks passed:

```powershell
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe -t -V 0 ".\nuke_tests\test_camera2_projection.py"
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe -t -V 0 ".\nuke_tests\test_read_preview.py"
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe --tg -V 0 ".\nuke_tests\test_panel_smoke.py"
```

Expected output:

```text
camera2-projection-test passed
read-preview-test passed
panel-smoke-test passed
```

## Important Camera2 findings

Verified empirically in Nuke 15.1v4:

- `Camera2` has knobs:
  - `focal`
  - `haperture`
  - `vaperture`
  - `win_translate`
  - `useMatrix`
  - `matrix`
- `matrix` accepts 16 row-major values.
- `world_matrix` reports the expected absolute matrix.
- `useMatrix` must be enabled.
- Nuke camera local image axes differ from core image axes. Adapter applies:

```text
diag(-1, -1, 1)
```

- Central principal point `(0.5, 0.5)` is verified by integration test.
- Off-center principal point mapping through `win_translate` is intentionally
  rejected by the adapter for now. The `nukescripts.snap3d` helper applies
  `win_translate` in a way that did not match the required principal-point
  interpretation. Do not silently re-enable this without a renderer-backed
  regression test.
- Updating parented `Camera2` nodes is intentionally rejected because the
  adapter currently writes a local matrix derived from a world matrix.

## Current blockers and limitations

The tool is not end-to-end validated yet:

1. Menu registration and dock opening were not verified manually in an
   interactive GUI.
   `--tg` instantiates `QApplication`, but Nuke still reports `not in GUI mode`
   when `registerWidgetAsPanel()` accesses the `Pane` menu.
2. VP lines and origin are still edited on a prototype `QGraphicsView` copy of
   the plate inside the panel. Stage `6` now explicitly requires moving these
   draggable handles onto the active Nuke Viewer image. The dockable panel
   should retain only settings, solver messages and camera actions.
3. There is no reference distance yet, so scene scale is arbitrary.
4. No state persistence in `.nk` yet.

## Next task

Finish stage 6 by moving interaction to the Nuke Viewer:

1. Implement a Python Viewer overlay for:
   - two red VP segments,
   - two blue VP segments,
   - the yellow origin handle,
   - draggable endpoints stored as relative plate coordinates.
2. Keep axis mapping, sensor width, messages and camera buttons in the dockable
   panel. Treat its current `QGraphicsView` plate copy as a prototype/fallback,
   not the target UI.
3. Manually launch interactive Nuke normally and verify:
   - `Lens Solver` launcher appears in the left-side Nodes toolbar,
   - dockable panel opens,
   - selected `Read` is visible in the active Viewer,
   - handles can be dragged directly over the Viewer plate,
   - `Create Camera` creates a useful `Camera2`.
4. Confirm that a generated camera is useful in a small `Project3D` or
   `ScanlineRender` check over the real plate.

After stage `6`, implement stage `7 - Box Match` before reference distance:

- draw a constrained wireframe cuboid over the active Viewer,
- use colored `X`, `Y`, `Z` edge groups,
- expose only control corners that preserve a coherent cuboid perspective,
- derive VP line groups from the cuboid edges,
- allow a cuboid corner to become origin,
- retain manual VP lines as the baseline and diagnostic mode.

Do not move on to reference distance or persistence until the Viewer workflow
and Box Match work end-to-end on a real plate.

## Useful commands

Install the development plugin once in `C:\Users\<user>\.nuke\init.py`:

```python
import nuke
nuke.pluginAddPath(r"D:/code/nuke_LensSolver")
```

Nuke loads the repository's `menu.py` through normal plugin discovery. Do not
add a second Lens Solver import to the user's `.nuke/menu.py`.

Run the terminal menu check:

```powershell
& "C:\Program Files\Nuke15.1v4\Nuke15.1.exe" --safe --tg -V 0 ".\nuke_tests\test_menu_registration.py"
```

Expected terminal-only result:

```text
menu-registration-test skipped: interactive GUI required
```

## Repository state

At handoff, all files are untracked because the local repository has not been
committed yet. Do not remove user files. Review `git status --short --branch`
before making further edits.
