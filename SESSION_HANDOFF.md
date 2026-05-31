# Nuke Lens Solver - project memory

Updated: 2026-05-31
Workspace: `D:\code\nuke_LensSolver`
Target: Foundry Nuke `15.1v4`

## Read first

Read `PRD.md`, `PLAN.md`, and `README.md` before editing.

This repository is an active prototype with tested core geometry and a manually
validated Nuke workflow. Keep changes narrowly scoped and preserve the
coordinate conventions below.

Do not launch Nuke automatically while developing or running Python tests.
Terminal Nuke invocations caused unwanted startup dialogs on this workstation.
The user runs interactive Nuke checks manually when requested.

## Current commits

Relevant history:

```text
f43c76d Implement stage 8 scale and Nuke scene export
6a1ee8f Prepare horizon overlay roadmap and canvas state
65c2f70 UI: Implement Box Match mode with independent Scene Origin.
2280a9a UI: Robust initialization and axis-aligned perspective grid.
```

Local `nuke_files/` contains user-created `.nk` fixtures and rendered images.
These are source material for ground-truth values, not test dependencies. Keep
them untracked unless the user explicitly asks to add them.

## Current implementation

Implemented:

- `lens_solver.core`:
  - guarded geometry, vector and matrix operations,
  - explicit UI, pixel, solver-plane and camera-space conversions,
  - tested `2VP` pinhole solver,
  - least-squares vanishing points from multiple segments,
  - optional reference-distance calibration,
  - projected cuboid edge extraction and Box Match solve,
  - coarse axis-aligned match-box reconstruction,
  - optional base-plane constraint for absolute box placement.
- `lens_solver.nuke_integration`:
  - `Camera2` create/update adapter,
  - selected `Read` and `Camera2` helpers,
  - EXR preview fallback through temporary Nuke nodes,
  - independent scene-grid card, origin card and match-box `Cube` helpers.
- `lens_solver.ui`:
  - dockable PySide2 panel,
  - editable VP lines and independent Scene Origin,
  - Box Match wireframe with eight image-space corners,
  - reference-distance line,
  - horizon HUD,
  - helper-node export buttons,
  - explicit `Match box base offset`.

Stage 8 is complete. Core behavior, helper export and representative manual
validation in Nuke are complete.

## Coordinate conventions

These conventions are critical:

- UI points use relative plate coordinates:
  - top-left: `(0, 0)`
  - bottom-right: `(1, 1)`
- Solver-plane origin is the principal point. Solver-plane Y points upward.
- Matrices are row-major and transform column vectors.
- Core camera space now matches classic Nuke camera space directly:
  - local `-Z` points forward,
  - local `+X` points right,
  - local `+Y` points up.
- `CORE_TO_NUKE_CAMERA_BASIS` is identity.
- Nuke world up is `+Y`.
- Default Nuke ground plane is `X/Z`.
- The panel therefore defaults to first axis `+X`, second axis `+Z`.
- Scene-grid and origin-card nodes are `Card2` nodes rotated by `-90` degrees
  around X so that they lie on the `X/Z` ground plane.

Do not reintroduce the older `diag(-1, -1, 1)` camera-adapter basis without a
renderer-backed regression test.

## Box Match invariants

Box Match means a general rectangular cuboid, not an ideal cube.

- The three dimensions are independent.
- The solver must never assume `width == height == depth`.
- Each vanishing-point solve uses all four projected edges in its cuboid-axis
  family.
- For default ground axes `+X/+Z`, the derived height axis is `+Y`.
- Corner semantics:
  - `box_v000`: base anchor,
  - `box_v100`: first-axis extent,
  - `box_v010`: second-axis extent,
  - `box_v001`: height extent,
  - remaining corners combine those extents.
- Export uses a Nuke `Cube` node with:
  - `translate = reconstructed center`
  - `scaling = reconstructed size`

Nuke's default `Cube` bounds are `-0.5 .. 0.5`, so `scaling` receives the full
cuboid size, not half-size.

## Scene grid and origin

Scene grid and origin card are independent scene helpers:

- Scene grid is always centered at world origin.
- Origin card is always centered at world origin.
- Box fitting and match-box export must not move, resize or snap the grid.
- A non-uniform cuboid does not distort grid aspect ratio.
- Grid cells remain square in world space; perspective alone changes their
  appearance in the image.

Do not attach the scene grid to the match box.

## Single-image ambiguities

One image does not determine every absolute 3D property:

1. Without a reference distance, camera translation and scene scale are
   arbitrary.
2. Even with camera scale, absolute match-box depth along its camera rays needs
   an additional base-plane constraint.
3. A projected cuboid can admit a floor-reflected camera solution.

Current UI handling:

- `Use reference distance` calibrates scene scale from a known segment on a
  selected world axis through Scene Origin.
- `Match box base offset` provides the independent base-plane constraint.
- With default `+X/+Z` ground axes, `Match box base offset` is the box base Y
  coordinate.
- For the `X/Z` floor workflow, Box Match resolves the floor-reflection
  ambiguity by preferring a camera in the `+Y` half-space.

The floor-reflection rule was added after manual Nuke validation showed an
otherwise correct export mirrored vertically through the floor.

## Nuke ground truth

The local `nuke_files/nuke_test_*.nk` scripts were inspected manually and their
numeric values copied into `tests/test_box_match.py`. Tests do not parse or load
the `.nk` files.

Copied fixtures:

```text
nuke_test_01
  camera translate:  3.140000105, 1.460000038, 4.684999943
  camera rotate:    -15.22866726, 33.37726593, -9.817846298
  focal:             64 mm
  cuboid bounds:    -0.5,-0.5,-0.5 .. 0.5,0.5,0.5

nuke_test_02
  camera translate:  3.140000105, 1.460000038, 4.684999943
  camera rotate:    -15.22866726, 33.37726593, -9.817846298
  focal:             60 mm
  cuboid bounds:    -0.5,-0.5,-1.210000038 .. 0.2849999964,0.5,0.5

nuke_test_03
  camera translate: -2.106587887, 0.828261137, 5.035273552
  camera rotate:    -8.282423019,-22.48977661,-4.742154598
  focal:             73 mm
  cuboid bounds:    -0.5,-0.5,-1.210000038 .. 0.2849999964,0.5,0.5
```

Only `nuke_test_01` is an ideal cube. `nuke_test_02` and `nuke_test_03` are
non-uniform cuboids and intentionally guard against cube-only math.

The synthetic tests:

1. Project copied Nuke cuboid corners into image space.
2. Re-run Box Match from those image points.
3. Recover focal length and camera transform.
4. Reconstruct cuboid dimensions and reprojection.
5. Apply base-plane offset and recover absolute cuboid bounds.
6. Verify exported fake `Camera2` and `Cube` knob values.
7. Verify the floor-reflection canonicalization regression.

## Verified behavior

Regular Python test suite:

```powershell
python -m pytest -q
```

Last result:

```text
60 passed
```

Compile check:

```powershell
python -m compileall -q lens_solver tests nuke_tests
```

Manual Nuke validation completed by the user for `nuke_test_01`:

- expected focal: `64 mm`
- observed solve: `64.079 mm`
- camera export: visually correct after floor-reflection fix
- scene grid export: correct and independent
- match-box export: correct after floor-reflection fix

The small focal difference is expected from manual handle placement.

Manual Nuke validation also completed successfully for `nuke_test_03`. This is
the representative non-uniform case: it uses a different camera and a cuboid
whose side lengths are not equal. The user confirmed that the complete export
workflow works correctly.

`nuke_test_02` remains covered by the synthetic ground-truth regression suite.

## Camera2 limitations

- Central principal point `(0.5, 0.5)` is supported.
- Off-center principal point mapping through `win_translate` is deferred.
- Updating parented `Camera2` nodes is rejected because the adapter currently
  writes an unparented world transform.
- Do not silently relax either limitation without targeted tests.

## Useful commands

Run regular tests:

```powershell
python -m pytest -q
python -m compileall -q lens_solver tests nuke_tests
git diff --check
```

Install the development plugin once in `C:\Users\<user>\.nuke\init.py`:

```python
import nuke
nuke.pluginAddPath(r"D:/code/nuke_LensSolver")
```

Nuke loads this repository's `init.py` and `menu.py` through normal plugin
discovery. Do not add a second Lens Solver import to the user's `.nuke/menu.py`.

## Next work

Continue with stage 9 principal-point and optics work from `PLAN.md`.
