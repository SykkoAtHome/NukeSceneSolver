"""VP lines are directed +axis markings; dropdowns select only axis letters."""

from __future__ import annotations

import dataclasses

from scene_solver.core.models import Point2D, Segment2D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp


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


def test_reversing_drawn_direction_is_rejected():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    forward = solve_2vp(_base_input(vp1, vp2))
    reversed_vp1 = tuple(Segment2D(s.end, s.start) for s in vp1)
    flipped = solve_2vp(_base_input(reversed_vp1, vp2))
    assert forward.ok
    assert not flipped.ok
    assert flipped.errors == (
        "The X VP lines must point toward their vanishing point.",
    )


def test_one_opposing_line_in_a_vp_group_is_rejected():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    inconsistent_vp1 = (vp1[0], Segment2D(vp1[1].end, vp1[1].start))
    result = solve_2vp(_base_input(inconsistent_vp1, vp2))
    assert not result.ok
    assert result.errors == (
        "The X VP lines must point toward their vanishing point.",
    )


def test_changing_dropdown_letter_changes_camera_orientation():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    x_axis = solve_2vp(_base_input(vp1, vp2))
    y_axis = solve_2vp(dataclasses.replace(_base_input(vp1, vp2), first_axis="Y"))
    assert x_axis.ok and y_axis.ok
    assert x_axis.camera_to_world_matrix != y_axis.camera_to_world_matrix


def test_3vp_rejects_third_axis_that_breaks_nuke_right_handed_frame():
    vp1 = (_segment(0.10, 0.40, 0.50, 0.45), _segment(0.10, 0.60, 0.50, 0.55))
    vp2 = (_segment(0.90, 0.40, 0.50, 0.45), _segment(0.90, 0.60, 0.50, 0.55))
    result = solve_2vp(dataclasses.replace(_base_input(vp1, vp2), mode="3vp", third_axis="Z"))
    assert not result.ok
    assert result.errors == (
        "The third VP axis must be Y for a right-handed Nuke coordinate system.",
    )


def test_solve_input_has_no_orient_axes_field():
    names = {f.name for f in dataclasses.fields(SolveInput)}
    assert "orient_axes_by_segments" not in names
