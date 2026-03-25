#!/usr/bin/env python3
"""Fixed evaluation harness for autoresearch image quality loop.

DO NOT MODIFY — this is the fixed eval side of the autoresearch pattern.

Generates 2D images from reference PCBs, compares against reference screenshots,
and outputs a composite quality score (lower is better, like val_bpb).
"""

import subprocess
import sys
from pathlib import Path

# Paths
PROJECT = Path(__file__).parent
REF_DIR = PROJECT / "reference"
EVAL_DIR = Path("/tmp/kicad-image-gen-eval")

# Board configs: (pcb_filename, reference_image_filename)
BOARDS = [
    ("train_relay.kicad_pcb", "relay_reference_pcb_image.png"),
    ("train_mcu_core.kicad_pcb", "mcu_core_pcb_image.png"),
    ("train_analog_input.kicad_pcb", "analog_reference_pcb_image.png"),
    ("train_power.kicad_pcb", "power_reference_pcb_image.png"),
    ("train_ethernet.kicad_pcb", "ethernet_reference_pcb_image.png"),
]


def generate_images() -> list[tuple[str, Path, Path]]:
    """Generate 2D images for all reference boards. Returns (name, generated, reference)."""
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for pcb_file, ref_image in BOARDS:
        name = pcb_file.replace("train_", "").replace(".kicad_pcb", "")
        pcb_path = REF_DIR / pcb_file
        gen_path = EVAL_DIR / f"{name}_generated.png"
        ref_path = REF_DIR / ref_image

        if not pcb_path.is_file():
            print(f"SKIP {name}: PCB not found at {pcb_path}", file=sys.stderr)
            continue
        if not ref_path.is_file():
            print(f"SKIP {name}: Reference not found at {ref_path}", file=sys.stderr)
            continue

        cmd = ["kicad-image-gen", "2d", str(pcb_path), "-o", str(gen_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"FAIL {name}: {result.stderr[:200]}", file=sys.stderr)
            continue

        results.append((name, gen_path, ref_path))
    return results


def compute_pixel_score(gen_path: Path, ref_path: Path) -> dict[str, float]:
    """Compute pixel-level comparison metrics between generated and reference.

    Returns dict of metric_name -> score. All scores: lower is better.
    """
    try:
        from PIL import Image
        import numpy as np
    except ImportError:
        print("PIL/numpy required: pip install Pillow numpy", file=sys.stderr)
        return {"error": 999.0}

    gen = Image.open(gen_path).convert("RGB")
    ref = Image.open(ref_path).convert("RGB")

    # Resize generated to match reference dimensions for comparison
    if gen.size != ref.size:
        gen = gen.resize(ref.size, Image.Resampling.LANCZOS)

    gen_arr = np.array(gen, dtype=np.float32)
    ref_arr = np.array(ref, dtype=np.float32)

    # 1. Overall Mean Absolute Error (lower is better)
    mae = np.mean(np.abs(gen_arr - ref_arr))

    # 2. Background color error — sample corners (should be dark navy ~#1a1a3e)
    corner_size = 20
    corners = [
        (0, 0), (0, -corner_size), (-corner_size, 0), (-corner_size, -corner_size)
    ]
    bg_errors = []
    for cy, cx in corners:
        gen_corner = gen_arr[cy:cy+corner_size if cy+corner_size != 0 else None,
                            cx:cx+corner_size if cx+corner_size != 0 else None]
        ref_corner = ref_arr[cy:cy+corner_size if cy+corner_size != 0 else None,
                            cx:cx+corner_size if cx+corner_size != 0 else None]
        bg_errors.append(np.mean(np.abs(gen_corner - ref_corner)))
    bg_error = np.mean(bg_errors)

    # 3. Color histogram similarity (lower distance = better)
    hist_error = 0.0
    for ch in range(3):
        gen_hist = np.histogram(gen_arr[:, :, ch], bins=64, range=(0, 256))[0].astype(float)
        ref_hist = np.histogram(ref_arr[:, :, ch], bins=64, range=(0, 256))[0].astype(float)
        gen_hist /= gen_hist.sum() + 1e-8
        ref_hist /= ref_hist.sum() + 1e-8
        hist_error += np.sum(np.abs(gen_hist - ref_hist))
    hist_error /= 3.0

    # 4. Structural: ratio of bright pixels (pads, text, lines)
    gen_bright = np.mean(gen_arr > 128)
    ref_bright = np.mean(ref_arr > 128)
    bright_ratio_error = abs(gen_bright - ref_bright) * 100

    return {
        "mae": round(mae, 2),
        "bg_error": round(bg_error, 2),
        "hist_error": round(hist_error, 4),
        "bright_ratio_error": round(bright_ratio_error, 2),
    }


def main():
    print("=== Generating evaluation images ===")
    pairs = generate_images()

    if not pairs:
        print("val_bpb 999.0")
        print("error No images generated")
        sys.exit(1)

    print(f"\n=== Scoring {len(pairs)} boards ===")
    all_scores: dict[str, list[float]] = {}

    for name, gen_path, ref_path in pairs:
        scores = compute_pixel_score(gen_path, ref_path)
        print(f"\n{name}:")
        for k, v in scores.items():
            print(f"  {k}: {v}")
            all_scores.setdefault(k, []).append(v)

    # Composite score (weighted, lower is better)
    avg_mae = sum(all_scores.get("mae", [999])) / max(len(all_scores.get("mae", [1])), 1)
    avg_bg = sum(all_scores.get("bg_error", [999])) / max(len(all_scores.get("bg_error", [1])), 1)
    avg_hist = sum(all_scores.get("hist_error", [999])) / max(len(all_scores.get("hist_error", [1])), 1)
    avg_bright = sum(all_scores.get("bright_ratio_error", [999])) / max(len(all_scores.get("bright_ratio_error", [1])), 1)

    # Composite: weighted sum normalized to ~0-10 range
    composite = (avg_mae / 25.0) * 0.4 + (avg_bg / 25.0) * 0.3 + avg_hist * 0.2 + (avg_bright / 5.0) * 0.1

    print(f"\n=== Composite Scores ===")
    print(f"avg_mae {avg_mae:.2f}")
    print(f"avg_bg_error {avg_bg:.2f}")
    print(f"avg_hist_error {avg_hist:.4f}")
    print(f"avg_bright_ratio_error {avg_bright:.2f}")
    print(f"val_bpb {composite:.4f}")


if __name__ == "__main__":
    main()
