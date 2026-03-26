"""Ratsnest computation from .kicad_pcb files.

Parses S-expression PCB files directly to extract net-pad connectivity,
then computes minimum spanning trees for signal nets. The resulting edges
can be injected into SVG exports as visual ratsnest lines.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

# Power/ground nets excluded from ratsnest
POWER_NETS: frozenset[str] = frozenset(
    {
        "GND",
        "VIN",
        "VCC",
        "+3V3",
        "+5V",
        "+12V",
        "+24V",
        "+3.3V",
        "+1.8V",
        "VBUS",
        "VBAT",
        "EARTH",
        "GNDREF",
        "GNDA",
        "GNDD",
        "VDDA",
        "VDDD",
        "VDD",
        "AVCC",
        "DVCC",
    }
)

# Regex patterns for parsing .kicad_pcb S-expressions
_RE_FOOTPRINT_AT = re.compile(
    r'\(footprint\s+"[^"]*"\s*\n'
    r"(?:.*?\n)*?"
    r"\s*\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)",
    re.MULTILINE,
)

_RE_AT = re.compile(r"\(at\s+([-\d.]+)\s+([-\d.]+)(?:\s+([-\d.]+))?\)")
# Matches both KiCad 9 format: (net 1 "GND") and KiCad 10 format: (net "GND")
_RE_NET = re.compile(r'\(net\s+(?:\d+\s+)?"([^"]*?)"\)')


def _rotate_point(px: float, py: float, angle_deg: float) -> tuple[float, float]:
    """Rotate point around origin using KiCad's CW rotation convention.

    KiCad stores positive angles as clockwise rotation in screen space
    (Y-down coordinate system). The CW rotation matrix is:
        x' = x*cos + y*sin
        y' = -x*sin + y*cos
    """
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return px * cos_a + py * sin_a, -px * sin_a + py * cos_a


_RE_PAD_NUM = re.compile(r'\(pad\s+"([^"]*)"')
_RE_REF = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"')


def parse_board_bounds(pcb_path: str | Path) -> tuple[float, float, float, float]:
    """Parse the board outline bounding box from Edge.Cuts layer.

    Scans top-level graphic primitives (gr_line, gr_rect, gr_arc) on the
    Edge.Cuts layer and returns the overall bounding box.

    Uses a block-based approach: finds each gr_* block, checks if it
    references Edge.Cuts, then extracts start/end/mid coordinates.

    Returns:
        Tuple of (min_x, min_y, max_x, max_y) in mm.

    Raises:
        ValueError: If no Edge.Cuts geometry is found.
    """
    text = Path(pcb_path).read_text(encoding="utf-8")

    xs: list[float] = []
    ys: list[float] = []

    coord_re = re.compile(r"\((start|end|mid)\s+([-\d.]+)\s+([-\d.]+)\)")

    # First try top-level (gr_*), then fall back to footprint (fp_*) if needed
    pattern = r"\(gr_(?:line|rect|arc|poly)\b"
    matches = list(re.finditer(pattern, text))
    if not matches:
        # Fall back: also include fp_* (but note these coords may be relative)
        pattern = r"\((?:gr_|fp_)(?:line|rect|arc|poly)\b"
        matches = list(re.finditer(pattern, text))

    for m in matches:
        block_start = m.start()
        # Find the closing paren by counting nesting
        depth = 0
        block_end = block_start
        for i in range(block_start, min(block_start + 2000, len(text))):
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
                if depth == 0:
                    block_end = i + 1
                    break
        block = text[block_start:block_end]

        # Check if this block is on Edge.Cuts
        if '"Edge.Cuts"' not in block:
            continue

        # Extract all start/end/mid coordinates
        for cm in coord_re.finditer(block):
            xs.append(float(cm.group(2)))
            ys.append(float(cm.group(3)))

    if not xs:
        msg = f"No Edge.Cuts geometry found in {pcb_path}"
        raise ValueError(msg)

    return (min(xs), min(ys), max(xs), max(ys))


def _parse_footprint_blocks(
    pcb_path: str | Path,
) -> list[tuple[float, float, float, str, str]]:
    """Parse footprint blocks, yielding (fp_x, fp_y, fp_rot, block_text, refdes)."""
    text = Path(pcb_path).read_text(encoding="utf-8")
    fp_starts = [m.start() for m in re.finditer(r"^\s+\(footprint\s", text, re.MULTILINE)]
    results = []

    for i, start in enumerate(fp_starts):
        end = fp_starts[i + 1] if i + 1 < len(fp_starts) else len(text)
        block = text[start:end]

        at_match = _RE_AT.search(block[:500])
        if not at_match:
            continue

        fp_x = float(at_match.group(1))
        fp_y = float(at_match.group(2))
        fp_rot = float(at_match.group(3)) if at_match.group(3) else 0.0

        ref_match = _RE_REF.search(block[:2000])
        refdes = ref_match.group(1) if ref_match else ""

        results.append((fp_x, fp_y, fp_rot, block, refdes))
    return results


def parse_net_pad_map(
    pcb_path: str | Path,
    *,
    include_power: bool = False,
) -> dict[str, list[tuple[float, float]]]:
    """Parse a .kicad_pcb file and build net → absolute pad positions map.

    Args:
        pcb_path: Path to .kicad_pcb file.
        include_power: If True, include power/ground nets. Default False.
    """
    net_pads: dict[str, list[tuple[float, float]]] = {}

    for fp_x, fp_y, fp_rot, block, _refdes in _parse_footprint_blocks(pcb_path):
        pad_starts = [m.start() for m in re.finditer(r"\(pad\s", block)]
        for ps in pad_starts:
            pad_block = block[ps : ps + 500]

            net_match = _RE_NET.search(pad_block)
            if not net_match:
                continue
            net_name = net_match.group(1)
            if not net_name:
                continue
            if not include_power and (net_name.upper() in POWER_NETS or net_name in POWER_NETS):
                continue

            pad_at = _RE_AT.search(pad_block)
            if not pad_at:
                continue

            pad_x = float(pad_at.group(1))
            pad_y = float(pad_at.group(2))
            rx, ry = _rotate_point(pad_x, pad_y, fp_rot)
            abs_x, abs_y = fp_x + rx, fp_y + ry
            net_pads.setdefault(net_name, []).append((abs_x, abs_y))

    return net_pads


@dataclass(frozen=True)
class PadLabel:
    """A pad with its absolute position, net name, pad number, and component refdes."""

    x: float
    y: float
    net_name: str
    pad_number: str
    refdes: str
    pad_width: float = 1.0
    pad_height: float = 1.0

    @property
    def label(self) -> str:
        """Short label: net name (or pad number if no net)."""
        return self.net_name or self.pad_number


_RE_PAD_SIZE = re.compile(r"\(size\s+([-\d.]+)\s+([-\d.]+)\)")
_RE_PAD_DRILL = re.compile(r"\(drill\s+([-\d.]+)")


@dataclass(frozen=True)
class MountingHole:
    """A mounting hole with absolute position and size."""

    x: float
    y: float
    diameter: float  # pad size in mm


@dataclass(frozen=True)
class THTpad:
    """A through-hole pad with position, size, and drill."""

    x: float
    y: float
    size: float  # pad diameter in mm
    drill: float  # drill diameter in mm


def parse_mounting_holes(pcb_path: str | Path) -> list[MountingHole]:
    """Parse mounting hole (NPTH) pad positions from a .kicad_pcb file."""
    holes: list[MountingHole] = []
    for fp_x, fp_y, fp_rot, block, _refdes in _parse_footprint_blocks(pcb_path):
        for m in re.finditer(r"\(pad\s", block):
            pad_block = block[m.start() : m.start() + 500]
            if "np_thru_hole" not in pad_block:
                continue
            pad_at = _RE_AT.search(pad_block)
            if not pad_at:
                continue
            pad_x, pad_y = float(pad_at.group(1)), float(pad_at.group(2))
            rx, ry = _rotate_point(pad_x, pad_y, fp_rot)
            size_match = _RE_PAD_SIZE.search(pad_block)
            diameter = float(size_match.group(1)) if size_match else 3.0
            holes.append(MountingHole(x=fp_x + rx, y=fp_y + ry, diameter=diameter))
    return holes


def parse_tht_pads(pcb_path: str | Path) -> list[THTpad]:
    """Parse through-hole (plated) pad positions with size and drill from a .kicad_pcb file."""
    pads: list[THTpad] = []
    for fp_x, fp_y, fp_rot, block, _refdes in _parse_footprint_blocks(pcb_path):
        for m in re.finditer(r"\(pad\s", block):
            pad_block = block[m.start() : m.start() + 500]
            if "thru_hole" not in pad_block or "np_thru_hole" in pad_block:
                continue
            pad_at = _RE_AT.search(pad_block)
            if not pad_at:
                continue
            pad_x, pad_y = float(pad_at.group(1)), float(pad_at.group(2))
            rx, ry = _rotate_point(pad_x, pad_y, fp_rot)
            size_match = _RE_PAD_SIZE.search(pad_block)
            drill_match = _RE_PAD_DRILL.search(pad_block)
            size = float(size_match.group(1)) if size_match else 1.5
            drill = float(drill_match.group(1)) if drill_match else 0.8
            pads.append(THTpad(x=fp_x + rx, y=fp_y + ry, size=size, drill=drill))
    return pads


def parse_pad_labels(pcb_path: str | Path) -> list[PadLabel]:
    """Parse all pads from a .kicad_pcb file with positions and labels.

    Returns every pad (including power nets) with its absolute position,
    net name, pad number, and parent component reference designator.
    """
    labels: list[PadLabel] = []

    for fp_x, fp_y, fp_rot, block, refdes in _parse_footprint_blocks(pcb_path):
        pad_starts = [m.start() for m in re.finditer(r"\(pad\s", block)]
        for ps in pad_starts:
            pad_block = block[ps : ps + 500]

            pad_num_match = _RE_PAD_NUM.search(pad_block)
            pad_number = pad_num_match.group(1) if pad_num_match else ""

            net_match = _RE_NET.search(pad_block)
            net_name = net_match.group(1) if net_match else ""

            pad_at = _RE_AT.search(pad_block)
            if not pad_at:
                continue

            pad_x = float(pad_at.group(1))
            pad_y = float(pad_at.group(2))
            rx, ry = _rotate_point(pad_x, pad_y, fp_rot)

            size_match = _RE_PAD_SIZE.search(pad_block)
            pw = float(size_match.group(1)) if size_match else 1.0
            ph = float(size_match.group(2)) if size_match else 1.0

            labels.append(
                PadLabel(
                    x=fp_x + rx,
                    y=fp_y + ry,
                    net_name=net_name,
                    pad_number=pad_number,
                    refdes=refdes,
                    pad_width=pw,
                    pad_height=ph,
                )
            )

    return labels


def nearest_neighbor_ratsnest(
    points: list[tuple[float, float]],
) -> list[tuple[int, int]]:
    """Compute ratsnest edges matching KiCad's approach.

    Each pad connects to its nearest same-net pad. This produces the same
    line pattern as KiCad's ratsnest — direct shortest connections without
    the crossing artifacts that MST can create.
    """
    n = len(points)
    if n < 2:
        return []
    if n == 2:
        return [(0, 1)]

    edges: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for i in range(n):
        best_j = -1
        best_dist = float("inf")
        for j in range(n):
            if i == j:
                continue
            dx = points[i][0] - points[j][0]
            dy = points[i][1] - points[j][1]
            dist = dx * dx + dy * dy
            if dist < best_dist:
                best_dist = dist
                best_j = j
        if best_j >= 0:
            edge = (min(i, best_j), max(i, best_j))
            if edge not in seen:
                seen.add(edge)
                edges.append(edge)
    return edges


def minimum_spanning_tree(
    points: list[tuple[float, float]],
) -> list[tuple[int, int]]:
    """Compute MST edges for 2D points via Prim's algorithm."""
    n = len(points)
    if n < 2:
        return []
    if n == 2:
        return [(0, 1)]

    in_tree = [False] * n
    min_cost = [float("inf")] * n
    min_edge: list[int] = [-1] * n
    edges: list[tuple[int, int]] = []

    in_tree[0] = True
    for j in range(1, n):
        dx = points[0][0] - points[j][0]
        dy = points[0][1] - points[j][1]
        min_cost[j] = dx * dx + dy * dy
        min_edge[j] = 0

    for _ in range(n - 1):
        best = -1
        best_cost = float("inf")
        for j in range(n):
            if not in_tree[j] and min_cost[j] < best_cost:
                best_cost = min_cost[j]
                best = j
        if best < 0:
            break
        in_tree[best] = True
        edges.append((min_edge[best], best))
        for j in range(n):
            if not in_tree[j]:
                dx = points[best][0] - points[j][0]
                dy = points[best][1] - points[j][1]
                dist2 = dx * dx + dy * dy
                if dist2 < min_cost[j]:
                    min_cost[j] = dist2
                    min_edge[j] = best

    return edges
