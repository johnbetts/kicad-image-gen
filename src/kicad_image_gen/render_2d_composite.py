"""Composite 2D rendering: 3D top-down base + PIL overlay for ratsnest/pad labels.

Uses ``kicad-cli pcb render --side top`` (orthographic 3D) as the photorealistic
base image, then composites ratsnest lines and pad labels on top using Pillow.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from kicad_image_gen.core import run_kicad_cli
from kicad_image_gen.ratsnest import (
    nearest_neighbor_ratsnest,
    parse_board_bounds,
    parse_net_pad_map,
    parse_pad_labels,
)

logger = logging.getLogger(__name__)

# Ratsnest overlay styling
_RATSNEST_COLOR = (102, 136, 170, 60)  # RGBA semi-transparent blue-gray
_RATSNEST_LINE_WIDTH = 1

# Pad label styling
_PAD_NUM_COLOR = (0, 204, 204, 200)  # cyan
_NET_NAME_COLOR = (153, 136, 170, 180)  # muted purple


def _mm_to_pixel_mapper(
    board_bounds: tuple[float, float, float, float],
    img_width: int,
    img_height: int,
) -> tuple[float, float, float, float]:
    """Compute mapping parameters from PCB mm coords to pixel coords.

    The 3D renderer fits the board into the image with some margin.
    We estimate the margin and compute scale + offset.

    Returns (scale_x, scale_y, offset_x, offset_y).
    """
    min_x, min_y, max_x, max_y = board_bounds
    board_w = max_x - min_x
    board_h = max_y - min_y

    if board_w <= 0 or board_h <= 0:
        msg = f"Invalid board bounds: {board_bounds}"
        raise ValueError(msg)

    # The 3D renderer fits the board to the image maintaining aspect ratio.
    # It centers the board and adds some margin (~3-5% on each side).
    # We estimate this by computing the scale from whichever dimension is tighter.
    board_aspect = board_w / board_h
    img_aspect = img_width / img_height

    if board_aspect > img_aspect:
        # Board is wider relative to image — width is the constraining dimension
        # Empirically, kicad-cli render uses ~4% margin on each side
        margin_frac = 0.04
        usable_width = img_width * (1 - 2 * margin_frac)
        scale = usable_width / board_w
        offset_x = img_width * margin_frac
        offset_y = (img_height - board_h * scale) / 2
    else:
        # Board is taller — height constrains
        margin_frac = 0.04
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


def render_2d_composite(
    pcb_path: str | Path,
    output_path: str | Path,
    *,
    width: int = 4800,
    height: int | None = None,
    ratsnest: bool = True,
    pad_labels: bool = False,
    quality: str = "basic",
    background: str = "opaque",
) -> Path:
    """Render a composite 2D image: 3D top-down base + PIL overlays.

    Pipeline:
    1. Use ``kicad-cli pcb render --side top`` for the base PNG
    2. Parse ratsnest / pad data from the .kicad_pcb
    3. Overlay ratsnest lines and pad labels using Pillow

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        output_path: Output PNG file path.
        width: Image width in pixels.
        height: Image height in pixels (auto-calculated from board aspect if None).
        ratsnest: Draw ratsnest MST lines on the image.
        pad_labels: Draw pad numbers and net names on the image.
        quality: Render quality for the 3D base — "basic" or "high".
        background: Background mode — "opaque" or "transparent".

    Returns:
        Resolved output path.
    """
    pcb_path = Path(pcb_path)
    output_path = Path(output_path)

    if not pcb_path.is_file():
        msg = f"PCB file not found: {pcb_path}"
        raise FileNotFoundError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Parse board bounds for coordinate mapping
    board_bounds = parse_board_bounds(pcb_path)
    min_x, min_y, max_x, max_y = board_bounds
    board_w = max_x - min_x
    board_h = max_y - min_y

    # Auto-calculate height from board aspect ratio if not specified
    if height is None:
        if board_w > 0:
            height = int(width * board_h / board_w)
        else:
            height = int(width * 0.75)

    # Step 1: Generate base PNG via kicad-cli 3D render (top-down orthographic)
    # Always render with transparent background so we can composite onto dark navy
    base_png = _render_base(pcb_path, width, height, quality=quality, background="transparent")

    try:
        # Load base image and composite onto dark navy background
        raw_img = Image.open(base_png).convert("RGBA")
        bg = Image.new("RGBA", raw_img.size, (0, 16, 35, 255))  # KiCad dark navy
        base_img = Image.alpha_composite(bg, raw_img)

        # Step 2+3: Draw overlays if requested
        if ratsnest or pad_labels:
            # Compute coordinate mapping
            scale_x, scale_y, offset_x, offset_y = _mm_to_pixel_mapper(
                board_bounds, base_img.width, base_img.height
            )

            # Create transparent overlay
            overlay = Image.new("RGBA", base_img.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            if ratsnest:
                _draw_ratsnest(draw, pcb_path, board_bounds, scale_x, scale_y, offset_x, offset_y)

            if pad_labels:
                _draw_pad_labels(
                    draw, pcb_path, board_bounds, scale_x, scale_y, offset_x, offset_y
                )

            # Composite overlay onto base
            base_img = Image.alpha_composite(base_img, overlay)

        # Save final image
        base_img.save(str(output_path), "PNG")
    finally:
        # Clean up temp base PNG
        try:
            Path(base_png).unlink(missing_ok=True)
        except OSError:
            pass

    if not output_path.is_file() or output_path.stat().st_size == 0:
        msg = f"Composite render produced no output at {output_path}"
        raise RuntimeError(msg)

    logger.info("Composite 2D render → %s", output_path)
    return output_path


def _render_base(
    pcb_path: Path,
    width: int,
    height: int,
    *,
    quality: str = "basic",
    background: str = "opaque",
) -> Path:
    """Render the 3D top-down orthographic base PNG via kicad-cli."""
    fd_handle, tmp_path = tempfile.mkstemp(suffix=".png", prefix="kicad_composite_base_")
    import os

    os.close(fd_handle)
    tmp_png = Path(tmp_path)

    args: list[str] = [
        "pcb",
        "render",
        "--side",
        "top",
        "-w",
        str(width),
        "--height",
        str(height),
        "--quality",
        quality,
        "--background",
        background,
        "-o",
        str(tmp_png),
        str(pcb_path),
    ]

    run_kicad_cli(args, timeout=120)

    if not tmp_png.is_file() or tmp_png.stat().st_size == 0:
        msg = "3D base render produced no output"
        raise RuntimeError(msg)

    return tmp_png


def _draw_ratsnest(
    draw: ImageDraw.ImageDraw,
    pcb_path: Path,
    board_bounds: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    offset_x: float,
    offset_y: float,
) -> None:
    """Draw ratsnest MST lines on the overlay."""
    net_pads = parse_net_pad_map(pcb_path, include_power=True)
    line_count = 0

    for _net_name, pads in net_pads.items():
        if len(pads) < 2:
            continue
        edges = nearest_neighbor_ratsnest(pads)
        for i, j in edges:
            x1, y1 = _pcb_to_pixel(
                pads[i][0], pads[i][1], board_bounds, scale_x, scale_y, offset_x, offset_y
            )
            x2, y2 = _pcb_to_pixel(
                pads[j][0], pads[j][1], board_bounds, scale_x, scale_y, offset_x, offset_y
            )
            draw.line([(x1, y1), (x2, y2)], fill=_RATSNEST_COLOR, width=_RATSNEST_LINE_WIDTH)
            line_count += 1

    if line_count > 0:
        logger.info("Drew %d ratsnest lines on composite image", line_count)


def _draw_pad_labels(
    draw: ImageDraw.ImageDraw,
    pcb_path: Path,
    board_bounds: tuple[float, float, float, float],
    scale_x: float,
    scale_y: float,
    offset_x: float,
    offset_y: float,
) -> None:
    """Draw pad number and net name labels on the overlay."""
    all_pads = parse_pad_labels(pcb_path)
    label_count = 0

    # Compute font size relative to scale (roughly 0.6mm in PCB space)
    pad_font_size = max(8, int(0.6 * scale_x))
    net_font_size = max(6, int(0.35 * scale_x))

    # Try to get a reasonable font; fall back to default
    try:
        pad_font = ImageFont.truetype("Arial", pad_font_size)
        net_font = ImageFont.truetype("Arial", net_font_size)
    except (OSError, IOError):
        try:
            pad_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", pad_font_size)
            net_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", net_font_size)
        except (OSError, IOError):
            pad_font = ImageFont.load_default()
            net_font = ImageFont.load_default()

    for pad in all_pads:
        px, py = _pcb_to_pixel(pad.x, pad.y, board_bounds, scale_x, scale_y, offset_x, offset_y)

        # Pin number centered on pad
        if pad.pad_number:
            draw.text(
                (px, py),
                pad.pad_number,
                fill=_PAD_NUM_COLOR,
                font=pad_font,
                anchor="mm",  # middle-middle anchor
            )
            label_count += 1

        # Net name offset below-right
        if pad.net_name:
            draw.text(
                (px + pad_font_size * 0.8, py + pad_font_size * 0.6),
                pad.net_name,
                fill=_NET_NAME_COLOR,
                font=net_font,
                anchor="lt",  # left-top anchor
            )
            label_count += 1

    if label_count > 0:
        logger.info("Drew %d pad labels on composite image", label_count)
