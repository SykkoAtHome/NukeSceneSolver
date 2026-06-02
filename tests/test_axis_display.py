"""Tests for the Qt-free axis-display helpers."""

from __future__ import annotations

from scene_solver.core.models import Point2D
from scene_solver.ui.axis_display import axis_arrow_heading, axis_color, axis_letter


def test_axis_color_maps_letter_to_nuke_gizmo_color():
    assert axis_color("+X") == "#ff5c5c"  # X red
    assert axis_color("-X") == "#ff5c5c"
    assert axis_color("+Y") == "#5cff5c"  # Y green
    assert axis_color("-y") == "#5cff5c"
    assert axis_color("Z") == "#5ca8ff"  # Z blue


def test_axis_letter_migrates_signed_saved_state():
    assert axis_letter("+X") == "X"
    assert axis_letter("-y") == "Y"
    assert axis_letter("Z") == "Z"


def test_arrow_points_from_start_to_end():
    start, end = Point2D(0.0, 0.0), Point2D(10.0, 0.0)
    heading = axis_arrow_heading(start, end)
    assert heading is not None
    assert heading.x > 0.9 and abs(heading.y) < 1e-9


def test_arrow_follows_segment_after_edit():
    start, end = Point2D(10.0, 0.0), Point2D(0.0, 0.0)
    heading = axis_arrow_heading(start, end)
    assert heading is not None
    assert heading.x < -0.9


def test_degenerate_zero_length_line_returns_none():
    p = Point2D(5.0, 5.0)
    assert axis_arrow_heading(p, p) is None
