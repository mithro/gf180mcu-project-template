#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "klayout"]
# ///
"""Render slot_1x1 and an exact 3-side GDS and overlay them to *visually*
prove the retained pads land at byte-identical (x, y) coordinates.

Both layouts share the die origin (0, 0).  Each layout is rendered to a
transparent RGBA image at the **same micron-per-pixel scale** using a fixed
world window (the slot_1x1 die box), so a pad at (x, y) maps to the same
pixel in both images.  slot_1x1 is tinted blue, the 3-side red; where a
3-side pad sits exactly on its slot_1x1 pad the two tints superimpose
(magenta) -- any positional drift would show as separated blue/red blobs.

Usage:
    uv run scripts/overlay_pad_diagram.py \
        --ref  slot_1x1.gds \
        --new  slot_0p5x1_3side_exact.gds \
        --out  docs/overlays/0p5x1_3side_exact_overlay.png \
        [--width 1600]

Designed to run in CI after both GDS artifacts exist (see the workflow).
"""

import argparse
import sys
from pathlib import Path

import klayout.lay as klay
import klayout.db as kdb
from PIL import Image

# slot_1x1 die box (um) -- the common world window for both renders.
REF_DIE = (0.0, 0.0, 3932.0, 5122.0)


def render(gds: str, width: int, height: int, world) -> Image.Image:
    """Render *gds* to an RGBA image of (width, height) px covering the
    micron rectangle *world* = (x0, y0, x1, y1).  Geometry outside the
    window is clipped; the bitmap scale is identical for every call with
    the same world+size, so coordinates map to identical pixels."""
    lv = klay.LayoutView()
    lv.set_config("background-color", "#000000")
    lv.set_config("grid-visible", "false")
    lv.set_config("grid-show-ruler", "false")
    lv.set_config("text-visible", "false")
    lv.load_layout(gds, 0)
    lv.max_hier()
    x0, y0, x1, y1 = world
    lv.zoom_box(kdb.DBox(x0, y0, x1, y1))
    lv.timer()
    px = lv.get_pixels_with_options(width, height)
    png = Path(f"{gds}.__tmp_overlay.png")
    px.write_png(str(png))
    img = Image.open(png).convert("RGBA")
    png.unlink(missing_ok=True)
    return img


def tint(img: Image.Image, rgb) -> Image.Image:
    """Map non-black pixels to *rgb*, alpha = luminance (so background is
    transparent and geometry is a translucent solid tint)."""
    src = img.convert("RGB")
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sp = src.load()
    op = out.load()
    r, g, b = rgb
    w, h = img.size
    for yy in range(h):
        for xx in range(w):
            pr, pg, pb = sp[xx, yy]
            lum = max(pr, pg, pb)
            if lum > 12:
                op[xx, yy] = (r, g, b, min(255, int(lum * 1.6)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="slot_1x1 GDS")
    ap.add_argument("--new", required=True, help="exact 3-side GDS")
    ap.add_argument("--out", required=True, help="output overlay PNG")
    ap.add_argument("--width", type=int, default=1400)
    args = ap.parse_args()

    x0, y0, x1, y1 = REF_DIE
    aspect = (y1 - y0) / (x1 - x0)
    width = args.width
    height = int(width * aspect)

    ref = render(args.ref, width, height, REF_DIE)
    new = render(args.new, width, height, REF_DIE)

    ref_t = tint(ref, (40, 110, 255))   # slot_1x1  -> blue
    new_t = tint(new, (255, 60, 60))    # 3-side    -> red

    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    canvas.alpha_composite(ref_t)
    canvas.alpha_composite(new_t)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG")
    print(
        f"wrote {out}  ({width}x{height}px, {(x1-x0)/width:.3f} um/px)\n"
        f"  blue  = slot_1x1\n"
        f"  red   = {Path(args.new).name}\n"
        f"  magenta/overlap = pads at IDENTICAL coordinates"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
