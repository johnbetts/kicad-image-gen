"""Tests for 2D rendering."""

from __future__ import annotations

from pathlib import Path

import pytest

from kicad_image_gen.render_2d import LAYER_PRESETS, render_2d


class TestRender2D:
    def test_default_layers(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_default.png"
        result = render_2d(test_pcb, out)
        assert result == out
        assert out.stat().st_size > 1000

    def test_top_preset(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_top.png"
        render_2d(test_pcb, out, layers="top")
        assert out.stat().st_size > 1000

    def test_bottom_preset(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_bottom.png"
        render_2d(test_pcb, out, layers="bottom")
        assert out.stat().st_size > 1000

    def test_copper_only(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_copper.png"
        render_2d(test_pcb, out, layers="copper")
        assert out.stat().st_size > 1000

    def test_custom_layers(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_custom.png"
        render_2d(test_pcb, out, layers="F.Cu,Edge.Cuts")
        assert out.stat().st_size > 1000

    def test_custom_width(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_wide.png"
        render_2d(test_pcb, out, width=3200)
        assert out.stat().st_size > 1000

    def test_black_and_white(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_bw.png"
        render_2d(test_pcb, out, black_and_white=True)
        assert out.stat().st_size > 1000

    def test_mirror(self, test_pcb: Path, tmp_output: Path) -> None:
        out = tmp_output / "2d_mirror.png"
        render_2d(test_pcb, out, mirror=True)
        assert out.stat().st_size > 1000

    def test_missing_pcb_raises(self, tmp_output: Path) -> None:
        with pytest.raises(FileNotFoundError):
            render_2d("/nonexistent.kicad_pcb", tmp_output / "out.png")

    def test_layer_presets_exist(self) -> None:
        expected = {"all", "top", "bottom", "copper", "silkscreen", "fab"}
        assert set(LAYER_PRESETS.keys()) == expected
