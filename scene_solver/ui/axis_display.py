"""Qt-free helpers for axis-consistent colours and signed segment arrows.

Kept free of any Qt import so the colour and geometry rules are unit-testable
without a running Qt. canvas.py converts the returned plain points/vectors into
Qt graphics items.
"""

from __future__ import annotations

from scene_solver.core import normalized_world_axis_name, world_axis_index
from scene_solver.core.models import Point2D, Vector2D

# Nuke gizmo convention, indexed by world axis (X=0, Y=1, Z=2).
AXIS_COLORS = ("#ff5c5c", "#5cff5c", "#5ca8ff")


def axis_color(axis: str) -> str:
    """Hex colour for an axis string like '+X', '-y', or 'Z'."""
    return AXIS_COLORS[world_axis_index(axis)]


def axis_letter(axis: str) -> str:
    """Normalized letter-only axis name for UI selectors and saved-state migration."""
    return normalized_world_axis_name(axis)


def axis_arrow_heading(
    start: Point2D,
    end: Point2D,
) -> Vector2D | None:
    """Resolve the stable arrow heading for one directed VP line.

    The stored handle order is the source of truth: the arrow points from start
    to end. Moving another VP segment cannot flip it. Returns None for a
    zero-length line.
    """
    direction = end - start
    if direction.length() <= 1e-9:
        return None
    return direction.normalized()
