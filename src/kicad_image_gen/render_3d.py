"""3D rendering via ``kicad-cli pcb render``."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from kicad_image_gen.core import run_kicad_cli
from kicad_image_gen.ratsnest import parse_board_bounds, parse_footprint_bounds

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
    width: int = 3200
    height: int = 1800
    dpi: int | None = None
    quality: str = "basic"
    perspective: bool = False
    floor: bool = False
    zoom: float = 1.0
    rotate: str | None = None
    pan: str | None = None
    pivot: str | None = None
    background: str = "transparent"
    preset: str | None = None
    pad_overlay: bool = False
    extra_args: list[str] = field(default_factory=list)


def render_3d(
    pcb_path: str | Path,
    output_path: str | Path,
    *,
    view: str = "top",
    width: int = 3200,
    height: int = 1800,
    dpi: int | None = None,
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
    pad_overlay: bool = False,
    crop: str | None = None,
    padding_mm: float = 5.0,
) -> Path:
    """Render a 3D image of a KiCad PCB to PNG.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        output_path: Output PNG file path.
        view: Named preset (top, bottom, iso, iso-back, front, back, left, right)
              or "custom" when using rotate directly.
        width: Image width in pixels.
        height: Image height in pixels.
        dpi: Pixels per mm of board dimension. When set, overrides width/height
             by computing dimensions from board bounds.
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
        pad_overlay: Draw semi-transparent pad position overlays on top of the
            rendered 3D image (top/bottom views only).
        crop: Reference designator to zoom into (e.g. "U1"). None for full board.
        padding_mm: Context padding in mm around crop target (default 5.0).

    Returns:
        Resolved output path.
    """
    pcb_path = Path(pcb_path)
    output_path = Path(output_path)
    if not pcb_path.is_file():
        msg = f"PCB file not found: {pcb_path}"
        raise FileNotFoundError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # When dpi is specified, compute width/height from board bounds
    if dpi is not None:
        bx0, by0, bx1, by1 = parse_board_bounds(pcb_path)
        board_w_mm = bx1 - bx0
        board_h_mm = by1 - by0
        width = int(board_w_mm * dpi)
        height = int(board_h_mm * dpi)
        logger.info("DPI %d → %dx%d (board %.1f×%.1f mm)", dpi, width, height, board_w_mm, board_h_mm)

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

    # Crop to component area using PIL
    if crop:
        try:
            _crop_3d_to_component(pcb_path, output_path, crop, padding_mm)
        except (ValueError, ImportError) as exc:
            logger.warning("Could not crop 3D render to '%s': %s", crop, exc)

    # Pad overlay: draw semi-transparent rectangles/circles at each pad position
    if pad_overlay and view in ("top", "bottom"):
        _apply_pad_overlay(pcb_path, output_path, view=view)

    logger.info("3D render (%s) → %s", view, output_path)
    return output_path


# ---------------------------------------------------------------------------
# Component crop helper
# ---------------------------------------------------------------------------


def _crop_3d_to_component(
    pcb_path: Path,
    output_path: Path,
    refdes: str,
    padding_mm: float,
) -> None:
    """Crop a rendered 3D PNG to show only the area around a specific component."""
    from PIL import Image

    board_bounds = parse_board_bounds(pcb_path)
    comp_bounds = parse_footprint_bounds(pcb_path, refdes)

    bx0, by0, bx1, by1 = board_bounds
    board_w = bx1 - bx0
    board_h = by1 - by0

    img = Image.open(output_path)
    img_w, img_h = img.size

    # Compute scale from board mm to image pixels
    # The 3D renderer fits the board into the image with some margin
    # Estimate the board area in the image (assume ~4% margin like SVG export)
    margin_frac = 0.04
    board_aspect = board_w / board_h if board_h > 0 else 1.0
    img_aspect = img_w / img_h if img_h > 0 else 1.0

    if board_aspect > img_aspect:
        usable_width = img_w * (1 - 2 * margin_frac)
        scale = usable_width / board_w
        offset_x = img_w * margin_frac
        offset_y = (img_h - board_h * scale) / 2
    else:
        usable_height = img_h * (1 - 2 * margin_frac)
        scale = usable_height / board_h
        offset_y = img_h * margin_frac
        offset_x = (img_w - board_w * scale) / 2

    # Convert component bounds (with padding) to pixel coords
    cx0 = comp_bounds[0] - padding_mm
    cy0 = comp_bounds[1] - padding_mm
    cx1 = comp_bounds[2] + padding_mm
    cy1 = comp_bounds[3] + padding_mm

    px0 = int(offset_x + (cx0 - bx0) * scale)
    py0 = int(offset_y + (cy0 - by0) * scale)
    px1 = int(offset_x + (cx1 - bx0) * scale)
    py1 = int(offset_y + (cy1 - by0) * scale)

    # Clamp to image bounds
    px0 = max(0, px0)
    py0 = max(0, py0)
    px1 = min(img_w, px1)
    py1 = min(img_h, py1)

    if px1 <= px0 or py1 <= py0:
        logger.warning("Crop region is empty for '%s'", refdes)
        return

    cropped = img.crop((px0, py0, px1, py1))
    cropped.save(str(output_path), "PNG")
    logger.info("Cropped 3D render to %s: %dx%d pixels", refdes, cropped.width, cropped.height)


# ---------------------------------------------------------------------------
# Pad overlay helpers
# ---------------------------------------------------------------------------

# Overlay styling
_SMD_PAD_COLOR = (0, 200, 200, 100)  # semi-transparent cyan
_THT_PAD_COLOR = (200, 0, 0, 100)  # semi-transparent red
_PAD_TEXT_COLOR = (255, 255, 255, 180)  # white text


def _mm_to_pixel_mapper(
    board_bounds: tuple[float, float, float, float],
    img_width: int,
    img_height: int,
) -> tuple[float, float, float, float]:
    """Compute mapping from PCB mm coords to pixel coords.

    Mirrors the logic in render_2d_composite.py.

    Returns (scale_x, scale_y, offset_x, offset_y).
    """
    min_x, min_y, max_x, max_y = board_bounds
    board_w = max_x - min_x
    board_h = max_y - min_y

    if board_w <= 0 or board_h <= 0:
        msg = f"Invalid board bounds: {board_bounds}"
        raise ValueError(msg)

    board_aspect = board_w / board_h
    img_aspect = img_width / img_height

    margin_frac = 0.04
    if board_aspect > img_aspect:
        usable_width = img_width * (1 - 2 * margin_frac)
        scale = usable_width / board_w
        offset_x = img_width * margin_frac
        offset_y = (img_height - board_h * scale) / 2
    else:
        usable_height = img_height * (1 - 2 * margin_frac)
        scale = usable_height / board_h
        offset_y = img_height * margin_frac
        offset_x = (img_width - board_w * scale) / 2

    return scale, scale, offset_x, offset_y


def _pcb_to_pixel(
    pcb_x: float,
    pcb_y: float,
    board_bounds: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    offset_x: float,
    offset_y: float,
) -> tuple[float, float]:
    """Convert a PCB coordinate (mm) to pixel coordinate."""
    min_x, min_y, _max_x, _max_y = board_bounds
    px = offset_x + (pcb_x - min_x) * scale_x
    py = offset_y + (pcb_y - min_y) * scale_y
    return px, py


def _apply_pad_overlay(
    pcb_path: Path,
    output_path: Path,
    *,
    view: str = "top",
) -> None:
    """Overlay semi-transparent pad markers on the rendered 3D image."""
    from PIL import Image, ImageDraw, ImageFont

    from kicad_image_gen.ratsnest import parse_board_bounds, parse_pad_labels, parse_tht_pads

    board_bounds = parse_board_bounds(pcb_path)
    all_pads = parse_pad_labels(pcb_path)
    tht_pads = parse_tht_pads(pcb_path)

    if not all_pads:
        return

    # Build set of THT pad positions for quick lookup (rounded to 0.01mm)
    tht_positions: set[tuple[float, float]] = set()
    for tp in tht_pads:
        tht_positions.add((round(tp.x, 2), round(tp.y, 2)))

    img = Image.open(output_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    scale_x, scale_y, offset_x, offset_y = _mm_to_pixel_mapper(
        board_bounds, img.width, img.height
    )

    # For bottom view, X is mirrored around center
    mirror_x = view == "bottom"
    min_x, _min_y, max_x, _max_y = board_bounds

    # Font for pad numbers
    font_size = max(8, int(0.5 * scale_x))
    try:
        font = ImageFont.truetype("Arial", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    pad_count = 0
    for pad in all_pads:
        pcb_x = pad.x
        pcb_y = pad.y

        if mirror_x:
            pcb_x = min_x + (max_x - pcb_x)

        px, py = _pcb_to_pixel(pcb_x, pcb_y, board_bounds, scale_x, scale_y, offset_x, offset_y)

        half_w = pad.pad_width * scale_x / 2
        half_h = pad.pad_height * scale_y / 2

        is_tht = (round(pad.x, 2), round(pad.y, 2)) in tht_positions

        if is_tht:
            # THT pads: circle
            radius = max(half_w, half_h)
            draw.ellipse(
                [px - radius, py - radius, px + radius, py + radius],
                fill=_THT_PAD_COLOR,
            )
        else:
            # SMD pads: rectangle
            draw.rectangle(
                [px - half_w, py - half_h, px + half_w, py + half_h],
                fill=_SMD_PAD_COLOR,
            )

        # Draw pad number
        if pad.pad_number:
            draw.text((px, py), pad.pad_number, fill=_PAD_TEXT_COLOR, font=font, anchor="mm")

        pad_count += 1

    result = Image.alpha_composite(img, overlay)
    result.save(str(output_path), "PNG")
    logger.info("Applied pad overlay with %d pads", pad_count)
