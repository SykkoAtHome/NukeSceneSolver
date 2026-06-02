"""Shared parsing helpers for signed world axes."""

from __future__ import annotations

from scene_solver.core.models import GeometryError, Vector3D


WORLD_AXIS_VECTORS = {
    "+X": Vector3D(1.0, 0.0, 0.0),
    "-X": Vector3D(-1.0, 0.0, 0.0),
    "+Y": Vector3D(0.0, 1.0, 0.0),
    "-Y": Vector3D(0.0, -1.0, 0.0),
    "+Z": Vector3D(0.0, 0.0, 1.0),
    "-Z": Vector3D(0.0, 0.0, -1.0),
}
_AXIS_INDICES = {"X": 0, "Y": 1, "Z": 2}
_NUKE_GROUND_AXIS_INDICES = {_AXIS_INDICES["X"], _AXIS_INDICES["Z"]}


def world_axis_vector(axis: str) -> Vector3D:
    """Return the unit vector represented by a signed world-axis name."""

    try:
        return WORLD_AXIS_VECTORS[axis.upper()]
    except (AttributeError, KeyError) as error:
        raise _unsupported_axis(axis) from error


def parse_world_axis(axis: str) -> tuple[int, float]:
    """Return the component index and sign represented by a world axis."""

    normalized = _normalized_signed_axis(axis)
    return _AXIS_INDICES[normalized[1]], 1.0 if normalized[0] == "+" else -1.0


def world_axis_index(axis: str) -> int:
    """Return the component index represented by a signed or unsigned axis."""

    try:
        return _AXIS_INDICES[axis.upper().strip("+-")]
    except (AttributeError, KeyError) as error:
        raise _unsupported_axis(axis) from error


def normalized_world_axis_name(axis: str) -> str:
    """Return an unsigned normalized axis name."""

    return tuple(_AXIS_INDICES)[world_axis_index(axis)]


def is_nuke_ground_plane_axes(first_axis_index: int, second_axis_index: int) -> bool:
    """Return whether two component indices describe Nuke's X/Z ground plane."""

    return {first_axis_index, second_axis_index} == _NUKE_GROUND_AXIS_INDICES


def signed_world_axis_name(axis: str, *, preserve_sign: bool = True) -> str:
    """Return a signed axis name, treating a letter-only UI axis as positive.

    A leading ``-`` is kept only when ``preserve_sign`` is set; every other
    input (unsigned, or any axis when ``preserve_sign`` is false) normalizes to
    the positive axis.
    """

    letter = normalized_world_axis_name(axis)
    if preserve_sign and axis.startswith("-"):
        return f"-{letter}"
    return f"+{letter}"


def flipped_world_axis(axis: str) -> str:
    """Return the same world axis with the opposite sign."""

    normalized = _normalized_signed_axis(axis)
    return f"{'-' if normalized[0] == '+' else '+'}{normalized[1]}"


def missing_world_axis(first_axis: str, second_axis: str) -> str:
    """Return the right-handed third signed axis for two perpendicular axes."""

    axis_by_index = {
        world_axis_index(first_axis): world_axis_vector(first_axis),
        world_axis_index(second_axis): world_axis_vector(second_axis),
    }
    if len(axis_by_index) != 2:
        raise GeometryError("World axes must be different.")
    missing_index = ({0, 1, 2} - set(axis_by_index)).pop()
    if missing_index == 0:
        missing_vector = axis_by_index[1].cross(axis_by_index[2])
    elif missing_index == 1:
        missing_vector = axis_by_index[2].cross(axis_by_index[0])
    else:
        missing_vector = axis_by_index[0].cross(axis_by_index[1])
    component = (missing_vector.x, missing_vector.y, missing_vector.z)[missing_index]
    return f"{'+' if component > 0.0 else '-'}{tuple(_AXIS_INDICES)[missing_index]}"


def _normalized_signed_axis(axis: str) -> str:
    try:
        normalized = axis.upper()
    except AttributeError as error:
        raise _unsupported_axis(axis) from error
    if normalized not in WORLD_AXIS_VECTORS:
        raise _unsupported_axis(axis)
    return normalized


def _unsupported_axis(axis: object) -> GeometryError:
    return GeometryError(
        f"Unsupported world axis {axis!r}. Expected one of: {', '.join(WORLD_AXIS_VECTORS)}."
    )
