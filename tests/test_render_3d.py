"""Tests for 3D rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_image_gen.render_3d import render_3d, _VIEW_PRESETS


class TestRender3D:
    def test_top_view(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_top.png"
        result = render_3d(test_pcb, out, view="top")
        assert result == out
        assert out.stat().st_size > 1000

    def test_iso_view(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_iso.png"
        result = render_3d(test_pcb, out, view="iso")
        assert result == out
        assert out.stat().st_size > 1000

    def test_bottom_view(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_bottom.png"
        render_3d(test_pcb, out, view="bottom")
        assert out.stat().st_size > 1000

    def test_high_quality_with_floor(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_hq.png"
        render_3d(test_pcb, out, view="iso", quality="high", floor=True)
        assert out.stat().st_size > 1000

    def test_custom_dimensions(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_small.png"
        render_3d(test_pcb, out, view="top", width=800, height=600)
        assert out.stat().st_size > 100

    def test_custom_rotation(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "3d_custom.png"
        render_3d(test_pcb, out, view="custom", rotate="-30,0,60", perspective=True)
        assert out.stat().st_size > 1000

    def test_missing_pcb_raises(self, tmp_output: Path) -> None:
        with pytest.raises(FileNotFoundError):
            render_3d("/nonexistent.kicad_pcb", tmp_output / "out.png")

    def test_all_presets_defined(self) -> None:
        expected = {
            "top",
            "bottom",
            "front",
            "back",
            "left",
            "right",
            "iso",
            "iso-back",
            "iso-bottom",
        }
        assert set(_VIEW_PRESETS.keys()) == expected
