# Bug Tracker — kicad-image-gen vs KiCad Editor Reference

## Resolved

### BUG-01: Mounting holes render as dark circles, not cyan filled [FIXED]
- **Commit**: a8b3e6b — injected cyan SVG circles at NPTH pad locations
- **Verify**: all 5 boards show cyan filled mounting holes matching reference

### BUG-02: THT pads missing annular ring (dark center hole) [FIXED]
- **Commit**: a8b3e6b — injected dark center dots at THT pad drill locations
- **Verify**: relay K1-K4 pads and connector J1-J4 pads show drill holes

### BUG-06: Power board cream/beige heatsink pads [WON'T FIX - SVG limitation]
- **Root cause**: SVG export shows raw F.Cu thermal pad; KiCad editor composites 3D model geometry over it
- **Workaround**: use `--composite` mode which uses the 3D renderer

### BUG-07: Ratsnest lines more visible than reference [FIXED]
- **Commit**: 1aeaafb — reduced opacity to 0.22, thinner strokes
- **Verify**: ratsnest now very subtle, matching KiCad editor faintness

## Open — P1

### BUG-03: Pad numbers not visible inside pads
- **Status**: pad_labels=False by default. When enabled, numbers overlay but don't render inside pads like KiCad editor
- **Fix needed**: Size pad number text relative to actual pad size from .kicad_pcb, render centered inside pad circle
- **Regression check**: enabling pad labels should not increase MAE vs reference (reference shows pad numbers)

## Open — P2

### BUG-04: Grid dots missing from background
- **Status**: deferred — cosmetic only, grid dot positions don't pixel-match reference
- **Fix**: optional SVG `<pattern>` overlay with 1mm dot grid in #232d3a
- **Regression check**: must not increase bg_error

### BUG-05: Board outline margins/annotations not matching
- **Status**: deferred — we use --exclude-drawing-sheet which hides margin annotations
- **Fix**: option to include drawing sheet, or inject board outline + dimension annotations
- **Regression check**: must not clip board content

### BUG-08: Net name labels visible on pads in reference but missing in ours
- **Status**: partially addressed via F.Fab layer; KiCad editor shows additional net annotations
- **Fix**: enable pad_labels with net names when pad_labels=True
- **Regression check**: labels must not obscure pad geometry

### BUG-09: Connector courtyard fill color differs
- **Status**: deferred — F.Fab renders as outline not fill in SVG export
- **Fix**: would require parsing fp_poly fills from footprint geometry
- **Regression check**: must not change non-connector areas

## Quality Scores History

| Date | val_bpb | avg_mae | avg_bg | bright_ratio | Notes |
|------|---------|---------|--------|-------------|-------|
| Baseline | 1.737 | 53.73 | 37.94 | 4.63 | Initial code |
| Autoresearch 20 iter | 1.070 | 36.50 | 18.40 | 1.60 | BG, ratsnest, labels |
| Custom theme + layers | 1.107 | 37.44 | 21.76 | 0.29 | Red pads, drill opt |
| Mounting holes + drill | 1.115 | 37.88 | 21.76 | 0.45 | Cyan holes, annular rings |
| Subtle ratsnest | 1.115 | 37.89 | 21.76 | 0.45 | Final current state |

## Regression Test Checklist
Run after every change: `pytest tests/ -q && python3 eval_harness.py`

1. [ ] All 18 unit tests pass
2. [ ] val_bpb does not increase by more than 0.05
3. [ ] Relay board: mounting holes cyan, pads red with drill dots
4. [ ] MCU board: ESP32 pads red, pad numbers visible in F.Fab
5. [ ] Analog board: J1-J4 connectors have red THT pads
6. [ ] Power board: cyan mounting holes in all 4 corners
7. [ ] Ethernet board: J1 connector pads visible, QFP pads red
