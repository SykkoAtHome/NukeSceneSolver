"""State management for persisting solver settings in the Nuke script."""

from __future__ import annotations

import json
from typing import Any

KNOB_NAME = "SceneSolver_state"


def save_state(state_dict: dict[str, Any], *, nuke_module: Any | None = None) -> None:
    """Save the panel state as a JSON string in a hidden knob on nuke.root()."""
    nuke = nuke_module or _import_nuke()
    root = nuke.root()
    if KNOB_NAME not in root.knobs():
        knob = nuke.String_Knob(KNOB_NAME, "Scene Solver State")
        knob.setVisible(False)
        root.addKnob(knob)
    
    state_json = json.dumps(state_dict)
    root[KNOB_NAME].setValue(state_json)


def load_state(*, nuke_module: Any | None = None) -> dict[str, Any] | None:
    """Load the panel state from the hidden knob on nuke.root()."""
    nuke = nuke_module or _import_nuke()
    root = nuke.root()
    if KNOB_NAME in root.knobs():
        state_json = root[KNOB_NAME].value()
        if state_json:
            try:
                state = json.loads(state_json)
            except json.JSONDecodeError:
                return None
            return state if isinstance(state, dict) else None
    return None


def _import_nuke() -> Any:
    try:
        import nuke
    except ImportError as error:
        raise RuntimeError("The nuke module is only available inside Nuke.") from error
    return nuke
