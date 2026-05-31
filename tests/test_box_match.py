from dataclasses import dataclass
from math import cos, isclose, radians, sin

import pytest

from scene_solver.core import (
    BoxDimensionInput,
    ImageDimensions,
    Matrix4,
    Point2D,
    ReferenceDistanceInput,
    Segment2D,
    SolveInput,
    Vector3D,
    box_axis_segments,
    reconstruct_match_box,
    solve_box_match,
    solve_box_match_with_dimension,
    solver_to_ui,
)
from scene_solver.nuke_integration.camera_adapter import CORE_TO_NUKE_CAMERA_BASIS
from scene_solver.nuke_integration.camera_adapter import create_camera
from scene_solver.nuke_integration.scene_helpers import create_match_box


DIMENSIONS = ImageDimensions(1920, 1080)
SENSOR_WIDTH_MM = 36.0


@dataclass(frozen=True, slots=True)
class CuboidBounds:
    minimum: Vector3D
    maximum: Vector3D

    @property
    def size(self) -> Vector3D:
        return self.maximum - self.minimum

    def corners(self) -> dict[str, Vector3D]:
        low, high = self.minimum, self.maximum
        return {
            "box_v000": Vector3D(low.x, low.y, low.z),
            "box_v100": Vector3D(high.x, low.y, low.z),
            "box_v010": Vector3D(low.x, low.y, high.z),
            "box_v110": Vector3D(high.x, low.y, high.z),
            "box_v001": Vector3D(low.x, high.y, low.z),
            "box_v101": Vector3D(high.x, high.y, low.z),
            "box_v011": Vector3D(low.x, high.y, high.z),
            "box_v111": Vector3D(high.x, high.y, high.z),
        }


@dataclass(frozen=True, slots=True)
class NukeGroundTruth:
    """Classic Camera3 and Cube values copied from a rendered Nuke script."""

    name: str
    camera_translate: Vector3D
    camera_rotate_degrees: Vector3D
    focal_length_mm: float
    cuboid: CuboidBounds

    @property
    def cuboid_base_y(self) -> float:
        return self.cuboid.minimum.y


NUKE_GROUND_TRUTH = (
    NukeGroundTruth(
        name="nuke_test_01",
        camera_translate=Vector3D(3.140000105, 1.460000038, 4.684999943),
        camera_rotate_degrees=Vector3D(-15.22866726, 33.37726593, -9.817846298),
        focal_length_mm=64.0,
        cuboid=CuboidBounds(
            minimum=Vector3D(-0.5, -0.5, -0.5),
            maximum=Vector3D(0.5, 0.5, 0.5),
        ),
    ),
    NukeGroundTruth(
        name="nuke_test_02",
        camera_translate=Vector3D(3.140000105, 1.460000038, 4.684999943),
        camera_rotate_degrees=Vector3D(-15.22866726, 33.37726593, -9.817846298),
        focal_length_mm=60.0,
        cuboid=CuboidBounds(
            minimum=Vector3D(-0.5, -0.5, -1.210000038),
            maximum=Vector3D(0.2849999964, 0.5, 0.5),
        ),
    ),
    NukeGroundTruth(
        name="nuke_test_03",
        camera_translate=Vector3D(-2.106587887, 0.828261137, 5.035273552),
        camera_rotate_degrees=Vector3D(-8.282423019, -22.48977661, -4.742154598),
        focal_length_mm=73.0,
        cuboid=CuboidBounds(
            minimum=Vector3D(-0.5, -0.5, -1.210000038),
            maximum=Vector3D(0.2849999964, 0.5, 0.5),
        ),
    ),
)


def assert_close(actual: float | None, expected: float, tolerance: float = 1e-7) -> None:
    assert actual is not None
    assert isclose(actual, expected, abs_tol=tolerance)


def assert_vector_close(actual: Vector3D, expected: Vector3D) -> None:
    assert_close(actual.x, expected.x)
    assert_close(actual.y, expected.y)
    assert_close(actual.z, expected.z)


def assert_point_close(actual: Point2D, expected: Point2D) -> None:
    assert_close(actual.x, expected.x)
    assert_close(actual.y, expected.y)


