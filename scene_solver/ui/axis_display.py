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
    vanishing_point: Point2D,
    positive: bool,
) -> Vector2D | None:
    """Resolve the passive arrow heading for a VP line pointing toward +axis.

    The arrowhead points toward the vanishing point if positive is True, and
    away from it if positive is False.
    """
    direction = end - start
    if direction.length() <= 1e-9:
        return None
    u = direction.normalized()
    to_vp = vanishing_point - start
    points_toward_vp = u.dot(to_vp) >= 0.0

    if positive == points_toward_vp:
        return u
    else:
        return u * -1.0


