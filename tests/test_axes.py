import pytest

from scene_solver.core.axes import missing_world_axis
from scene_solver.core.models import GeometryError


@pytest.mark.parametrize(
    ("first_axis", "second_axis", "expected"),
    (
        ("+X", "+Y", "+Z"),
        ("+X", "+Z", "+Y"),
        ("+X", "-Z", "-Y"),
        ("-Y", "+Z", "-X"),
    ),
)
def test_missing_world_axis_is_right_handed(
    first_axis: str,
    second_axis: str,
    expected: str,
) -> None:
    assert missing_world_axis(first_axis, second_axis) == expected


def test_missing_world_axis_rejects_duplicate_axes() -> None:
    with pytest.raises(GeometryError, match="different"):
        missing_world_axis("+X", "-X")
