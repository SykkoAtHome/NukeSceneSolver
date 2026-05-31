import pytest

from scene_solver.core.models import Matrix4, Point2D, Segment2D, Vector3D
from scene_solver.core.solver_2vp import SolveInput, solve_2vp
from scene_solver.nuke_integration.camera_adapter import (
    CameraAdapterError,
    core_camera_to_nuke_matrix,
    create_camera,
    update_camera,
)


class FakeKnob:
    def __init__(self) -> None:
        self.values: dict[int, float | bool] = {}

    def setValue(self, value: float | bool, index: int = 0) -> None:
        self.values[index] = value


class FakeCamera:
    def __init__(self, *, parented: bool = False) -> None:
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
        self.parented = parented

    def Class(self) -> str:
        return "Camera2"

    def __getitem__(self, name: str) -> FakeKnob:
        return self.knobs[name]

    def inputs(self) -> int:
        return 1

    def input(self, index: int) -> object | None:
        return object() if self.parented else None


class FakeNodes:
    def Camera2(self, *, name: str) -> FakeCamera:
        return FakeCamera()


class FakeNuke:
    nodes = FakeNodes()


def segments_for(vanishing_point: Point2D) -> tuple[Segment2D, Segment2D]:
    return (
        Segment2D(Point2D(0.1, 0.2), vanishing_point),
        Segment2D(Point2D(0.8, 0.7), vanishing_point),
    )


def successful_result():
    return solve_2vp(
        SolveInput(
            image_width=1920,
            image_height=1080,
            vp1_segments=segments_for(Point2D(1.7, 0.5)),
            vp2_segments=segments_for(Point2D(-0.175, -2.1666666666666665)),
        )
    )


def test_core_camera_matrix_conversion_uses_nuke_local_axes_directly() -> None:
    matrix = Matrix4.translation(Vector3D(1.0, 2.0, 3.0))

    converted = core_camera_to_nuke_matrix(matrix)

    assert converted.rows == (
        (1.0, 0.0, 0.0, 1.0),
        (0.0, 1.0, 0.0, 2.0),
        (0.0, 0.0, 1.0, 3.0),
        (0.0, 0.0, 0.0, 1.0),
    )


def test_update_camera_sets_camera2_knobs() -> None:
    result = successful_result()
    camera = FakeCamera()

    update_camera(camera, result)

    assert result.ok
    assert camera["projection_mode"].values == {0: 0}
    assert camera["focal"].values == {0: result.focal_length_mm}
    assert camera["haperture"].values == {0: 36.0}
    assert camera["vaperture"].values == {0: 20.25}
    assert camera["win_translate"].values == {0: 0.0, 1: 0.0}
    assert camera["useMatrix"].values == {0: True}
    assert len(camera["matrix"].values) == 16


def test_create_camera_uses_injected_nuke_module() -> None:
    camera = create_camera(successful_result(), nuke_module=FakeNuke())

    assert camera.Class() == "Camera2"
    assert camera["useMatrix"].values == {0: True}


def test_update_camera_rejects_unsuccessful_result() -> None:
    result = solve_2vp(
        SolveInput(
            image_width=1920,
            image_height=1080,
            vp1_segments=segments_for(Point2D(1.0, 0.5)),
            vp2_segments=segments_for(Point2D(1.5, 0.5)),
        )
    )

    with pytest.raises(CameraAdapterError, match="unsuccessful"):
        update_camera(FakeCamera(), result)


def test_update_camera_rejects_parented_camera() -> None:
    with pytest.raises(CameraAdapterError, match="parented"):
        update_camera(FakeCamera(parented=True), successful_result())


def test_update_camera_sets_win_translate_for_off_center_principal_point() -> None:
    result = solve_2vp(
        SolveInput(
            image_width=1920,
            image_height=1080,
            vp1_segments=segments_for(Point2D(1.7, 0.5)),
            vp2_segments=segments_for(Point2D(-0.175, -2.1666666666666665)),
            principal_point=Point2D(0.65, 0.38),
        )
    )
    camera = FakeCamera()

    update_camera(camera, result)

    assert result.ok
    assert camera["win_translate"].values[0] == pytest.approx((0.5 - 0.65) * 2.0)
    assert camera["win_translate"].values[1] == pytest.approx((0.38 - 0.5) * 2.0)
