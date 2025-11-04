
#!/usr/bin/env python3
"""
recolor_png.py
----------------
Convert (near-)black pixels in a PNG to a target color while preserving alpha,
and remove (near-)white pixels by making them fully transparent.

Typical use case: barcodes/logos on transparent or white background where the
black ink should be re-colored (e.g., to brand color) and stray white/near-white
pixels should be removed.

Requirements:
    - Python 3.8+
    - Pillow (PIL fork)
    - NumPy

Install:
    pip install pillow numpy

Examples:
    # Recolor near-black to orange, remove near-white, with default thresholds
    python recolor_png.py input.png --target-color "#ff6600" -o output.png

    # Use custom thresholds (0..255). Higher = more tolerant.
    python recolor_png.py input.png -c 0,120,255 --black-thresh 32 --white-thresh 16

    # Batch process a folder (bash):
    for f in *.png; do python recolor_png.py "$f" -c "#111111" -o "out_${f}"; done

    # Process all PNGs in a folder into an output folder
    python recolor_png.py /path/to/input_dir -c "#ff6600" --output-dir /path/to/output_dir

    # Same, with a filename suffix and overwrite enabled
    python recolor_png.py /path/to/input_dir -c "#ff6600" --output-dir /path/to/output_dir \
        --suffix _recolored --overwrite

Notes:
    - PNG stores un-premultiplied RGBA, so we keep alpha as-is for recolored pixels.
    - For pixels classified as near-white, we set alpha to 0 and also zero the RGB
      to avoid any white fringe artifacts during later compositing.
"""

import argparse
import os
from typing import Tuple

import numpy as np
from PIL import Image


def parse_color(s: str) -> Tuple[int, int, int]:
    """Parse a color string like '#RRGGBB' or 'R,G,B' into an (R,G,B) tuple."""
    s = s.strip()
    if s.startswith('#'):
        s = s[1:]
        if len(s) == 3:
            # Expand short hex like 'f60' -> 'ff6600'
            s = ''.join(ch*2 for ch in s)
        if len(s) != 6:
            raise ValueError("Hex color must be 3 or 6 hex digits, e.g. #ff6600 or #f60")
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    # Comma-separated
    parts = s.split(',')
    if len(parts) != 3:
        raise ValueError("Color must be '#RRGGBB' or 'R,G,B'")
    try:
        r, g, b = (int(p.strip()) for p in parts)
    except Exception as e:
        raise ValueError("R,G,B must be integers") from e
    for v in (r, g, b):
        if not (0 <= v <= 255):
            raise ValueError("R,G,B values must be in 0..255")
    return (r, g, b)


