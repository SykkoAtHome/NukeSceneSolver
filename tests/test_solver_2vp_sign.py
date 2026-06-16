"""VP lines are directed +axis markings; dropdowns select only axis letters."""

from __future__ import annotations

import dataclasses

import pytest

from scene_solver.core.coordinates import ImageDimensions
from scene_solver.core.models import Point2D, Segment2D
from scene_solver.core.models import Vector3D
from scene_solver.core.solver_2vp import SolveInput, _validate_third_axis_segments, solve_2vp


def _segment(ax, ay, bx, by):
    return Segment2D(Point2D(ax, ay), Point2D(bx, by))


def _base_input(vp1, vp2):
    return SolveInput(
        image_width=1920,
        image_height=1080,
        vp1_segments=vp1,
        vp2_segments=vp2,
        first_axis="X",
        second_axis="Z",
    )


def test_reversing_all_drawn_directions_does_not_flip_camera_orientation():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    inp = _base_input(vp1, vp2)
    forward = solve_2vp(inp)
    reversed_vp1 = tuple(Segment2D(s.end, s.start) for s in vp1)
    flipped = solve_2vp(dataclasses.replace(inp, vp1_segments=reversed_vp1))
    assert forward.ok and flipped.ok
    for r1, r2 in zip(forward.camera_to_world_matrix.rows, flipped.camera_to_world_matrix.rows):
        assert r1 == pytest.approx(r2, abs=1e-12)


def test_one_opposing_line_in_a_vp_group_is_accepted():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    inconsistent_vp1 = (vp1[0], Segment2D(vp1[1].end, vp1[1].start))
    result = solve_2vp(_base_input(inconsistent_vp1, vp2))
    assert result.ok


def test_changing_dropdown_letter_changes_camera_orientation():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    x_axis = solve_2vp(_base_input(vp1, vp2))
    y_axis = solve_2vp(dataclasses.replace(_base_input(vp1, vp2), first_axis="Y"))
    assert x_axis.ok and y_axis.ok
    assert x_axis.camera_to_world_matrix != y_axis.camera_to_world_matrix


def test_1vp_horizon_is_undirected_and_chooses_nuke_upright_y():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    horizon = _segment(0.20, 0.50, 0.80, 0.50)
    solve_input = dataclasses.replace(
        _base_input(vp1, (horizon,)),
        mode="1vp",
        known_focal_length_mm=50.0,
    )
    forward = solve_2vp(solve_input)
    reversed_horizon = solve_2vp(
        dataclasses.replace(solve_input, vp2_segments=(Segment2D(horizon.end, horizon.start),))
    )
    assert forward.ok and reversed_horizon.ok
    assert forward.camera_to_world_matrix == reversed_horizon.camera_to_world_matrix


def test_1vp_can_flip_world_up_for_upside_down_shots():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    solve_input = dataclasses.replace(
        _base_input(vp1, (_segment(0.20, 0.50, 0.80, 0.50),)),
        mode="1vp",
        known_focal_length_mm=50.0,
    )
    upright = solve_2vp(solve_input)
    upside_down = solve_2vp(dataclasses.replace(solve_input, flip_world_up=True))

    assert upright.ok and upside_down.ok
    assert upright.camera_to_world_matrix != upside_down.camera_to_world_matrix
    assert upright.camera_to_world_matrix is not None
    assert upside_down.camera_to_world_matrix is not None
    upright_y = tuple(row[1] for row in upright.camera_to_world_matrix.rows[:3])
    upside_down_y = tuple(row[1] for row in upside_down.camera_to_world_matrix.rows[:3])
    assert upside_down_y == pytest.approx(tuple(-component for component in upright_y))


def test_1vp_rejects_y_as_the_only_marked_axis():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    result = solve_2vp(
        dataclasses.replace(
            _base_input(vp1, (_segment(0.20, 0.50, 0.80, 0.50),)),
            mode="1vp",
            first_axis="Y",
            known_focal_length_mm=50.0,
        )
    )
    assert not result.ok
    assert result.errors == (
        "1VP mode requires an X or Z vanishing-point axis; "
        "Y alone does not determine Nuke yaw.",
    )


