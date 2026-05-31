#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["klayout", "pillow"]
# ///
"""Overlay every pad of an exact-config build on the slot_1x1 pad grid,
reading BOTH pad sets straight from the built GDS -- no model, no theory.

Every IO pad instance (structural corner & filler cells excluded) is drawn at
its true GDS origin.  slot_1x1's pads are the light-blue reference grid; the
exact config's pads are drawn on top -- GREEN where a pad sits exactly on a
slot_1x1 pad coordinate, solid RED where it does not.  Nothing is skipped or
hidden, so an off-grid or extra pad is impossible to miss.  (This replaces the
former closed-form/ideal-model drawing, which could not show such a pad.)

Usage:
    uv run scripts/plot_exact_pad_overlay.py \
        --ref slot_1x1.gds --new exact.gds --out overlay.png [--title NAME]
"""

import argparse
import sys
from pathlib import Path

import klayout.db as kdb
from PIL import Image, ImageDraw

IO_MARKERS = ("_io__",)  # gf180mcu_fd_io__ / gf180mcu_ws_io__


def pads(gds: str):
    """Return (pads, (die_w, die_h)) where pads is a list of
    (origin_xy, bbox_x0y0x1y1, cellname) for every IO pad instance, with the
    structural corner/filler cells excluded (consistent with the verifier)."""
    layout = kdb.Layout()
    layout.read(gds)
    top = list(layout.top_cells())[0]
    dbu = layout.dbu
    out = []
    for inst in top.each_inst():
        cn = layout.cell(inst.cell_index).name
        if not any(m in cn for m in IO_MARKERS):
            continue
        if "__fill" in cn or "__cor" in cn:
            continue
        t = inst.trans
        bb = inst.bbox()
        origin = (round(t.disp.x * dbu, 3), round(t.disp.y * dbu, 3))
        rect = (bb.left * dbu, bb.bottom * dbu, bb.right * dbu, bb.top * dbu)
        out.append((origin, rect, cn))
    die = top.bbox()
    return out, (die.right * dbu, die.top * dbu)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="built slot_1x1 GDS")
    ap.add_argument("--new", required=True, help="built exact-config GDS")
    ap.add_argument("--out", required=True, help="output overlay PNG")
    ap.add_argument("--title", default="", help="title label (default: --new stem)")
    ap.add_argument("--width", type=int, default=1400)
    args = ap.parse_args()

    ref_pads, ref_die = pads(args.ref)
    new_pads, new_die = pads(args.new)
    ref_origins = {o for o, _, _ in ref_pads}

    # Common world frame = the slot_1x1 die box (both share die origin 0,0),
    # so the exact die sits in the kept corner and the cut-away area is shown.
    w_um = max(ref_die[0], new_die[0])
    h_um = max(ref_die[1], new_die[1])
    margin = 40
    s = args.width / w_um
    img = Image.new("RGB", (args.width + 2 * margin, int(h_um * s) + 2 * margin),
                    (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")

    def x(u):
        return margin + u * s

    def y(u):
        return margin + (h_um - u) * s  # flip so +y is up

    def box(r, **kw):
        d.rectangle([x(r[0]), y(r[3]), x(r[2]), y(r[1])], **kw)

    lw = max(2, int(s * 2))
    box((0, 0, ref_die[0], ref_die[1]), outline=(150, 150, 150), width=2)
    box((0, 0, new_die[0], new_die[1]), outline=(0, 170, 0), width=2)

    # slot_1x1 reference grid (translucent blue)
    for _, r, _ in ref_pads:
        box(r, fill=(40, 110, 255, 60), outline=(40, 110, 255, 150))

    # exact-config pads, drawn from the real GDS: green if aligned, red if not
    n_align = n_un = 0
    for o, r, _ in new_pads:
        if o in ref_origins:
            box(r, outline=(0, 160, 0, 255), width=lw)
            n_align += 1
        else:
            box(r, fill=(230, 30, 30, 220), outline=(150, 0, 0, 255), width=lw)
            n_un += 1

    title = args.title or Path(args.new).stem
    d.text(
        (margin, 12),
        f"{title}: {len(new_pads)} pads read from GDS -- "
        f"{n_align} aligned to slot_1x1 (green outline), "
        f"{n_un} UNALIGNED (solid red).  blue = slot_1x1 pad grid.",
        fill=(0, 0, 0),
    )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG")
    print(f"wrote {out}  ({len(new_pads)} pads: {n_align} aligned, "
          f"{n_un} unaligned)")
    # This is a visualizer; the pass/fail gate is verify_exact_pad_gds.py.
    return 0


if __name__ == "__main__":
    sys.exit(main())
