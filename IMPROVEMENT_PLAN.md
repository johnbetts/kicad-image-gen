# Improvement Plan for kicad-image-gen

## Autoresearch Results Summary

20 iterations, val_bpb: **1.7371 → 1.0697** (38% improvement)

| Metric | Baseline | Final | Notes |
|--------|----------|-------|-------|
| avg_mae | 53.73 | 36.50 | Mean absolute pixel error vs reference |
| avg_bg_error | 37.94 | 18.40 | Background color match |
| avg_hist_error | 1.65 | 1.16 | Color histogram distance |
| bright_ratio_error | 4.63 | 1.60 | Bright pixel ratio match |

## Remaining Gaps (What's Left to Fix)

### 1. Pad Color Rendering (highest impact, ~30% of remaining MAE)
**Problem**: Generated pads render as light blue/white circles. Reference shows red/orange filled pads with dark annular rings and small red drill markers. This is the single biggest visual difference.

**Root cause**: The KiCad SVG export renders pads as the *layer color* (mask, copper), not the interactive editor's composite pad rendering. The editor composites F.Cu + F.Mask + drill into the familiar red-with-hole look.

**Fix approaches**:
- **A) Custom KiCad color theme**: Create a `.json` theme file that sets copper/mask colors to match the editor's composite appearance. This would make the SVG export produce pad colors closer to the reference. Estimated effort: 2 hours. Expected impact: large.
- **B) Post-process pad rendering**: Parse pad positions/sizes from `.kicad_pcb`, then inject custom SVG circles (red fill + dark ring + drill dot) at each pad location on top of the SVG export. Estimated effort: 4 hours. Expected impact: large but complex.
- **C) Use `kicad-cli pcb render` for 2D**: The 3D renderer's top-down orthographic view renders pads much closer to the editor look (it does the composite). Tradeoff: no SVG overlay capability (ratsnest, labels). Could be used as a "photo-realistic 2D" mode.

### 2. Mounting Hole Rendering (~15% of remaining MAE)
**Problem**: Reference shows mounting holes as large cyan filled circles with magenta courtyard squares. Our export shows them differently based on theme.

**Fix**: Same as above — a custom theme with `F.Cu` and pad colors tuned, or explicit SVG injection of mounting hole circles based on pad parsing (type=np_thru_hole pads with large drill).

### 3. Grid Dots (~10% of remaining bg_error)
**Problem**: KiCad editor shows a dot grid pattern (1mm spacing) that contributes to the background appearance. The grid was tested (iter 6) but discarded because dot positions don't align with reference screenshots pixel-for-pixel.

**Fix**: Not worth pursuing for pixel-match scoring since grid position is arbitrary. However, adding an *optional* grid overlay would improve visual authenticity. Use SVG `<pattern>` with proper dot size/color matching KiCad's grid (RGB ~35,45,58 dots on #001023 background).

### 4. Edge Cuts / Board Outline Visibility (~5% of remaining MAE)
**Problem**: Reference shows magenta edge cuts prominently with a visible board margin area. Our export clips to board area.

**Fix**: Add `--page-size-mode 0` or `1` option to show drawing sheet frame, or inject a board outline rect from the Edge.Cuts layer parsed from `.kicad_pcb`.

### 5. Copper Pour Hatching (~5% of remaining MAE)
**Problem**: Reference MCU board shows hatched fill zones (red diagonal lines) for copper pours. The SVG export shows zones differently.

**Fix**: Enable `--check-zones` flag in SVG export to ensure zone fills are rendered. May also need to ensure the `.kicad_pcb` has zones filled.

### 6. Interactive Annotations (pad numbers, net names)
**Problem**: The KiCad editor shows pad numbers (cyan, inside pads) and net names only when hovering/selecting. The autoresearch loop disabled these (iter 8) because they hurt the score vs "clean" reference screenshots.

**Fix**: Make these toggleable (already done: `pad_labels=False` default, `ratsnest=True` default). For improvement loop usage, users want these ON. For matching screenshots, they should be OFF. Consider a `--mode editor` vs `--mode review` CLI flag.

## Recommended Next Steps (Priority Order)

### Phase 1: Custom Color Theme (Highest ROI)
Create a KiCad color theme JSON file that produces SVG exports visually matching the editor:
1. Export the `user` theme from KiCad preferences
2. Adjust pad/copper/mask colors to produce the composite red-pad look in SVG
3. Bundle as `kicad_image_gen_theme.json` and install to KiCad's color directory
4. Default to this theme in render_2d.py

### Phase 2: Pad Overlay Enhancement
For boards where pads need to look "interactive" (like the editor):
1. Parse pad positions, sizes, shapes, and drill from `.kicad_pcb`
2. Inject SVG circles/rects with red fill, dark annular ring, cyan pad number
3. Make this an opt-in `--editor-pads` flag

### Phase 3: Composite 2D Mode
Combine the 3D renderer's top-down orthographic view (which produces editor-like pad rendering) with SVG overlay injection:
1. `kicad-cli pcb render --side top` → base PNG
2. Parse `.kicad_pcb` for pad/net positions
3. Overlay ratsnest lines and labels using PIL/Pillow compositing
4. This gives "best of both worlds": photorealistic base + data overlays

### Phase 4: Eval Harness Improvements
- Add SSIM (structural similarity) metric alongside MAE
- Per-board scoring breakdown in results.tsv
- Automated before/after visual comparison HTML report
- CI integration: run eval on every PR

### Phase 5: Feature Additions
- `--mode editor` (pad numbers, net names, grid) vs `--mode fab` (clean, no overlays)
- Animated GIF mode cycling through views (top → iso → bottom)
- Diff mode: overlay two PCB versions showing what changed
- Net highlighting: color specific nets for review
