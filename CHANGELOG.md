# Changelog

## [0.1.0] - 2026-03-24

### Added
- Initial release
- 2D PCB editor-style PNG export via `kicad-cli pcb export svg` + `rsvg-convert`
- 3D rendered PNG export via `kicad-cli pcb render` with 9 view presets
- Ratsnest line injection into 2D SVG exports (MST-based signal net visualization)
- CLI with `2d`, `3d`, and `both` subcommands
- Python API: `render_2d()`, `render_3d()`, `render_all()`
- Layer presets: all, top, bottom, copper, silkscreen, fab
- 3D view presets: top, bottom, front, back, left, right, iso, iso-back, iso-bottom
- SVG-to-PNG fallback chain: rsvg-convert, cairosvg, sips
- Standalone `.kicad_pcb` S-expression parser for net-pad extraction (no pcbnew dependency)
