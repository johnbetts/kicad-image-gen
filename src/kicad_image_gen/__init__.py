"""kicad-image-gen: Generate PNG screenshots of KiCad PCBs."""

from kicad_image_gen.render_2d import LAYER_PRESETS, render_2d
from kicad_image_gen.render_2d_composite import render_2d_composite
from kicad_image_gen.render_3d import render_3d

__all__ = ["render_2d", "render_2d_composite", "render_3d", "render_all", "LAYER_PRESETS"]


def render_all(
    pcb_path: str,
    output_dir: str,
    *,
    width_2d: int = 2400,
    width_3d: int = 1600,
    height_3d: int = 900,
    quality: str = "basic",
) -> dict[str, str]:
    """Generate a standard set of 2D and 3D images.

    Returns a dict mapping label → output path.
    """
    from pathlib import Path

    pcb = Path(pcb_path)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = pcb.stem
    results: dict[str, str] = {}

    for side, preset in [("top", "top"), ("bottom", "bottom")]:
        p = out / f"{stem}_2d_{side}.png"
        render_2d(pcb, p, layers=preset, width=width_2d, mirror=(side == "bottom"))
        results[f"2d_{side}"] = str(p)

    for view in ("top", "bottom", "iso"):
        p = out / f"{stem}_3d_{view}.png"
        render_3d(pcb, p, view=view, width=width_3d, height=height_3d, quality=quality)
        results[f"3d_{view}"] = str(p)

    return results
