"""World-plane horizon projection tests."""

from __future__ import annotations

from math import cos, radians, sin, tan

import pytest

from scene_solver.core.models import GeometryError, Matrix4
from scene_solver.core.projection import (
    solver_projection_matrix,
    world_plane_horizon_solver_line,
)


def test_xz_ground_horizon_is_horizontal_for_an_unrotated_camera():
    projection = solver_projection_matrix(1.0, Matrix4.identity())
    a, b, c = world_plane_horizon_solver_line(projection, 0, 2)
    assert a == pytest.approx(0.0)
    assert b == pytest.approx(1.0)
    assert c == pytest.approx(0.0)


def test_xz_ground_horizon_tracks_camera_pitch():
    angle = radians(20.0)
    world_to_camera = Matrix4.from_rows(
        (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, cos(angle), -sin(angle), 0.0),
            (0.0, sin(angle), cos(angle), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    projection = solver_projection_matrix(1.0, world_to_camera)
    a, b, c = world_plane_horizon_solver_line(projection, 0, 2)
    assert a * 0.0 + b * tan(angle) + c == pytest.approx(0.0)


def test_world_plane_horizon_requires_two_different_axes():
    projection = solver_projection_matrix(1.0, Matrix4.identity())
    with pytest.raises(GeometryError, match="two different axis"):
        world_plane_horizon_solver_line(projection, 0, 0)
