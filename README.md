# kicad-image-gen

Generate PNG screenshots of KiCad PCBs that look like the PCB editor -- headlessly, from the command line or Python.

## Why This Exists

I was designing PCBs with an AI-assisted workflow ([kicad-ai-workflow](https://github.com/johnbetts/kicad-ai-workflow)) and hit a wall: every time I wanted Claude to review a board layout, I had to manually screenshot the KiCad PCB editor and paste the image into the conversation. Over and over. For every iteration.

I tried `kicad-cli` exports, but the raw SVG/PDF output looked nothing like the editor -- wrong colors, no ratsnest, no pad labels, missing mounting holes. The images were useless for AI-driven layout review because they didn't show the information an EE needs to evaluate placement: which pads connect where, what's routed, what isn't.

So I built this tool. It generates images that match the KiCad PCB editor appearance -- dark navy background, red pads, cyan mounting holes, visible ratsnest lines, pad numbers and net names -- using a custom color theme, SVG post-processing, and careful layer ordering.

Now my workflow is fully automated: generate a board, render images, feed them to Claude for review, apply fixes, re-render, repeat. The whole loop runs inside [autoresearch](https://github.com/johnbetts/kicad-ai-workflow) iterations -- modify placement, render, score, keep or discard -- without ever opening KiCad.

## Requirements

- **KiCad 10** (uses `kicad-cli` under the hood)
- **Python 3.10+**
- **rsvg-convert** (for SVG-to-PNG conversion): `brew install librsvg`

## Install

```bash
pip install -e .

# Install the custom KiCad color theme (required for editor-matching colors)
cp kicad_image_gen_theme.json ~/Library/Preferences/kicad/10.0/colors/kicad_image_gen.json
```

## CLI Usage

```bash
# 2D editor-style screenshot (with ratsnest + pad labels)
kicad-image-gen 2d board.kicad_pcb -o board_2d.png

# Composite mode (3D render base + overlay -- photorealistic)
kicad-image-gen 2d --composite board.kicad_pcb -o board_composite.png

# 3D rendered view
kicad-image-gen 3d board.kicad_pcb --view iso -q high --floor -o board_3d.png

# Full set: 2D top/bottom + 3D top/bottom/iso
kicad-image-gen both board.kicad_pcb -o output_dir/
```

### 2D Options

| Flag | Description |
|------|-------------|
| `-l`, `--layers` | Layer list or preset: `all`, `top`, `bottom`, `copper`, `silkscreen`, `fab` |
| `-w`, `--width` | Output width in pixels (default: 4800) |
| `-t`, `--theme` | KiCad color theme name (default: `kicad_image_gen`) |
| `--composite` | Use 3D renderer as base with PIL overlays |
| `--no-ratsnest` | Hide ratsnest lines |
| `--no-pad-labels` | Hide pad numbers and net names |
| `--pad-labels` | Show pad numbers and net names (default) |
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
from kicad_image_gen import render_2d, render_3d, render_2d_composite, render_all

# 2D editor view with ratsnest and pad labels
render_2d("board.kicad_pcb", "board_2d.png", width=4800)

# 2D clean (no overlays)
render_2d("board.kicad_pcb", "board_clean.png", ratsnest=False, pad_labels=False)

# 3D isometric
render_3d("board.kicad_pcb", "board_3d.png", view="iso", quality="high", floor=True)

# Composite (photorealistic base + ratsnest overlay)
render_2d_composite("board.kicad_pcb", "board_composite.png", ratsnest=True)

# Full set: 2d_top, 2d_bottom, 3d_top, 3d_bottom, 3d_iso
results = render_all("board.kicad_pcb", "output/")
```

## What It Renders

The 2D output matches the KiCad PCB editor appearance:

- **Red pads** via custom color theme with transparent soldermask
- **Cyan mounting holes** injected at NPTH pad locations
- **Ratsnest lines** (MST-based) showing unrouted net connectivity
- **Pad labels** with pin numbers (cyan) and net names scaled to pad size
- **Dark navy background** with subtle board substrate fill
- **Yellow edge cuts** for board outline visibility
- **Board margin** via viewBox padding

## Architecture

Thin wrapper around `kicad-cli` (KiCad 10's official CLI). No dependency on the deprecated `pcbnew` Python bindings.

- **2D pipeline**: `kicad-cli pcb export svg` with custom theme and layer ordering -> SVG post-processing (background, mounting holes, ratsnest, pad labels) -> `rsvg-convert` -> PNG
- **3D pipeline**: `kicad-cli pcb render` -> PNG (direct output)
- **Composite pipeline**: `kicad-cli pcb render --side top` -> Pillow overlay compositing
- **PCB parsing**: Standalone `.kicad_pcb` S-expression regex parser for pads, nets, bounds, mounting holes

## Using with AI Agents

This tool was built specifically for AI-driven PCB design loops. Other Claude Code skills can call it directly:

```python
from kicad_image_gen import render_2d
render_2d(pcb_path, output_path)
```

Or via CLI in any agent's bash:

```bash
kicad-image-gen 2d board.kicad_pcb -o placement.png
```

## License

Apache 2.0