def rotation_x(degrees: float) -> Matrix4:
    angle = radians(degrees)
    return Matrix4.from_rows(
        (
            (1.0, 0.0, 0.0, 0.0),
            (0.0, cos(angle), -sin(angle), 0.0),
            (0.0, sin(angle), cos(angle), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def rotation_y(degrees: float) -> Matrix4:
    angle = radians(degrees)
    return Matrix4.from_rows(
        (
            (cos(angle), 0.0, sin(angle), 0.0),
            (0.0, 1.0, 0.0, 0.0),
            (-sin(angle), 0.0, cos(angle), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def rotation_z(degrees: float) -> Matrix4:
    angle = radians(degrees)
    return Matrix4.from_rows(
        (
            (cos(angle), -sin(angle), 0.0, 0.0),
            (sin(angle), cos(angle), 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )


def nuke_camera_to_world(ground_truth: NukeGroundTruth) -> Matrix4:
    """Build classic Camera3 SRT transform with Nuke's default ZXY rotation order."""

    rotate = ground_truth.camera_rotate_degrees
    return (
        Matrix4.translation(ground_truth.camera_translate)
        @ rotation_y(rotate.y)
        @ rotation_x(rotate.x)
        @ rotation_z(rotate.z)
    )


def project_nuke_world_point(ground_truth: NukeGroundTruth, point: Vector3D) -> Point2D:
    """Project through classic Camera3 using the core-to-Nuke local-axis basis."""

    nuke_camera_point = nuke_camera_to_world(ground_truth).inverse().transform_point(point)
    core_camera_point = CORE_TO_NUKE_CAMERA_BASIS.transform_point(nuke_camera_point)
    focal_plane_distance = ground_truth.focal_length_mm / SENSOR_WIDTH_MM
    return solver_to_ui(
        Point2D(
            -focal_plane_distance * core_camera_point.x / core_camera_point.z,
            -focal_plane_distance * core_camera_point.y / core_camera_point.z,
        ),
        DIMENSIONS,
    )


def reconstructed_cuboid_corners(center: Vector3D, size: Vector3D) -> dict[str, Vector3D]:
    low = center - size * 0.5
    high = center + size * 0.5
    return CuboidBounds(low, high).corners()


def assert_cuboid_bounds(
    actual_center: Vector3D,
    actual_size: Vector3D,
    expected: CuboidBounds,
) -> None:
    assert_vector_close(actual_center - actual_size * 0.5, expected.minimum)
    assert_vector_close(actual_center + actual_size * 0.5, expected.maximum)


class FakeKnob:
    def __init__(self) -> None:
        self.values: dict[int, float | bool] = {}

    def setValue(self, value: float | bool, index: int = 0) -> None:
        self.values[index] = value


class FakeCamera:
    def __init__(self) -> None:
        self.knobs = {
            name: FakeKnob()
            for name in (
                "projection_mode",
                "focal",
                "haperture",
                "vaperture",
                "winroll",
                "win_scale",
                "win_translate",
                "useMatrix",
                "matrix",
            )
        }

    def Class(self) -> str:
        return "Camera2"

    def __getitem__(self, name: str) -> FakeKnob:
        return self.knobs[name]

    def inputs(self) -> int:
        return 0

    def input(self, index: int) -> None:
        return None


class FakeCube:
    def __init__(self) -> None:
        self.knobs = {
            "translate": FakeKnob(),
            "scaling": FakeKnob(),
        }

    def Class(self) -> str:
        return "Cube"

    def knob(self, name: str) -> FakeKnob | None:
        return self.knobs.get(name)


class FakeNodes:
    def __init__(self) -> None:
        self.camera = FakeCamera()
        self.cube = FakeCube()

    def Camera2(self, *, name: str) -> FakeCamera:
        return self.camera

    def Cube(self, *, name: str) -> FakeCube:
        return self.cube


class FakeNuke:
    def __init__(self) -> None:
        self.nodes = FakeNodes()


def flatten(matrix: Matrix4) -> tuple[float, ...]:
    return tuple(value for row in matrix.rows for value in row)


def test_nuke_ground_truth_contains_non_uniform_cuboids() -> None:
    for ground_truth in NUKE_GROUND_TRUTH[1:]:
        size = ground_truth.cuboid.size
        assert not (isclose(size.x, size.y) and isclose(size.y, size.z))


def test_box_match_preserves_selected_axis_signs_when_edge_order_is_reversed() -> None:
    ground_truth = NUKE_GROUND_TRUTH[0]
    projected = {
        name: project_nuke_world_point(ground_truth, point)
        for name, point in ground_truth.cuboid.corners().items()
    }
    reversed_x = {
        "box_v000": projected["box_v100"],
        "box_v100": projected["box_v000"],
        "box_v010": projected["box_v110"],
        "box_v110": projected["box_v010"],
        "box_v001": projected["box_v101"],
        "box_v101": projected["box_v001"],
        "box_v011": projected["box_v111"],
        "box_v111": projected["box_v011"],
    }
    result = solve_box_match(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=(),
            vp2_segments=(),
            origin=project_nuke_world_point(ground_truth, Vector3D(0.0, 0.0, 0.0)),
            first_axis="+X",
            second_axis="+Z",
        ),
        reversed_x,
    )

    assert result.ok
    assert result.camera_position is not None
    assert result.camera_position.y > 0.0


def test_box_dimension_calibration_recovers_camera_and_cuboid_without_reference_line() -> None:
    ground_truth = NUKE_GROUND_TRUTH[2]
    projected_corners = {
        name: project_nuke_world_point(ground_truth, point)
        for name, point in ground_truth.cuboid.corners().items()
    }
    result, calibration = solve_box_match_with_dimension(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=(),
            vp2_segments=(),
            origin=project_nuke_world_point(ground_truth, Vector3D(0.0, 0.0, 0.0)),
            first_axis="+X",
            second_axis="+Z",
            sensor_width_mm=SENSOR_WIDTH_MM,
        ),
        projected_corners,
        BoxDimensionInput(axis="Z", length=ground_truth.cuboid.size.z),
        base_plane_offset=ground_truth.cuboid_base_y,
    )

    assert result.ok
    assert result.camera_position is not None
    assert calibration is not None
    assert_vector_close(result.camera_position, ground_truth.camera_translate)
    assert_close(calibration.measured_length, ground_truth.cuboid.size.z)
    match_box = reconstruct_match_box(
        result,
        projected_corners,
        "+X",
        "+Z",
        base_plane_offset=ground_truth.cuboid_base_y,
    )
    assert_cuboid_bounds(match_box.center, match_box.size, ground_truth.cuboid)


@pytest.mark.parametrize("ground_truth", NUKE_GROUND_TRUTH, ids=lambda value: value.name)
def test_box_match_recovers_camera_and_reprojects_cuboid_from_nuke_ground_truth(
    ground_truth: NukeGroundTruth,
) -> None:
    projected_corners = {
        name: project_nuke_world_point(ground_truth, point)
        for name, point in ground_truth.cuboid.corners().items()
    }
    solve_result = solve_box_match(
        SolveInput(
            image_width=DIMENSIONS.width,
            image_height=DIMENSIONS.height,
            vp1_segments=box_axis_segments(projected_corners, 0),
            vp2_segments=box_axis_segments(projected_corners, 1),
            origin=project_nuke_world_point(ground_truth, Vector3D(0.0, 0.0, 0.0)),
            first_axis="+X",
            second_axis="+Z",
            sensor_width_mm=SENSOR_WIDTH_MM,
            reference_distance=ReferenceDistanceInput(
                segment_ui=Segment2D(
                    project_nuke_world_point(ground_truth, Vector3D(-0.5, 0.0, 0.0)),
                    project_nuke_world_point(ground_truth, Vector3D(0.5, 0.0, 0.0)),
                ),
                axis="+X",
                distance=1.0,
            ),
        ),
        projected_corners,
    )

    assert solve_result.ok
    assert_close(solve_result.focal_length_mm, ground_truth.focal_length_mm)
    assert solve_result.camera_position is not None
    assert_vector_close(solve_result.camera_position, ground_truth.camera_translate)

    match_box = reconstruct_match_box(solve_result, projected_corners, "+X", "+Z")
    expected_size = ground_truth.cuboid.size
    assert_close(match_box.size.x / match_box.size.y, expected_size.x / expected_size.y)
    assert_close(match_box.size.z / match_box.size.y, expected_size.z / expected_size.y)
    for name, point in reconstructed_cuboid_corners(match_box.center, match_box.size).items():
        assert_point_close(project_nuke_world_point(ground_truth, point), projected_corners[name])

    anchored_box = reconstruct_match_box(
        solve_result,
        projected_corners,
        "+X",
        "+Z",
        base_plane_offset=ground_truth.cuboid_base_y,
    )
    assert_cuboid_bounds(anchored_box.center, anchored_box.size, ground_truth.cuboid)

    nuke = FakeNuke()
    camera = create_camera(solve_result, nuke_module=nuke)
    cube = create_match_box(anchored_box, nuke_module=nuke)
    assert_close(camera["focal"].values[0], ground_truth.focal_length_mm)
    assert tuple(camera["matrix"].values[index] for index in range(16)) == pytest.approx(
        flatten(nuke_camera_to_world(ground_truth)),
        abs=1e-7,
    )
    assert cube.knob("translate").values == pytest.approx(
        {0: anchored_box.center.x, 1: anchored_box.center.y, 2: anchored_box.center.z},
        abs=1e-7,
    )
    assert cube.knob("scaling").values == pytest.approx(
        {0: anchored_box.size.x, 1: anchored_box.size.y, 2: anchored_box.size.z},
        abs=1e-7,
    )
    assert_cuboid_bounds(
        Vector3D(*(cube.knob("translate").values[index] for index in range(3))),
        Vector3D(*(cube.knob("scaling").values[index] for index in range(3))),
        ground_truth.cuboid,
    )