def test_3vp_rejects_third_axis_that_breaks_nuke_right_handed_frame():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    result = solve_2vp(dataclasses.replace(_base_input(vp1, vp2), mode="3vp", third_axis="Z"))
    assert not result.ok
    assert result.errors == (
        "The third VP axis must be +Y for a right-handed Nuke coordinate system.",
    )


def test_3vp_accepts_parallel_y_up_lines_as_vp_at_infinity():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.50, 0.45, 0.90, 0.40), _segment(0.50, 0.55, 0.90, 0.60))
    vp3 = (_segment(0.40, 0.80, 0.40, 0.20), _segment(0.60, 0.80, 0.60, 0.20))
    result = solve_2vp(
        dataclasses.replace(
            _base_input(vp1, vp2),
            mode="3vp",
            third_axis="Y",
            vp3_segments=vp3,
        )
    )
    assert result.ok
    assert result.vanishing_points_ui[2] is None
    assert (
        "The third VP is at infinity; auto principal point is partially constrained. "
        "Assuming image center for its unresolved component."
    ) in result.warnings


def test_3vp_parallel_y_lines_recover_the_constrained_principal_point_component():
    vp1 = (_segment(0.50, 0.70, 0.00, 0.55), _segment(0.50, 0.10, 0.00, 0.25))
    vp2 = (_segment(0.50, 0.70, 1.00, 0.55), _segment(0.50, 0.10, 1.00, 0.25))
    vp3 = (_segment(0.40, 0.80, 0.40, 0.20), _segment(0.60, 0.80, 0.60, 0.20))
    result = solve_2vp(
        dataclasses.replace(
            _base_input(vp1, vp2),
            image_width=1000,
            image_height=1000,
            mode="3vp",
            third_axis="Y",
            vp3_segments=vp3,
        )
    )
    assert result.ok
    assert result.principal_point_ui.x == pytest.approx(0.5)
    assert result.principal_point_ui.y == pytest.approx(0.4)
    assert result.relative_focal_length == pytest.approx(2.0)


def test_3vp_accepts_opposing_parallel_y_directions():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.50, 0.45, 0.90, 0.40), _segment(0.50, 0.55, 0.90, 0.60))
    vp3 = (_segment(0.40, 0.80, 0.40, 0.20), _segment(0.60, 0.20, 0.60, 0.80))
    result = solve_2vp(
        dataclasses.replace(
            _base_input(vp1, vp2),
            mode="3vp",
            third_axis="Y",
            vp3_segments=vp3,
        )
    )
    assert result.ok


def test_3vp_accepts_finite_vp_between_consistently_oriented_segments():
    _validate_third_axis_segments(
        "Y",
        (
            _segment(0.20, 0.50, 0.50, 0.50),
            _segment(0.80, 0.50, 0.50, 0.50),
        ),
        dimensions=ImageDimensions(1000, 1000),
        principal_point=Point2D(0.50, 0.50),
        focal_plane_distance=1.0,
        expected_camera_direction=Vector3D(0.0, 0.0, -1.0),
    )


def test_3vp_rejects_parallel_y_lines_that_do_not_match_the_solved_axis():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.50, 0.45, 0.90, 0.40), _segment(0.50, 0.55, 0.90, 0.60))
    vp3 = (_segment(0.40, 0.80, 0.60, 0.20), _segment(0.50, 0.80, 0.70, 0.20))
    result = solve_2vp(
        dataclasses.replace(
            _base_input(vp1, vp2),
            mode="3vp",
            third_axis="Y",
            vp3_segments=vp3,
        )
    )
    assert not result.ok
    assert result.errors == (
        "The Y VP lines do not align with the solved Nuke axis direction.",
    )


def test_solve_input_has_no_orient_axes_field():
    names = {f.name for f in dataclasses.fields(SolveInput)}
    assert "orient_axes_by_segments" not in names
