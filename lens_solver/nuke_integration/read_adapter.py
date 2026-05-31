"""Small Nuke node-selection helpers used by the panel."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import tempfile
from typing import Any


class NodeSelectionError(ValueError):
    """Raised when the current Nuke selection cannot satisfy a panel action."""


class PreviewRenderError(RuntimeError):
    """Raised when Nuke cannot render a small plate preview for the panel."""


@dataclass(frozen=True, slots=True)
class PlateInfo:
    node: Any
    node_name: str
    width: int
    height: int
    file_path: str


def get_selected_read(*, nuke_module: Any | None = None) -> PlateInfo:
    """Return metadata for the single selected Read node."""

    nuke = nuke_module or _import_nuke()
    selected = nuke.selectedNodes("Read")
    if len(selected) != 1:
        raise NodeSelectionError("Select exactly one Read node.")
    node = selected[0]
    return PlateInfo(
        node=node,
        node_name=node.name(),
        width=int(node.width()),
        height=int(node.height()),
        file_path=_evaluated_file_path(node),
    )


def get_selected_camera(*, nuke_module: Any | None = None) -> Any:
    """Return the single selected Camera2 node."""

    nuke = nuke_module or _import_nuke()
    selected = nuke.selectedNodes("Camera2")
    if len(selected) != 1:
        raise NodeSelectionError("Select exactly one Camera2 node.")
    return selected[0]


def render_plate_preview(
    plate: PlateInfo,
    *,
    max_dimension: int = 1280,
    nuke_module: Any | None = None,
    temporary_directory: str | os.PathLike[str] | None = None,
) -> bytes:
    """Render a small PNG preview of one plate frame through Nuke.

    A temporary Reformat keeps EXR and high-resolution inputs cheap enough for
    an interactive panel. Returning bytes lets the Qt layer own its QImage
    without depending on the lifetime of the temporary file.
    """

    if plate.node is None:
        raise PreviewRenderError("Cannot render a preview without a Read node.")
    width, height = _preview_dimensions(plate.width, plate.height, max_dimension)
    nuke = nuke_module or _import_nuke()
    previous_selection = tuple(nuke.selectedNodes())
    previous_modified = _script_modified(nuke)
    temporary_nodes: list[Any] = []
    file_descriptor, file_path = tempfile.mkstemp(
        prefix="nuke_lens_solver_preview_",
        suffix=".png",
        dir=temporary_directory,
    )
    os.close(file_descriptor)
    preview_path = Path(file_path)

    try:
        reformat = nuke.nodes.Reformat(name="LensSolverPreviewReformat")
        temporary_nodes.append(reformat)
        reformat.setInput(0, plate.node)
        _set_knob(reformat, "type", "to box")
        _set_knob(reformat, "box_width", width)
        _set_knob(reformat, "box_height", height)
        _set_knob(reformat, "box_fixed", True)
        _set_knob(reformat, "resize", "fit")

        write = nuke.nodes.Write(name="LensSolverPreviewWrite")
        temporary_nodes.append(write)
        write.setInput(0, reformat)
        _set_knob(write, "file", preview_path.as_posix())
        _set_knob(write, "file_type", "png")
        _set_knob(write, "channels", "rgb")

        frame = int(nuke.frame())
        nuke.execute(write, frame, frame)
        data = preview_path.read_bytes()
        if not data:
            raise PreviewRenderError("Nuke rendered an empty preview file.")
        return data
    except PreviewRenderError:
        raise
    except Exception as error:
        raise PreviewRenderError(f"Nuke could not render the plate preview: {error}") from error
    finally:
        for node in reversed(temporary_nodes):
            try:
                nuke.delete(node)
            except Exception:
                pass
        try:
            preview_path.unlink(missing_ok=True)
        except Exception:
            pass
        _restore_selection(nuke, previous_selection)
        _restore_script_modified(nuke, previous_modified)


def _evaluated_file_path(node: Any) -> str:
    knob = node.knob("file")
    if knob is None:
        return ""
    try:
        return str(knob.evaluate())
    except Exception:
        return str(knob.value())


def _preview_dimensions(width: int, height: int, max_dimension: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise PreviewRenderError("Plate dimensions must be positive.")
    if max_dimension <= 0:
        raise PreviewRenderError("Preview maximum dimension must be positive.")
    scale = min(1.0, max_dimension / max(width, height))
    return max(1, round(width * scale)), max(1, round(height * scale))


def _set_knob(node: Any, name: str, value: Any) -> None:
    knob = node.knob(name)
    if knob is None:
        raise PreviewRenderError(f"Temporary {node.Class()} node has no {name!r} knob.")
    knob.setValue(value)


def _script_modified(nuke: Any) -> bool | None:
    modified = getattr(nuke, "modified", None)
    if not callable(modified):
        return None
    try:
        return bool(modified())
    except Exception:
        return None


def _restore_script_modified(nuke: Any, previous_modified: bool | None) -> None:
    if previous_modified is None:
        return
    try:
        nuke.modified(previous_modified)
    except Exception:
        pass


def _restore_selection(nuke: Any, previous_selection: tuple[Any, ...]) -> None:
    try:
        all_nodes = nuke.allNodes()
    except Exception:
        return
    for node in all_nodes:
        try:
            node.setSelected(node in previous_selection)
        except Exception:
            pass


def _import_nuke() -> Any:
    try:
        import nuke
    except ImportError as error:
        raise NodeSelectionError("The nuke module is only available inside Nuke.") from error
    return nuke
