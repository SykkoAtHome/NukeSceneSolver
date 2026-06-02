"""Tests for the Qt-free origin-snapping helper."""

from __future__ import annotations

from scene_solver.ui.snapping import nearest_snap_target


def test_no_targets_returns_none():
    assert nearest_snap_target((0.0, 0.0), [], 15.0) is None


def test_all_targets_outside_threshold_returns_none():
    targets = [(100.0, 0.0), (0.0, -50.0)]
    assert nearest_snap_target((0.0, 0.0), targets, 15.0) is None


def test_single_target_inside_threshold_wins():
    targets = [(5.0, 0.0), (100.0, 100.0)]
    assert nearest_snap_target((0.0, 0.0), targets, 15.0) == (5.0, 0.0)


def test_closest_of_two_inside_threshold_wins():
    targets = [(10.0, 0.0), (3.0, 0.0)]
    assert nearest_snap_target((0.0, 0.0), targets, 15.0) == (3.0, 0.0)


def test_target_exactly_on_threshold_is_included():
    targets = [(15.0, 0.0)]
    assert nearest_snap_target((0.0, 0.0), targets, 15.0) == (15.0, 0.0)


def test_distance_tie_resolves_to_first_encountered():
    targets = [(0.0, 5.0), (5.0, 0.0)]
    assert nearest_snap_target((0.0, 0.0), targets, 15.0) == (0.0, 5.0)
