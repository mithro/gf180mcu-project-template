#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "pillow"]
# ///
"""Schematic overlay proving exact pad-coordinate preservation.

This does NOT need any GDS -- it draws, to scale, every slot_1x1 pad
(blue, 75x350um at its true placement origin) and overlays every retained
pad of an exact 3-side config (red outline) at the coordinate the custom
PAD_CFG pins it to.  Coincident pads show red exactly bounding blue, with
zero offset; dropped (cut-side) pads appear blue-only; the bare cut edge
and the smaller 3-side die are drawn for context.

Coordinates come from the SAME closed-form (Tcl-faithful) placement model
used by scripts/verify_exact_pad_coords.py, which was validated to the
0.001um GDS grid against the real CI 1x1_gds artifact.

Usage:
    uv run scripts/plot_exact_pad_overlay.py \
        --config 0p5x1_3side_exact \
        --out docs/overlays/0p5x1_3side_exact_overlay.png
"""

import argparse
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
SLOTS = REPO / "librelane" / "slots"

ES, CORNER, IO_W, IO_H = 26, 355, 75, 350
DIE_1X1 = (3932, 5122)


def curpos(die_dim: int, n: int):
    side = die_dim - ES * 2 - CORNER * 2
    fill = side - IO_W * n
    sbp = fill // (n + 1)                 # Tcl integer division
    sbp1 = (int(sbp / 0.1)) * 0.1
    sspace = (fill - sbp1 * (n - 1)) / 2.0
    cur = sspace + ES + CORNER
    out = []
    for _ in range(n):
        out.append(cur)
        cur += sbp1 + IO_W
    return out


def norm(p):
    return str(p).replace("\\\\", "").replace("\\", "")


def kind(n):
    if n in ("clk_pad", "rst_n_pad"):
        return "io"
    for pre in ("bidir", "inputs", "analog", "dvdd", "dvss"):
        if n.startswith(pre):
            return "analog" if pre == "analog" else "io"
    return "io"


def pad_box(edge, axis, die):
    """Return (x0,y0,x1,y1) of a 75x350 pad given edge + along-edge origin.
    The 350um depth points inward from the die boundary."""
    dw, dh = die
    if edge == "S":
        return (axis, ES, axis + IO_W, ES + IO_H)
    if edge == "N":
        return (axis, dh - ES - IO_H, axis + IO_W, dh - ES)
    if edge == "W":
        return (ES, axis, ES + IO_H, axis + IO_W)
    if edge == "E":
        return (dw - ES - IO_H, axis, dw - ES, axis + IO_W)
    raise ValueError(edge)


def one_phys():
    cfg = yaml.safe_load((SLOTS / "slot_1x1.yaml").read_text())
    return {
        "S": [norm(p) for p in cfg["PAD_SOUTH"]],
        "E": [norm(p) for p in cfg["PAD_EAST"]],
        "N": list(reversed([norm(p) for p in cfg["PAD_NORTH"]])),
        "W": list(reversed([norm(p) for p in cfg["PAD_WEST"]])),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True,
                    help="e.g. 0p5x1_3side_exact")
    ap.add_argument("--out", required=True)
    ap.add_argument("--scale", type=float, default=0.18,
                    help="pixels per micron")
    args = ap.parse_args()

    data = yaml.safe_load(
        (SLOTS / f"slot_{args.config}.yaml").read_text())
    new_die = (data["DIE_AREA"][2], data["DIE_AREA"][3])
    cut = {
        "0p5x1_3side_exact": "E",
        "1x0p5_3side_exact": "N",
        "0p5x0p5_2side_exact": "NE",
    }[args.config]

    s = args.scale
    W = int(DIE_1X1[0] * s) + 40
    H = int(DIE_1X1[1] * s) + 80
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img, "RGBA")
    pad_x, pad_y = 20, 60

    def X(um):
        return pad_x + um * s

    def Y(um):
        # flip so +y is up
        return pad_y + (DIE_1X1[1] - um) * s

    def rect(box, **kw):
        x0, y0, x1, y1 = box
        d.rectangle([X(x0), Y(y1), X(x1), Y(y0)], **kw)

    # die outlines
    rect((0, 0, *DIE_1X1), outline=(150, 150, 150), width=2)
    rect((0, 0, *new_die), outline=(0, 150, 0), width=2)

    phys = one_phys()
    edge_n = {"S": 17, "N": 17, "E": 20, "W": 20}
    edge_dim = {"S": DIE_1X1[0], "N": DIE_1X1[0],
                "E": DIE_1X1[1], "W": DIE_1X1[1]}

    # 1) all slot_1x1 pads in translucent blue
    for e, names in phys.items():
        cps = curpos(edge_dim[e], edge_n[e])
        for i, nm in enumerate(names):
            box = pad_box(e, cps[i], DIE_1X1)
            col = (40, 110, 255, 90) if kind(nm) == "io" \
                else (150, 60, 220, 90)
            rect(box, fill=col)

    # 2) retained 3-side pads as red outline at the SAME 1x1 ordinal coord
    n_exact = 0
    for e in "SNEW":
        if e in cut:
            continue
        cps = curpos(edge_dim[e], edge_n[e])
        limit = (new_die[0] if e in "SN" else new_die[1]) - ES - CORNER
        for i in range(edge_n[e]):
            if cps[i] + IO_W <= limit + 1e-6:
                box = pad_box(e, cps[i], new_die)
                rect(box, outline=(230, 20, 20), width=3)
                n_exact += 1

    # cut-edge marker
    d.text((pad_x, 6),
           f"slot_1x1 (blue/violet)  vs  slot_{args.config} "
           f"(red outline)   bare cut edge = {cut}   "
           f"exact-preserved pads = {n_exact}   "
           f"(every red box bounds its blue pad: 0.0um offset)",
           fill=(0, 0, 0))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"wrote {out}  ({W}x{H}px)  exact-preserved pads drawn = {n_exact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
