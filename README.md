# kicad-image-gen

Generate PNG screenshots of KiCad PCBs -- 2D editor views and 3D renders -- headlessly from the command line. Designed for automated improvement loops where you need visual feedback without opening KiCad.

## Requirements

- **KiCad 10** (uses `kicad-cli` under the hood)
- **Python 3.10+**
- **rsvg-convert** (for SVG-to-PNG conversion): `brew install librsvg`

## Install

```bash
pip install -e .
```

## CLI Usage

```bash
# 2D editor-style screenshot (with ratsnest lines)
kicad-image-gen 2d board.kicad_pcb -o board_2d.png
kicad-image-gen 2d board.kicad_pcb --layers top --width 3200
kicad-image-gen 2d board.kicad_pcb --layers F.Cu,Edge.Cuts --no-ratsnest

# 3D rendered view
kicad-image-gen 3d board.kicad_pcb -o board_3d.png
kicad-image-gen 3d board.kicad_pcb --view iso -q high --floor
kicad-image-gen 3d board.kicad_pcb --view bottom --perspective

# Full set: 2D top/bottom + 3D top/bottom/iso
kicad-image-gen both board.kicad_pcb -o output_dir/
```

### 2D Options

| Flag | Description |
|------|-------------|
| `-l`, `--layers` | Layer list or preset: `all`, `top`, `bottom`, `copper`, `silkscreen`, `fab` |
| `-w`, `--width` | Output width in pixels (default: 2400) |
| `-t`, `--theme` | KiCad color theme name |
| `-m`, `--mirror` | Mirror the board |
| `--bw` | Black and white |

### 3D Options

| Flag | Description |
|------|-------------|
| `--view` | Preset: `top`, `bottom`, `iso`, `iso-back`, `iso-bottom`, `front`, `back`, `left`, `right` |
| `-w`, `--width` | Image width (default: 1600) |
| `--height` | Image height (default: 900) |
| `-q`, `--quality` | `basic` or `high` |
| `--perspective` | Perspective projection |
| `--floor` | Enable floor, shadows, post-processing |
| `--zoom` | Camera zoom level |
| `--rotate` | Custom rotation as `X,Y,Z` degrees |

## Python API

```python
from kicad_image_gen import render_2d, render_3d, render_all

# Individual renders
render_2d("board.kicad_pcb", "board_2d.png", layers="top", width=2400)
render_3d("board.kicad_pcb", "board_3d.png", view="iso", quality="high", floor=True)

# Batch: generates 2d_top, 2d_bottom, 3d_top, 3d_bottom, 3d_iso
results = render_all("board.kicad_pcb", "output/")
```

### Ratsnest Lines

2D renders include signal-net ratsnest lines by default (MST-based connectivity overlay). These show unrouted connections as green lines. Disable with `ratsnest=False`:

```python
render_2d("board.kicad_pcb", "out.png", ratsnest=False)
```

## Architecture

Thin wrapper around `kicad-cli` (KiCad 10's official CLI). No dependency on the deprecated `pcbnew` Python bindings.

- **2D pipeline**: `kicad-cli pcb export svg` -> ratsnest injection -> `rsvg-convert` -> PNG
- **3D pipeline**: `kicad-cli pcb render` -> PNG (direct output)
- **Ratsnest**: Parses `.kicad_pcb` S-expressions directly to extract net-pad positions, computes MST edges, injects `<line>` elements into SVG

## License

Apache 2.0
