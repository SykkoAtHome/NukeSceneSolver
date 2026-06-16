# Nuke Scene Solver

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Nuke 15.1+](https://img.shields.io/badge/Nuke-15.1+-orange.svg)](https://www.foundry.com/products/nuke)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

A powerful, native Python tool for **Foundry Nuke 15.1+** that solves camera intrinsics, position, and orientation from perspective lines marked on a single image. It features a fully dockable PySide2 panel, an interactive canvas editor, robust photogrammetry algorithms, and a seamless export workflow into Nuke's 3D system.

---

## 🚀 Key Features

* **Multi-Mode Vanishing Point Solvers**:
  * **1VP Mode**: Fits a camera from a single vanishing point (X or Z), a known focal length, and a horizon line.
  * **2VP Mode**: Solves camera orientation and focal length from two vanishing points (e.g., ground plane X and Z), automatically resolving focal plane geometry.
  * **3VP Mode**: Simultaneously solves orientation, focal length, and the optical center (Principal Point) using three orthogonal vanishing points.
* **Interactive Box Match Mode**:
  * Fit a 3D rectangular cuboid (wireframe box) directly over buildings, interiors, or objects by dragging its 8 corners on the plate.
  * Solves camera distance and scene scale dynamically based on the estimated dimension of a real-world object.
* **Aesthetic & Responsive Canvas Editor**:
  * **Snapping**: Snaps the Scene Origin handle directly to nearby vanishing point ends and box corners.
  * **Plate Dimming**: Darken busy or high-contrast plates using an interactive slider so the perspective lines and wireframes read clearly.
  * **Horizon HUD**: Live, mathematically calculated horizon overlay projected onto the image view.
  * **Extension Guidelines**: Projects dashed lines from handles to the canvas boundaries to assist with aligning vanishing points.
* **Native Nuke Export**:
  * Generates/updates native Nuke **`Camera2`** nodes.
  * Exports ground **`Card2` (Scene Grid)** and origin-marker nodes rotated onto the X/Z ground plane.
  * Exports reconstructed 3D **`Cube`** nodes with correct translation and uniform/non-uniform world scale.

---

## 📐 Coordinate Conventions

To ensure seamless integration with Nuke's rendering engine, this tool strictly adheres to Nuke's native coordinate conventions:

* **UI/Plate Coordinates**: Normalized image coordinates where top-left is `(0.0, 0.0)` and bottom-right is `(1.0, 1.0)`.
* **Solver Space**: Origin is the principal point, Y points upward, and the full image width corresponds to `1.0`.
* **Camera Space**: Matches classic Nuke camera space:
  * Local **`-Z`** points forward (view direction).
  * Local **`+X`** points right.
  * Local **`+Y`** points up.
* **World Space**: 
  * World **`+Y`** is Up.
  * Default ground plane is **`X/Z`**.
  * The panel defaults to first axis `+X` and second axis `+Z` for ground vanishing points.

---

## 📦 Installation & Setup

1. **Clone or download** this repository to your local machine:
   ```bash
   git clone https://github.com/SykkoAtHome/NukeSceneSolver.git
   ```

2. Add the plugin root path to your `.nuke/init.py` file:
   ```python
   import nuke
   nuke.pluginAddPath(r"D:/code/NukeSceneSolver")
   ```

3. **Restart Nuke**.
4. Open the interface from the Nodes toolbar on the left side: **`Scene Solver > Open Scene Solver`**.

---

## 🛠️ Usage Workflow

### 1. Load your Plate
Select any **`Read`** node in your Nuke Node Graph and click **`Use Selected Read`** in the panel. 
* Common Qt-supported image formats display directly on the canvas.
* For heavy production formats (like `.exr`), the panel automatically renders a fast, temporary 1280px PNG proxy of the current frame in the background, cleaning up all temporary nodes instantly.

### 2. Match Perspective (Lines vs Box Match)
* **Vanishing Point Lines**: Draw/drag the colored segments to align with visible perspective lines in your plate (red for X, blue for Z, green for Y). You can select custom signed axes (e.g. `+X`, `-X`, `+Z`) in the dropdown panel; the solver respects your choice explicitly.
* **Box Match**: Enable Box Match to overlay a 3D wireframe box. Drag the 8 vertices to align with a prominent rectangular object. 

### 3. Calibrate Scale
* **Arbitrary Scale**: Set a preferred camera-to-origin distance (e.g., 10 units).
* **Match-Box Scale**: If using Box Match, select one of the box axes (X, Y, or Z), input its estimated real-world dimension (e.g., 1.5 meters for a matchbox, 5 meters for a room), and set the floor height offset. The camera distance and 3D scene grid scale will calibrate automatically!

### 4. Export to Nuke
Click the export buttons to generate nodes in your scene:
* **`Create Camera`**: Generates an unparented `Camera2` node with the solved focal length, position, and rotation matrix.
* **`Create Scene Grid`**: Generates a scaled `Card2` grid resting on the solved ground plane.
* **`Create Origin Card`**: Places an origin card helper at the world origin `(0,0,0)`.
* **`Create Match Box`**: Generates a Nuke `Cube` node matching your Box Match's solved translation, orientation, and 3D dimensions.

---

## 🧪 Development & Testing

This project has been developed with high emphasis on test-driven development (TDD). The core geometry module is independent of both Nuke and PySide2, allowing for rapid and isolated command-line testing.

### Run Unit Tests
To run the full suite of 46 automated mathematical and regression tests:
```powershell
python -m pytest
```

### Static Analysis & Compilation Check
To verify that all scripts compile correctly without syntax or type errors:
```powershell
python -m compileall -q scene_solver tests
```

---

## ⚠️ Current Limitations

* **Parented Cameras**: Updating a parented `Camera2` node is currently rejected by the adapter to prevent applying absolute world transforms as local matrices. Please ensure exported cameras remain unparented.
* **Nuke Version**: Optimized and validated for Nuke 15.1.
