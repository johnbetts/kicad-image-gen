"""Core utilities: KiCad CLI discovery and subprocess helpers."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_KICAD_CLI_SEARCH_PATHS = [
    "/Applications/KiCad 10/KiCad.app/Contents/MacOS/kicad-cli",
    "/Applications/KiCad 9/KiCad.app/Contents/MacOS/kicad-cli",
    "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli",
]


class KiCadCLINotFoundError(FileNotFoundError):
    """Raised when kicad-cli cannot be located."""


def find_kicad_cli() -> str:
    """Locate the kicad-cli executable.

    Search order:
    1. ``$KICAD_CLI`` environment variable
    2. Known macOS application bundle paths (KiCad 10 → 9 → default)
    3. ``$PATH`` lookup via ``shutil.which``
    """
    env_cli = os.environ.get("KICAD_CLI")
    if env_cli and Path(env_cli).is_file():
        return env_cli

    for candidate in _KICAD_CLI_SEARCH_PATHS:
        if Path(candidate).is_file():
            return candidate

    path_cli = shutil.which("kicad-cli")
    if path_cli:
        return path_cli

    msg = "kicad-cli not found. Install KiCad 10, set $KICAD_CLI, or add kicad-cli to your PATH."
    raise KiCadCLINotFoundError(msg)


def run_kicad_cli(
    args: list[str],
    *,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    """Run a kicad-cli command, returning the CompletedProcess.

    Raises subprocess.CalledProcessError on non-zero exit.
    """
    kicad_cli = find_kicad_cli()
    cmd = [kicad_cli, *args]
    logger.debug("Running: %s", " ".join(cmd))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )
