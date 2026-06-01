from scene_solver.nuke_integration.state import KNOB_NAME, load_state, save_state


class FakeKnob:
    def __init__(self, name: str, label: str) -> None:
        self.name = name
        self.label = label
        self.visible = True
        self._value = ""

    def setVisible(self, visible: bool) -> None:
        self.visible = visible

    def setValue(self, value: str) -> None:
        self._value = value

    def value(self) -> str:
        return self._value


class FakeRoot:
    def __init__(self) -> None:
        self._knobs: dict[str, FakeKnob] = {}

    def knobs(self) -> dict[str, FakeKnob]:
        return self._knobs

    def addKnob(self, knob: FakeKnob) -> None:
        self._knobs[knob.name] = knob

    def __getitem__(self, name: str) -> FakeKnob:
        return self._knobs[name]


class FakeNuke:
    String_Knob = FakeKnob

    def __init__(self) -> None:
        self._root = FakeRoot()

    def root(self) -> FakeRoot:
        return self._root


def test_state_round_trip_uses_injected_nuke_module() -> None:
    nuke = FakeNuke()
    state = {"mode": "2vp", "canvas": {"origin": {"x": 0.4, "y": 0.6}}}

    save_state(state, nuke_module=nuke)

    assert nuke.root()[KNOB_NAME].visible is False
    assert load_state(nuke_module=nuke) == state


def test_load_state_returns_none_for_invalid_json() -> None:
    nuke = FakeNuke()
    nuke.root().addKnob(FakeKnob(KNOB_NAME, "Scene Solver State"))
    nuke.root()[KNOB_NAME].setValue("{")

    assert load_state(nuke_module=nuke) is None


def test_load_state_returns_none_for_non_object_json() -> None:
    nuke = FakeNuke()
    nuke.root().addKnob(FakeKnob(KNOB_NAME, "Scene Solver State"))
    nuke.root()[KNOB_NAME].setValue("[]")

    assert load_state(nuke_module=nuke) is None
