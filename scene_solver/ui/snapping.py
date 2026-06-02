"""Qt-free snapping helper for the canvas Origin handle.

Kept free of any Qt import so the nearest-target rule is unit-testable without a
running Qt. canvas.py converts QPointF scene positions into plain ``(x, y)``
float tuples before calling, then applies the returned target to the Origin.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

Point = Tuple[float, float]


def nearest_snap_target(
    point: Point,
    targets: Iterable[Point],
    threshold: float,
) -> Optional[Point]:
    """Return the target closest to ``point`` within ``threshold``, else None.

    Distances are Euclidean in the same coordinate space as ``point`` and
    ``targets``. Targets exactly at ``threshold`` count as inside. When several
    targets qualify the nearest wins; an exact distance tie resolves to the
    first such target encountered.
    """
    px, py = point
    threshold_sq = threshold * threshold
    best: Optional[Point] = None
    best_distance_sq: Optional[float] = None
    for target in targets:
        tx, ty = target
        distance_sq = (tx - px) ** 2 + (ty - py) ** 2
        if distance_sq > threshold_sq:
            continue
        if best_distance_sq is None or distance_sq < best_distance_sq:
            best = target
            best_distance_sq = distance_sq
    return best