def process_image(
    img: Image.Image,
    target_rgb: Tuple[int, int, int],
    black_thresh: int,
    white_thresh: int,
    exclude_almost_transparent: bool = True,
    almost_transparent_alpha: int = 0,
) -> Image.Image:
    """
    Recolor near-black pixels to target_rgb (preserving alpha) and make
    near-white pixels fully transparent (alpha=0).

    Args:
        img: Input PIL Image. Will be converted to RGBA internally.
        target_rgb: (R,G,B) color for recoloring near-black pixels.
        black_thresh: 0..255. Pixel considered near-black if R,G,B <= black_thresh.
        white_thresh: 0..255. Pixel considered near-white if R,G,B >= 255 - white_thresh.
        exclude_almost_transparent: If True, skip recoloring pixels with very low alpha.
        almost_transparent_alpha: Alpha threshold (inclusive) under which recolor is skipped.

    Returns:
        PIL Image in RGBA.
    """
    rgba = img.convert("RGBA")
    arr = np.array(rgba, dtype=np.uint16)  # avoid overflow on writes
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]
    a = arr[..., 3]

    # Masks
    # Consider near-white first: these become fully transparent
    # (set alpha=0 and zero RGB to prevent white fringes).
    if white_thresh < 0 or white_thresh > 255:
        raise ValueError("white_thresh must be in 0..255")
    if black_thresh < 0 or black_thresh > 255:
        raise ValueError("black_thresh must be in 0..255")

    white_min = 255 - white_thresh
    near_white_mask = (r >= white_min) & (g >= white_min) & (b >= white_min)

    # Apply near-white removal
    arr[..., 0][near_white_mask] = 0
    arr[..., 1][near_white_mask] = 0
    arr[..., 2][near_white_mask] = 0
    arr[..., 3][near_white_mask] = 0  # alpha to 0

    # Recompute masks after white removal (so we don't recolor freshly zeroed pixels)
    r = arr[..., 0]
    g = arr[..., 1]
    b = arr[..., 2]
    a = arr[..., 3]

    # Near-black mask (preserve alpha). Skip fully transparent pixels, and optionally
    # skip almost transparent pixels (to avoid recoloring anti-aliased edges with tiny alpha).
    near_black_mask = (r <= black_thresh) & (g <= black_thresh) & (b <= black_thresh)
    if exclude_almost_transparent:
        near_black_mask &= (a > almost_transparent_alpha)

    # Apply recolor for near-black pixels
    tr, tg, tb = target_rgb
    arr[..., 0][near_black_mask] = tr
    arr[..., 1][near_black_mask] = tg
    arr[..., 2][near_black_mask] = tb
    # alpha stays unchanged

    # Clip back to uint8 range and convert to PIL Image
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGBA")


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Recolor near-black to a target color and remove near-white to transparent.")
    p.add_argument("input", help="Input PNG file path OR a directory containing PNGs.")
    p.add_argument("-o", "--output", help="Output PNG file path. Defaults to '<name>_recolored.png'.")
    p.add_argument("--output-dir", help="When INPUT is a directory, write outputs here (created if missing).")
    p.add_argument("--suffix", default="_recolored", help="When batching, append this suffix before the extension unless --output is used per-file. Default: _recolored")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output files.")
    p.add_argument("--recursive", action="store_true", help="Recurse into subdirectories when INPUT is a directory.")
    p.add_argument("-c", "--target-color", required=True, help="Target color for near-black pixels. '#RRGGBB' or 'R,G,B'.")
    p.add_argument("--black-thresh", type=int, default=24, help="Tolerance for near-black (0..255). Default: 24.")
    p.add_argument("--white-thresh", type=int, default=16, help="Tolerance for near-white (0..255). Default: 16.")
    p.add_argument(
        "--keep-very-transparent",
        action="store_true",
        help="Do not recolor pixels with alpha <= almost-transparent threshold (default behavior is to skip recolor for those)."
    )
    p.add_argument(
        "--almost-transparent-alpha",
        type=int,
        default=0,
        help="Alpha threshold (0..255) under which recolor is skipped when not using --keep-very-transparent. Default: 0."
    )
    return p


def main():
    parser = build_argparser()
    args = parser.parse_args()

    in_path = args.input
    target = parse_color(args.target_color)

    def process_one(in_file: str, out_file: str):
        img = Image.open(in_file)
        out = process_image(
            img,
            target_rgb=target,
            black_thresh=args.black_thresh,
            white_thresh=args.white_thresh,
            exclude_almost_transparent=(not args.keep_very_transparent),
            almost_transparent_alpha=args.almost_transparent_alpha,
        )
        os.makedirs(os.path.dirname(out_file), exist_ok=True)
        if (not args.overwrite) and os.path.exists(out_file):
            print(f"Skip (exists): {out_file}")
            return
        out.save(out_file, format="PNG")
        print(f"Saved: {out_file}")

    if os.path.isdir(in_path):
        # Directory mode
        if not args.output_dir:
            raise SystemExit("When INPUT is a directory, you must provide --output-dir.")
        input_dir = in_path
        output_dir = args.output_dir
        patterns = [".png", ".PNG", ".Png", ".pNg", ".pnG"]
        candidates = []
        if args.recursive:
            for root, _, files in os.walk(input_dir):
                for fn in files:
                    if any(fn.endswith(ext) for ext in patterns):
                        candidates.append(os.path.join(root, fn))
        else:
            for fn in os.listdir(input_dir):
                if any(fn.endswith(ext) for ext in patterns):
                    candidates.append(os.path.join(input_dir, fn))
        if not candidates:
            print("No PNG files found to process.")
            return
        for src in candidates:
            rel = os.path.relpath(src, input_dir)
            base, _ = os.path.splitext(rel)
            # If --output provided, treat it as a pattern is not supported in dir mode
            # Construct output path in output_dir mirroring structure
            out_file = os.path.join(output_dir, base + args.suffix + ".png")
            process_one(src, out_file)
    else:
        # Single-file mode
        if not os.path.isfile(in_path):
            raise SystemExit(f"Input file not found: {in_path}")
        out_path = args.output
        if not out_path:
            base, _ = os.path.splitext(in_path)
            out_path = f"{base}{args.suffix}.png"
        process_one(in_path, out_path)


if __name__ == "__main__":
    main()
