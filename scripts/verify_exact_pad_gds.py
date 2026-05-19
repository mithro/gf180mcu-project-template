#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["klayout"]
# ///
"""True-silicon proof of exact pad-coordinate preservation.

Extracts the IO-pad instance origins from a *built* slot_1x1 GDS and a
*built* exact 3-side GDS (both produced by the LibreLane Chip flow) and
asserts that every retained 3-side pad origin coincides -- to the 0.001um
GDS grid -- with a slot_1x1 pad origin.  Only the 2 deliberately relocated
analog pads are allowed to differ.

This complements scripts/verify_exact_pad_coords.py (closed-form proof):
this one inspects the *actual fabricated layout*, not a model.

Usage:
    uv run scripts/verify_exact_pad_gds.py \
        --ref slot_1x1.gds --new slot_0p5x1_3side_exact.gds \
        --expect-exact 32 --max-relocated 2
"""

import argparse
import sys

import klayout.db as kdb

IO_MARKERS = ("_io__",)  # gf180mcu_fd_io__ / gf180mcu_ws_io__


def pad_origins(gds: str) -> set[tuple[float, float]]:
    layout = kdb.Layout()
    layout.read(gds)
    top = list(layout.top_cells())[0]
    dbu = layout.dbu
    out = set()
    for inst in top.each_inst():
        cname = layout.cell(inst.cell_index).name
        if not any(m in cname for m in IO_MARKERS):
            continue
        if "__fill" in cname or "__cor" in cname:
            continue
        t = inst.trans
        out.add((round(t.disp.x * dbu, 3), round(t.disp.y * dbu, 3)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="built slot_1x1 GDS")
    ap.add_argument("--new", required=True, help="built exact 3-side GDS")
    ap.add_argument("--expect-exact", type=int, required=True,
                    help="number of coordinate-preserved pads expected")
    ap.add_argument("--max-relocated", type=int, default=2,
                    help="max non-preserved pads (relocated analog)")
    args = ap.parse_args()

    ref = pad_origins(args.ref)
    new = pad_origins(args.new)
    shared = sorted(new & ref)
    extra = sorted(new - ref)

    print(f"slot_1x1 IO-pad origins:  {len(ref)}")
    print(f"3-side    IO-pad origins:  {len(new)}")
    print(f"\nEXACT coincident origins ({len(shared)}):")
    for p in shared:
        print(f"  {p}")
    print(f"\nNon-preserved origins ({len(extra)}, "
          f"expect <= {args.max_relocated} relocated analog):")
    for p in extra:
        print(f"  {p}")

    ok = (len(shared) >= args.expect_exact
          and len(extra) <= args.max_relocated)
    print(
        f"\n{'PASS' if ok else 'FAIL'}: {len(shared)} pads at EXACT "
        f"slot_1x1 coordinates in the built GDS "
        f"(expected >= {args.expect_exact}); "
        f"{len(extra)} relocated (<= {args.max_relocated})"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
