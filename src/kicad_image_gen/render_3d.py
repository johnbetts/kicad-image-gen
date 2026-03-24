"""3D rendering via ``kicad-cli pcb render``."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from kicad_image_gen.core import run_kicad_cli

logger = logging.getLogger(__name__)

# Named view presets: (side, rotate, perspective)
_VIEW_PRESETS: dict[str, tuple[str | None, str | None, bool]] = {
    "top": ("top", None, False),
    "bottom": ("bottom", None, False),
    "front": ("front", None, False),
    "back": ("back", None, False),
    "left": ("left", None, False),
    "right": ("right", None, False),
    "iso": (None, "-45,0,45", True),
    "iso-back": (None, "-45,0,-135", True),
    "iso-bottom": (None, "45,0,45", True),
}


@dataclass(frozen=True)
class Render3DOptions:
    """Options for 3D rendering."""

    view: str = "top"
    width: int = 1600
    height: int = 900
    quality: str = "basic"
    perspective: bool = False
    floor: bool = False
    zoom: float = 1.0
    rotate: str | None = None
    pan: str | None = None
    pivot: str | None = None
    background: str = "transparent"
    preset: str | None = None
    extra_args: list[str] = field(default_factory=list)


def render_3d(
    pcb_path: str | Path,
    output_path: str | Path,
    *,
    view: str = "top",
    width: int = 1600,
    height: int = 900,
    quality: str = "basic",
    perspective: bool = False,
    floor: bool = False,
    zoom: float = 1.0,
    rotate: str | None = None,
    pan: str | None = None,
    pivot: str | None = None,
    background: str = "transparent",
    preset: str | None = None,
    extra_args: list[str] | None = None,
) -> Path:
    """Render a 3D image of a KiCad PCB to PNG.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        output_path: Output PNG file path.
        view: Named preset (top, bottom, iso, iso-back, front, back, left, right)
              or "custom" when using rotate directly.
        width: Image width in pixels.
        height: Image height in pixels.
        quality: Render quality — "basic" or "high".
        perspective: Use perspective projection.
        floor: Enable floor, shadows, and post-processing.
        zoom: Camera zoom level.
        rotate: Custom rotation as "X,Y,Z" degrees (overrides view preset rotation).
        pan: Camera pan as "X,Y,Z".
        pivot: Pivot point as "X,Y,Z" in cm from board center.
        background: "transparent", "opaque", or "default".
        preset: Appearance preset name.
        extra_args: Additional raw CLI arguments.

    Returns:
        Resolved output path.
    """
    pcb_path = Path(pcb_path)
    output_path = Path(output_path)
    if not pcb_path.is_file():
        msg = f"PCB file not found: {pcb_path}"
        raise FileNotFoundError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve view preset
    preset_side, preset_rotate, preset_perspective = _VIEW_PRESETS.get(view, (None, None, False))

    args: list[str] = ["pcb", "render"]
    args.extend(["-w", str(width)])
    args.extend(["--height", str(height)])
    args.extend(["--quality", quality])
    args.extend(["--background", background])

    if preset_side:
        args.extend(["--side", preset_side])

    effective_rotate = rotate or preset_rotate
    if effective_rotate:
        args.extend(["--rotate", effective_rotate])

    if perspective or preset_perspective:
        args.append("--perspective")

    if floor:
        args.append("--floor")

    if zoom != 1.0:
        args.extend(["--zoom", str(zoom)])

    if pan:
        args.extend(["--pan", pan])

    if pivot:
        args.extend(["--pivot", pivot])

    if preset:
        args.extend(["--preset", preset])

    if extra_args:
        args.extend(extra_args)

    args.extend(["-o", str(output_path)])
    args.append(str(pcb_path))

    run_kicad_cli(args, timeout=120)

    if not output_path.is_file() or output_path.stat().st_size == 0:
        msg = f"3D render produced no output at {output_path}"
        raise RuntimeError(msg)

    logger.info("3D render (%s) → %s", view, output_path)
    return output_path
