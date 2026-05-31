#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["klayout"]
# ///
"""Strict true-silicon proof of exact pad-coordinate preservation.

Extracts EVERY IO-pad instance origin from a *built* exact-config GDS and the
*built* slot_1x1 GDS and asserts that **every** pad in the exact config sits on
a slot_1x1 pad origin -- with no extras and no duplicates.

The check is deliberately pad-type-agnostic: it does not know or care whether a
pad is a signal, power, clock or analog pad.  Any pad whose origin is not a
slot_1x1 pad origin (an *unaligned* pad), and any duplicate pad at an origin
(an *extra* pad), fails the check.  "Exact" means exact: a pad either lands on a
real slot_1x1 coordinate or it does not belong here.

(Corner and filler cells are structural padring fill, not pads, and their
positions legitimately differ on a smaller die, so they are excluded.)

Usage:
    uv run scripts/verify_exact_pad_gds.py --ref slot_1x1.gds --new exact.gds
"""

import argparse
import math
import sys
from collections import Counter

import klayout.db as kdb

IO_MARKERS = ("_io__",)  # gf180mcu_fd_io__ / gf180mcu_ws_io__


def pad_origins(gds: str) -> list[tuple[float, float]]:
    """Origins (um, rounded to the 0.001um GDS grid) of every IO *pad*
    instance -- excluding only the structural corner/filler cells."""
    layout = kdb.Layout()
    layout.read(gds)
    top = list(layout.top_cells())[0]
    dbu = layout.dbu
    out = []
    for inst in top.each_inst():
        cname = layout.cell(inst.cell_index).name
        if not any(m in cname for m in IO_MARKERS):
            continue
        if "__fill" in cname or "__cor" in cname:
            continue
        t = inst.trans
        out.append((round(t.disp.x * dbu, 3), round(t.disp.y * dbu, 3)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="built slot_1x1 GDS")
    ap.add_argument("--new", required=True, help="built exact-config GDS")
    args = ap.parse_args()

    ref_list = pad_origins(args.ref)
    new_list = pad_origins(args.new)
    ref = set(ref_list)
    counts = Counter(new_list)

    aligned = sorted(o for o in counts if o in ref)
    unaligned = sorted(o for o in counts if o not in ref)
    duplicated = sorted(o for o, c in counts.items() if c > 1)

    print(f"slot_1x1 pad origins:        {len(ref)}")
    print(f"exact-config pad instances:  {len(new_list)} "
          f"({len(counts)} distinct)")
    print(f"\nAligned to a slot_1x1 pad ({len(aligned)}):")
    for p in aligned:
        print(f"  {p}")
    if duplicated:
        print(f"\nDUPLICATE (extra) pads ({len(duplicated)}):")
        for p in duplicated:
            print(f"  {p} x{counts[p]}")
    print(f"\nUNALIGNED pads ({len(unaligned)}):")
    for p in unaligned:
        nearest = min(ref, key=lambda r: math.dist(p, r)) if ref else None
        d = math.dist(p, nearest) if nearest else -1
        print(f"  {p}  (nearest slot_1x1 pad {nearest}, {d:.3f} um away)")

    ok = not unaligned and not duplicated
    print(
        f"\n{'PASS' if ok else 'FAIL'}: {len(aligned)} pads aligned to "
        f"slot_1x1, {len(unaligned)} unaligned, {len(duplicated)} "
        f"duplicated.  "
        + ("Every pad matches an exact slot_1x1 coordinate."
           if ok else
           "Off-grid or extra pads present -- not an exact slot.")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
