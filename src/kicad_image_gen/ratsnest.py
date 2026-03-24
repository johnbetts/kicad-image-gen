"""Ratsnest computation from .kicad_pcb files.

Parses S-expression PCB files directly to extract net-pad connectivity,
then computes minimum spanning trees for signal nets. The resulting edges
can be injected into SVG exports as visual ratsnest lines.
"""

from __future__ import annotations

import math
import re
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
_RE_NET = re.compile(r'\(net\s+\d+\s+"([^"]*?)"\)')


def _rotate_point(px: float, py: float, angle_deg: float) -> tuple[float, float]:
    """Rotate point around origin (KiCad CW convention in Y-down coords)."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return px * cos_a - py * sin_a, px * sin_a + py * cos_a


def parse_net_pad_map(pcb_path: str | Path) -> dict[str, list[tuple[float, float]]]:
    """Parse a .kicad_pcb file and build net → absolute pad positions map.

    Extracts footprint positions and pad positions/nets using regex,
    computes absolute pad coordinates accounting for footprint rotation.
    Filters out power/ground nets and unnamed nets.
    """
    text = Path(pcb_path).read_text(encoding="utf-8")
    net_pads: dict[str, list[tuple[float, float]]] = {}

    # Split into footprint blocks
    # Find each "(footprint" and its matching close
    fp_starts = [m.start() for m in re.finditer(r"^\s+\(footprint\s", text, re.MULTILINE)]

    for i, start in enumerate(fp_starts):
        # Find the extent of this footprint block
        end = fp_starts[i + 1] if i + 1 < len(fp_starts) else len(text)
        block = text[start:end]

        # Extract footprint position
        at_match = _RE_AT.search(block[:500])  # Position is near the top
        if not at_match:
            continue

        fp_x = float(at_match.group(1))
        fp_y = float(at_match.group(2))
        fp_rot = float(at_match.group(3)) if at_match.group(3) else 0.0

        # Find all pads in this footprint
        pad_starts = [m.start() for m in re.finditer(r"\(pad\s", block)]
        for ps in pad_starts:
            # Extract a reasonable chunk for the pad definition
            pad_block = block[ps : ps + 500]

            # Get net name
            net_match = _RE_NET.search(pad_block)
            if not net_match:
                continue
            net_name = net_match.group(1)
            if not net_name or net_name.upper() in POWER_NETS or net_name in POWER_NETS:
                continue

            # Get pad position (relative to footprint)
            pad_at = _RE_AT.search(pad_block)
            if not pad_at:
                continue

            pad_x = float(pad_at.group(1))
            pad_y = float(pad_at.group(2))

            # Compute absolute position
            rx, ry = _rotate_point(pad_x, pad_y, fp_rot)
            abs_x, abs_y = fp_x + rx, fp_y + ry

            net_pads.setdefault(net_name, []).append((abs_x, abs_y))

    return net_pads


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
