"""Shared test fixtures for kicad-image-gen."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Use a known test PCB — override via KICAD_TEST_PCB env var
_DEFAULT_TEST_PCB = Path.home() / "Dropbox/Source/kicad-test/variants/smd-0603/smd-0603.kicad_pcb"


@pytest.fixture
def test_pcb() -> Path:
    """Path to a real .kicad_pcb file for integration tests."""
    pcb = Path(os.environ.get("KICAD_TEST_PCB", str(_DEFAULT_TEST_PCB)))
    if not pcb.is_file():
        pytest.skip(f"Test PCB not found: {pcb}")
    return pcb


@pytest.fixture
def tmp_output(tmp_path: Path) -> Path:
    """Temporary output directory."""
    return tmp_path
