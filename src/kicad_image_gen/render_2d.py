"""2D PCB editor-style image export via SVG → PNG conversion."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from kicad_image_gen.core import find_kicad_cli
from kicad_image_gen.ratsnest import minimum_spanning_tree, parse_net_pad_map, parse_pad_labels

logger = logging.getLogger(__name__)

_DEFAULT_LAYERS_TOP = "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Fab,Edge.Cuts"
_DEFAULT_LAYERS_BOTTOM = "B.Cu,B.SilkS,B.Mask,B.Fab,Edge.Cuts"
_DEFAULT_WIDTH = 4800

# Layer presets for convenience
LAYER_PRESETS: dict[str, str] = {
    "all": "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,F.Fab,B.Fab,F.CrtYd,B.CrtYd,Edge.Cuts",
    "top": "F.Cu,F.SilkS,F.Mask,F.Fab,Edge.Cuts",
    "bottom": "B.Cu,B.SilkS,B.Mask,B.Fab,Edge.Cuts",
    "copper": "F.Cu,B.Cu,Edge.Cuts",
    "silkscreen": "F.SilkS,B.SilkS,Edge.Cuts",
    "fab": "F.Fab,B.Fab,F.CrtYd,B.CrtYd,Edge.Cuts",
}


def render_2d(
    pcb_path: str | Path,
    output_path: str | Path,
    *,
    layers: str | None = None,
    width: int = _DEFAULT_WIDTH,
    theme: str | None = None,
    background: str | None = None,
    mirror: bool = False,
    black_and_white: bool = False,
    ratsnest: bool = True,
    pad_labels: bool = True,
) -> Path:
    """Export a 2D editor-style PNG image of a KiCad PCB.

    Pipeline: kicad-cli pcb export svg → inject overlays → convert to PNG.

    Args:
        pcb_path: Path to the ``.kicad_pcb`` file.
        output_path: Output PNG file path.
        layers: Comma-separated layer list, or a preset name (top, bottom, all,
                copper, silkscreen, fab). Defaults to all visible layers.
        width: Output image width in pixels.
        theme: KiCad color theme name.
        background: Not used for SVG export (SVG background is theme-controlled).
        mirror: Mirror the board (useful for bottom layer views).
        black_and_white: Render in black and white.
        ratsnest: Inject ratsnest lines showing signal-net connectivity (default True).
        pad_labels: Inject pad net-name labels at each pad location (default True).

    Returns:
        Resolved output path.
    """
    pcb_path = Path(pcb_path)
    output_path = Path(output_path)
    if not pcb_path.is_file():
        msg = f"PCB file not found: {pcb_path}"
        raise FileNotFoundError(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Resolve layer preset
    resolved_layers = LAYER_PRESETS.get(layers or "", layers or _DEFAULT_LAYERS_TOP)

    # Step 1: Export SVG
    svg_path = _export_svg(
        pcb_path,
        resolved_layers,
        theme=theme,
        mirror=mirror,
        black_and_white=black_and_white,
    )
    if svg_path is None:
        msg = "SVG export failed — ensure kicad-cli supports 'pcb export svg'"
        raise RuntimeError(msg)

    # Step 2: Inject overlays into SVG
    if ratsnest or pad_labels:
        _inject_overlays(svg_path, pcb_path, ratsnest=ratsnest, pad_labels=pad_labels)

    # Step 3: Convert SVG → PNG
    try:
        png_path = _convert_svg_to_png(svg_path, output_path, width)
    finally:
        _cleanup(svg_path)

    if png_path is None:
        msg = (
            "No SVG→PNG converter found. Install one of: "
            "rsvg-convert (librsvg), cairosvg (pip), or use macOS sips."
        )
        raise RuntimeError(msg)

    logger.info("2D export (%s) → %s", resolved_layers, output_path)
    return png_path


def _export_svg(
    pcb_path: Path,
    layers: str,
    *,
    theme: str | None = None,
    mirror: bool = False,
    black_and_white: bool = False,
) -> Path | None:
    """Run kicad-cli pcb export svg, return path to temp SVG or None."""
    kicad_cli = find_kicad_cli()

    with tempfile.TemporaryDirectory(prefix="kicad_svg_") as tmpdir:
        svg_out = Path(tmpdir) / f"{pcb_path.stem}.svg"
        cmd = [
            kicad_cli,
            "pcb",
            "export",
            "svg",
            "--mode-single",
            "-l",
            layers,
            "--exclude-drawing-sheet",
            "--page-size-mode",
            "2",
            "-o",
            str(svg_out),
        ]

        if theme:
            cmd.extend(["--theme", theme])
        if mirror:
            cmd.append("--mirror")
        if black_and_white:
            cmd.append("--black-and-white")

        cmd.append(str(pcb_path))

        logger.debug("SVG export: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
            logger.warning("SVG export failed: %s", exc)
            return None

        if result.returncode != 0:
            logger.warning("SVG export exited %d: %s", result.returncode, result.stderr[:500])
            return None

        if not svg_out.is_file():
            return None

        # Persist outside tmpdir
        fd, tmp_path = tempfile.mkstemp(suffix=".svg", prefix="kicad_2d_")
        os.close(fd)
        shutil.copy2(svg_out, tmp_path)
        return Path(tmp_path)


def _convert_svg_to_png(
    svg_path: Path,
    output_path: Path,
    width: int,
) -> Path | None:
    """Convert SVG to PNG using the first available backend."""
    for converter in (_convert_rsvg, _convert_cairosvg, _convert_sips):
        result = converter(svg_path, output_path, width)
        if result is not None:
            return result
    return None


def _convert_rsvg(svg_path: Path, output_path: Path, width: int) -> Path | None:
    """Convert via rsvg-convert (librsvg)."""
    rsvg = shutil.which("rsvg-convert")
    if not rsvg:
        return None
    cmd = [rsvg, "-w", str(width), "-o", str(output_path), str(svg_path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and output_path.is_file():
            return output_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _convert_cairosvg(svg_path: Path, output_path: Path, width: int) -> Path | None:
    """Convert via cairosvg Python library."""
    try:
        import cairosvg  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(output_path),
            output_width=width,
        )
        if output_path.is_file() and output_path.stat().st_size > 0:
            return output_path
    except Exception as exc:
        logger.warning("cairosvg failed: %s", exc)
    return None


def _convert_sips(svg_path: Path, output_path: Path, width: int) -> Path | None:
    """Convert via macOS sips (last resort — limited SVG support)."""
    sips = shutil.which("sips")
    if not sips:
        return None
    # sips can convert some SVGs but has limited support.
    # It works better with PDF intermediary, but try direct first.
    cmd = [
        sips,
        "-s",
        "format",
        "png",
        "-z",
        str(width),
        str(width),
        str(svg_path),
        "--out",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 0:
            return output_path
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


# ---------------------------------------------------------------------------
# SVG overlay injection (ratsnest + pad labels)
# ---------------------------------------------------------------------------

_SVG_NS = "http://www.w3.org/2000/svg"
_RATSNEST_COLOR = "#44ee44"
_RATSNEST_OPACITY = "0.55"
_RATSNEST_STROKE_WIDTH = "0.25"
_LABEL_FONT_SIZE = "0.6"
_LABEL_COLOR = "#ffffff"
_LABEL_BG_COLOR = "#000000"
_LABEL_BG_OPACITY = "0.65"


def _inject_overlays(
    svg_path: Path,
    pcb_path: Path,
    *,
    ratsnest: bool = True,
    pad_labels: bool = True,
) -> None:
    """Inject ratsnest lines and/or pad labels into the exported SVG."""
    ET.register_namespace("", _SVG_NS)
    try:
        tree = ET.parse(str(svg_path))
    except ET.ParseError:
        logger.warning("Failed to parse SVG for overlay injection")
        return

    root = tree.getroot()
    viewbox = root.get("viewBox")
    if not viewbox:
        logger.debug("SVG has no viewBox — skipping overlays")
        return

    modified = False

    # --- Ratsnest lines ---
    if ratsnest:
        net_pads = parse_net_pad_map(pcb_path)
        if net_pads:
            ratsnest_group = ET.SubElement(root, f"{{{_SVG_NS}}}g")
            ratsnest_group.set("id", "ratsnest")
            ratsnest_group.set("opacity", _RATSNEST_OPACITY)

            line_count = 0
            for _net_name, pads in net_pads.items():
                if len(pads) < 2:
                    continue
                edges = minimum_spanning_tree(pads)
                for i, j in edges:
                    line = ET.SubElement(ratsnest_group, f"{{{_SVG_NS}}}line")
                    line.set("x1", f"{pads[i][0]:.4f}")
                    line.set("y1", f"{pads[i][1]:.4f}")
                    line.set("x2", f"{pads[j][0]:.4f}")
                    line.set("y2", f"{pads[j][1]:.4f}")
                    line.set("stroke", _RATSNEST_COLOR)
                    line.set("stroke-width", _RATSNEST_STROKE_WIDTH)
                    line_count += 1

            if line_count > 0:
                modified = True
                logger.info("Injected %d ratsnest lines into SVG", line_count)

    # --- Pad labels ---
    if pad_labels:
        all_pads = parse_pad_labels(pcb_path)
        if all_pads:
            labels_group = ET.SubElement(root, f"{{{_SVG_NS}}}g")
            labels_group.set("id", "pad-labels")

            font_size = float(_LABEL_FONT_SIZE)
            label_count = 0
            for pad in all_pads:
                text_str = pad.label
                if not text_str:
                    continue

                # Background rectangle for readability
                text_width = len(text_str) * font_size * 0.55
                rect = ET.SubElement(labels_group, f"{{{_SVG_NS}}}rect")
                rect.set("x", f"{pad.x + 0.3:.4f}")
                rect.set("y", f"{pad.y - font_size * 0.8:.4f}")
                rect.set("width", f"{text_width:.4f}")
                rect.set("height", f"{font_size * 1.1:.4f}")
                rect.set("fill", _LABEL_BG_COLOR)
                rect.set("opacity", _LABEL_BG_OPACITY)
                rect.set("rx", "0.15")

                # Text label
                text_el = ET.SubElement(labels_group, f"{{{_SVG_NS}}}text")
                text_el.set("x", f"{pad.x + 0.4:.4f}")
                text_el.set("y", f"{pad.y:.4f}")
                text_el.set("font-size", _LABEL_FONT_SIZE)
                text_el.set("font-family", "monospace")
                text_el.set("fill", _LABEL_COLOR)
                text_el.text = text_str
                label_count += 1

            if label_count > 0:
                modified = True
                logger.info("Injected %d pad labels into SVG", label_count)

    if modified:
        tree.write(str(svg_path), xml_declaration=True, encoding="unicode")


def _cleanup(path: Path) -> None:
    """Remove temp file, ignoring errors."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
