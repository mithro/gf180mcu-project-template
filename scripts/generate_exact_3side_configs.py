#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Generate *exact-pad* 3-side slot configurations.

Unlike the approximate ``slot_*_3side.yaml`` configs (which let LibreLane's
``pad_cfg.tcl`` auto-distribute pads evenly along each edge -- giving only the
same *pitch* as ``slot_1x1`` but different absolute coordinates), the configs
produced here pin **every** retained pad to the *exact* (x, y) coordinate it
occupies in a real ``slot_1x1`` build.

Mechanism
=========
``OpenROAD.PadRing`` sources ``$PAD_CFG`` (``read_pad_cfg``).  The stock
``pad_cfg.tcl`` distributes pads with::

    space_between_pads = (side_len - sum_pad_widths) / (n_pads + 1)   # then rounded

so coordinates depend on the die dimension *and* the pad count of that edge.
A half-size die therefore moves every pad.

We instead emit a **custom per-config ``PAD_CFG``** (``pad_cfg_exact.tcl`` +
a generated ``*_pad_locs.tcl`` data file) that replaces the distribution loop
with an explicit ``place_pad -row <ROW> -location <offset> <inst> -master
<inst's own master>`` for each pad, where ``<offset>`` is the exact
along-edge placement coordinate measured from a real ``slot_1x1`` GDS.

slot_1x1 ground truth (verified against the CI ``1x1_gds`` artifact;
all GF180 IO cells are 75um wide, corner 355um, seal ring 26um)::

    South / North edge:  offset(i) = 488.5 + i * 180.0   (i = 0..16, W->E)
    East  / West  edge:  offset(i) = 519.0 + i * 211.0   (i = 0..19, S->N)

These two arithmetic progressions are *exactly* what ``pad_cfg.tcl`` produces
for ``slot_1x1`` (die [0,0,3932,5122], 17 pads on S/N, 20 on E/W).  A pad
"survives" into a half die if it sits fully clear of the cut-side corner::

    offset + 75 <= die_dim_along_edge - 26 - 355

Pads across / past the bare cut edge are dropped.  Two analog pads are added
(relocated, *not* coordinate-preserved) purely to keep ``NUM_ANALOG_PADS`` >=
1 so the RTL ``analog_PAD[NUM_ANALOG_PADS-1:0]`` port does not collapse to
``[-1:0]`` (cf. commit 8e74c56).  Every *signal* and *power* pad keeps its
exact slot_1x1 coordinate.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# --- slot_1x1 deterministic placement constants (see module docstring) -------
SN_START, SN_STEP = 488.5, 180.0   # South / North, W->E
EW_START, EW_STEP = 519.0, 211.0   # East / West, S->N
SEAL = 26.0
CORNER = 355.0
IO_W = 75.0

REPO = Path(__file__).resolve().parent.parent
SLOTS_DIR = REPO / "librelane" / "slots"
SLOT_1X1 = SLOTS_DIR / "slot_1x1.yaml"

ROW = {"S": "IO_SOUTH", "N": "IO_NORTH", "E": "IO_EAST", "W": "IO_WEST"}


def _norm(p: str) -> str:
    return str(p).replace("\\\\", "").replace("\\", "")


def _kind(name: str) -> str:
    if name == "clk_pad":
        return "clk"
    if name == "rst_n_pad":
        return "rst"
    for pre, k in (
        ("bidir", "bidir"),
        ("inputs", "input"),
        ("analog", "analog"),
        ("dvdd", "dvdd"),
        ("dvss", "dvss"),
    ):
        if name.startswith(pre):
            return k
    raise ValueError(f"unknown pad kind: {name}")


def _offset(edge: str, i: int) -> float:
    if edge in "SN":
        return round(SN_START + i * SN_STEP, 4)
    return round(EW_START + i * EW_STEP, 4)


@dataclass
class ExactConfig:
    name: str            # e.g. "0p5x1_3side_exact"
    define: str          # e.g. "SLOT_0P5X1_3SIDE_EXACT"
    die: list            # [0,0,w,h]
    core: list            # [x1,y1,x2,y2]
    cuts: str            # bare-cut edge(s): subset of S/N/E/W


CONFIGS = [
    # Half WIDTH, EAST is the bare cut edge.  Full height -> the WEST edge's
    # pads keep their exact slot_1x1 Y automatically; S/N west-portion pads
    # are pinned to their exact slot_1x1 X.
    ExactConfig(
        name="0p5x1_3side_exact",
        define="SLOT_0P5X1_3SIDE_EXACT",
        die=[0, 0, 1966, 5122],
        core=[442, 442, 1524, 4680],
        cuts="E",
    ),
    # Half HEIGHT, NORTH is the bare cut edge.  (The approximate
    # slot_1x0p5_3side cuts SOUTH and keeps NORTH, but slot_1x1's north pads
    # sit at y~5096 which cannot exist in a 2561-tall die -- exact
    # preservation REQUIRES keeping the SOUTH half and cutting NORTH.)
    ExactConfig(
        name="1x0p5_3side_exact",
        define="SLOT_1X0P5_3SIDE_EXACT",
        die=[0, 0, 3932, 2561],
        core=[442, 442, 3490, 2119],
        cuts="N",
    ),
    # QUARTER: half WIDTH and half HEIGHT -> a kept SW corner.  TWO bare cut
    # edges (NORTH and EAST), exactly like the half-width (cut E) and
    # half-height (cut N) cases superimposed.  Only the pads of the two
    # retained edges (SOUTH, WEST) whose slot_1x1 coordinate still fits the
    # 1966x2561 die survive, pinned to their EXACT slot_1x1 (x,y):
    #   SOUTH: x=488.5+i*180 must satisfy x+75 <= 1966-26-355  -> i=0..5
    #   WEST:  y=519.0+i*211 must satisfy y+75 <= 2561-26-355  -> i=0..7
    # (Same die origin (0,0) as slot_1x1, so the kept corner's absolute
    # coordinates are byte-identical to slot_1x1's.)
    ExactConfig(
        name="0p5x0p5_2side_exact",
        define="SLOT_0P5X0P5_2SIDE_EXACT",
        die=[0, 0, 1966, 2561],
        core=[442, 442, 1524, 2119],
        cuts="NE",
    ),
]


def load_1x1_phys_order() -> dict:
    """Return {edge: [logical_pad_name, ...]} in physical (placement) order.

    pad_cfg.tcl iterates the YAML list directly for S and E, and reversed
    for N and W (those two edges are listed reversed in the YAML so the file
    reads in a consistent rotational direction).
    """
    cfg = yaml.safe_load(SLOT_1X1.read_text())
    yl = {
        "S": [_norm(p) for p in cfg["PAD_SOUTH"]],
        "E": [_norm(p) for p in cfg["PAD_EAST"]],
        "N": [_norm(p) for p in cfg["PAD_NORTH"]],
        "W": [_norm(p) for p in cfg["PAD_WEST"]],
    }
    return {
        "S": yl["S"],
        "E": yl["E"],
        "N": list(reversed(yl["N"])),
        "W": list(reversed(yl["W"])),
    }


def build(cfg: ExactConfig, phys: dict):
    """Compute retained pads per edge with their exact slot_1x1 offsets.

    Returns (edges, analog_extra) where:
      edges[edge] = list of dicts {kind, off1x1, name_1x1, ordinal}
      analog_extra = list of dicts {edge, off} for the 2 relocated analog pads
    """
    die_w, die_h = cfg.die[2], cfg.die[3]
    edges = {"S": [], "N": [], "E": [], "W": []}
    for e in "SNEW":
        if e in cfg.cuts:
            continue
        dim = die_w if e in "SN" else die_h
        limit = dim - SEAL - CORNER
        for i, nm in enumerate(phys[e]):
            off = _offset(e, i)
            if off + IO_W <= limit + 1e-6:
                edges[e].append(
                    {"kind": _kind(nm), "off": off, "src": nm, "ord": i}
                )

    # Two relocated analog pads (kept only so NUM_ANALOG_PADS >= 1; their
    # coordinates are intentionally NOT slot_1x1-preserved -- slot_1x1's
    # analog pads sit on the discarded side of the cut).  Park them in the
    # gap between the last retained pad on an edge and that edge's cut-side
    # corner so they never perturb a coordinate-pinned pad.
    analog_extra = []
    for e in "SNEW":
        if len(analog_extra) == 2:
            break
        if e in cfg.cuts or not edges[e]:
            continue
        dim = die_w if e in "SN" else die_h
        limit = dim - SEAL - CORNER
        last = edges[e][-1]["off"] + IO_W
        gap = limit - last
        if gap >= IO_W + 1.0:
            analog_extra.append({"edge": e, "off": round(last + 1.0, 1)})
    if len(analog_extra) < 2:
        raise RuntimeError(
            f"{cfg.name}: could not park 2 analog pads (found "
            f"{len(analog_extra)} free gaps)"
        )
    return edges, analog_extra


def renumber(edges: dict, analog_extra: list):
    """Assign contiguous per-type indices and produce the final per-edge
    ordered placement lists (matching the RTL generate loops).

    Each placement is a dict:
      {inst, off, ord1x1, exact}
    where ``ord1x1`` is the pad's ordinal index along its edge in the FULL
    slot_1x1 padring (used by the PAD_CFG to replay the stock cur_pos
    arithmetic for byte-identical placement) and ``exact`` is True for
    coordinate-preserved pads / False for the 2 relocated analog pads."""
    ctr = {"bidir": 0, "input": 0, "analog": 0, "dvdd": 0, "dvss": 0}
    placements = {"S": [], "N": [], "E": [], "W": []}

    def inst_for(kind: str) -> str:
        if kind == "clk":
            return "clk_pad"
        if kind == "rst":
            return "rst_n_pad"
        idx = ctr[kind]
        ctr[kind] += 1
        return {
            "bidir": f"bidir\\\\[{idx}\\\\].pad",
            "input": f"inputs\\\\[{idx}\\\\].pad",
            "analog": f"analog\\\\[{idx}\\\\].pad",
            "dvdd": f"dvdd_pads\\\\[{idx}\\\\].pad",
            "dvss": f"dvss_pads\\\\[{idx}\\\\].pad",
        }[kind]

    # Place the (relocated) analog pads first so they take analog[0], analog[1].
    extra_by_edge = {}
    for ax in analog_extra:
        extra_by_edge.setdefault(ax["edge"], []).append(ax["off"])

    for e in "SNEW":
        merged = [
            (p["off"], p["kind"], p["ord"], True) for p in edges[e]
        ]
        for off in extra_by_edge.get(e, []):
            merged.append((off, "analog", None, False))
        merged.sort(key=lambda t: t[0])
        for off, kind, ord1x1, exact in merged:
            inst = inst_for(kind)
            placements[e].append(
                {
                    "inst": inst,
                    "off": off,
                    "ord1x1": ord1x1,
                    "exact": exact,
                }
            )

    counts = {k: ctr[k] for k in ctr}
    return placements, counts


def emit_yaml(cfg: ExactConfig, placements: dict) -> str:
    n_sides = 4 - len(cfg.cuts)
    lines = []
    a = lines.append
    a(f"# Exact-pad {n_sides}-side configuration -- AUTOGENERATED by")
    a("# scripts/generate_exact_3side_configs.py.  DO NOT EDIT BY HAND.")
    a("#")
    if len(cfg.cuts) == 1:
        a(f"# Half-size slot_1x1 with the {cfg.cuts} edge as a bare cut "
          f"edge.")
    else:
        a(f"# Quarter-size slot_1x1 with the {'+'.join(cfg.cuts)} edges as "
          f"bare cut edges (kept SW corner).")
    a("# Every signal/power pad is pinned (via a custom PAD_CFG) to the")
    a("# EXACT (x,y) it occupies in a real slot_1x1 build.  2 analog pads")
    a("# are relocated (not coordinate-preserved) only to keep the RTL")
    a("# analog_PAD port from collapsing to [-1:0].")
    a("FP_SIZING: absolute")
    a(f"DIE_AREA: {cfg.die}")
    a(f"CORE_AREA: {cfg.core}")
    a("")
    a(f'VERILOG_DEFINES: ["{cfg.define}"]')
    a("")
    a(f"# Partial padring ({n_sides}-sided): use the partial PDN script.")
    a("PDN_CFG: dir::pdn_partial.tcl")
    a("")
    a("# Custom pad config: explicit per-pad placement at exact slot_1x1")
    a("# coordinates (bypasses pad_cfg.tcl's even auto-distribution).")
    a(f"PAD_CFG: dir::slots/exact/{cfg.name}_pad_cfg.tcl")
    a("")
    for e, key in (("S", "PAD_SOUTH"), ("E", "PAD_EAST"),
                   ("N", "PAD_NORTH"), ("W", "PAD_WEST")):
        pl = placements[e]
        if not pl:
            a(f"{key}: []")
            a("")
            continue
        a(f"{key}: [")
        for i, p in enumerate(pl):
            inst = p["inst"]
            comma = "," if i < len(pl) - 1 else ""
            if inst in ("clk_pad", "rst_n_pad"):
                a(f"    {inst}{comma}")
            else:
                a(f'    "{inst}"{comma}')
        a("]")
        a("")
    return "\n".join(lines).rstrip() + "\n"


def emit_pad_cfg(cfg: ExactConfig, placements: dict) -> str:
    """Custom PAD_CFG.

    Exactness strategy: rather than guessing how OpenROAD's ``place_pad
    -location`` snaps to the IO-site grid, this script *replays the stock
    ``pad_cfg.tcl`` cur_pos arithmetic verbatim* -- but parameterised with
    slot_1x1's die dimension (3932 for S/N, 5122 for E/W) and slot_1x1's
    FULL per-edge pad count (17 for S/N, 20 for E/W).  For each retained pad
    we issue the *identical* ``place_pad -row .. -location <cur_pos>`` call
    (same numeric argument) that the real slot_1x1 build issued for the pad
    at that 1x1 ordinal, so OpenROAD's deterministic snapping yields the
    *byte-identical* origin.  Only the 2 relocated analog pads use an
    explicit ad-hoc ``-location`` (they are deliberately not preserved)."""
    # slot_1x1 ground-truth padring parameters (see slot_1x1.yaml).
    SN_DIE = 3932          # DIE_WIDTH used for South/North in slot_1x1
    EW_DIE = 5122          # DIE_HEIGHT used for East/West in slot_1x1
    SN_N = 17              # pads on each of slot_1x1's S and N edges
    EW_N = 20              # pads on each of slot_1x1's E and W edges
    edge_die = {"S": SN_DIE, "N": SN_DIE, "E": EW_DIE, "W": EW_DIE}
    edge_n = {"S": SN_N, "N": SN_N, "E": EW_N, "W": EW_N}

    L = []
    a = L.append
    a("# AUTOGENERATED by scripts/generate_exact_3side_configs.py -- "
      "DO NOT EDIT.")
    a("#")
    a(f"# Exact-pad PAD_CFG for slot_{cfg.name}.")
    a("#")
    a("# This replays LibreLane common/pad_cfg.tcl's cur_pos arithmetic")
    a("# using slot_1x1's die dimension + full per-edge pad count, then")
    a("# issues, for every retained pad, the identical place_pad -location")
    a("# call the real slot_1x1 build issued for that 1x1 ordinal -- giving")
    a("# byte-identical pad coordinates.  (S/N: 1x1 die=3932 n=17; E/W:")
    a("# 1x1 die=5122 n=20.  Constants from the PDK IO config:")
    a("# PAD_EDGE_SPACING=26, PAD_FAKE_CORNER_SITE=355, PAD_FAKE_SITE=0.1.)")
    a("")
    a("source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl")
    a("set_global_connections")
    a("")
    a(f'puts "\\[INFO\\] Generating EXACT-pad padring for {cfg.name}…"')
    a("")
    a("make_io_sites \\")
    a("    -horizontal_site $::env(PAD_SITE_NAME) \\")
    a("    -vertical_site $::env(PAD_SITE_NAME) \\")
    a("    -corner_site $::env(PAD_CORNER_SITE_NAME) \\")
    a("    -offset $::env(PAD_EDGE_SPACING)")
    a("")
    a("set block [ord::get_db_block]")
    a("")
    a("# ---- slot_1x1 cur_pos replay helper ---------------------------------")
    a("# Reproduces pad_cfg.tcl lines 73-131 for a slot_1x1 edge and returns")
    a("# the list of cur_pos values (one per 1x1 ordinal, all pads 75um).")
    a("proc lx_1x1_curpos {die_dim n_pads is_horizontal} {")
    a("    set es $::env(PAD_EDGE_SPACING)")
    a("    if {$is_horizontal} {")
    a("        set corner $::env(PAD_FAKE_CORNER_SITE_WIDTH)")
    a("    } else {")
    a("        set corner $::env(PAD_FAKE_CORNER_SITE_HEIGHT)")
    a("    }")
    a("    set site $::env(PAD_FAKE_SITE_WIDTH)")
    a("    set pad_w 75")
    a("    set side_width [expr {$die_dim - $es*2 - $corner*2}]")
    a("    set sum_w [expr {$pad_w * $n_pads}]")
    a("    set fill [expr {$side_width - $sum_w}]")
    a("    set sbp [expr {$fill / ($n_pads + 1)}]")
    a("    set sbp1 [expr {floor($sbp / $site) * $site}]")
    a("    set sspace [expr {($fill - $sbp1*($n_pads-1)) / 2.0}]")
    a("    set cur [expr {$sspace + $es + $corner}]")
    a("    set out {}")
    a("    for {set i 0} {$i < $n_pads} {incr i} {")
    a("        lappend out $cur")
    a("        set cur [expr {$cur + $sbp1 + $pad_w}]")
    a("    }")
    a("    return $out")
    a("}")
    a("")
    a("# Place pad #idx of $::env($side) (the SAME resolved instance list")
    a("# stock pad_cfg.tcl iterates -- avoids any name re-escaping) at the")
    a("# given along-edge location.")
    a("proc lx_place {block side row idx loc} {")
    a("    set inst [lindex $::env($side) $idx]")
    a('    if { [set i [$block findInst $inst]] == "NULL" } {')
    a('        puts stderr "\\[ERROR\\] exact PAD_CFG: $side\\[$idx\\] '
      '($inst) not found"')
    a("        exit 1")
    a("    }")
    a("    place_pad -row $row -location $loc \\")
    a("        -master [[$i getMaster] getName] $inst")
    a("}")
    a("")
    for e, key in (("S", "PAD_SOUTH"), ("E", "PAD_EAST"),
                   ("N", "PAD_NORTH"), ("W", "PAD_WEST")):
        pl = placements[e]
        if not pl:
            a(f"# {key}: bare cut edge -- no pads")
            a("")
            continue
        is_h = "1" if e in "SN" else "0"
        a(f"# ---- {ROW[e]} ({key}) ----")
        a(f"# {key} list order == placement order below (idx -> location).")
        a(f"set cp_{e} [lx_1x1_curpos {edge_die[e]} {edge_n[e]} {is_h}]")
        for idx, p in enumerate(pl):
            if p["exact"]:
                a(f'lx_place $block {key} {ROW[e]} {idx} '
                  f'[lindex $cp_{e} {p["ord1x1"]}]'
                  f'  ;# {p["inst"].replace(chr(92)*2, "")} '
                  f'@ 1x1 ordinal {p["ord1x1"]}')
            else:
                a(f'lx_place $block {key} {ROW[e]} {idx} {p["off"]:.4f}'
                  f'  ;# {p["inst"].replace(chr(92)*2, "")} '
                  f'(relocated analog, NOT 1x1-preserved)')
        a("")
    a('puts "\\[INFO\\] Placing corner cells…"')
    a("place_corners $::env(PAD_CORNER)")
    a("")
    a('puts "\\[INFO\\] Placing filler cells…"')
    for row in ("IO_NORTH", "IO_SOUTH", "IO_WEST", "IO_EAST"):
        a(f"place_io_fill -row {row} {{*}}$::env(PAD_FILLERS)")
    a("")
    a('puts "\\[INFO\\] Connecting ring signals…"')
    a("connect_by_abutment")
    a("")
    a("# Place io terminals (matches stock pad_cfg.tcl).")
    a("if { [info exists ::env(PAD_PLACE_IO_TERMINALS)] } {")
    a('    puts "\\[INFO\\] Placing I/O terminals…"')
    a("    foreach side {PAD_SOUTH PAD_EAST PAD_NORTH PAD_WEST} {")
    a("        if { ![info exists ::env($side)] } { continue }")
    a("        foreach inst_name $::env($side) {")
    a("            if { [set inst [$block findInst $inst_name]] == "
      '"NULL" } { continue }')
    a("            set master_name [[$inst getMaster] getName]")
    a("            foreach master_pin $::env(PAD_PLACE_IO_TERMINALS) {")
    a("                set parts [split $master_pin /]")
    a("                if {$master_name == [lindex $parts 0]} {")
    a("                    place_io_terminals "
      "$inst_name/[lindex $parts 1]")
    a("                    break")
    a("                }")
    a("            }")
    a("        }")
    a("    }")
    a("}")
    a("")
    a('puts "\\[INFO\\] Removing I/O rows…"')
    a("remove_io_rows")
    a("")
    return "\n".join(L)


def emit_defines_block(cfg: ExactConfig, counts: dict) -> str:
    n_dvdd = counts["dvdd"]
    n_dvss = counts["dvss"]
    n_in = counts["input"]
    n_bi = counts["bidir"]
    n_an = counts["analog"]
    if len(cfg.cuts) == 1:
        hdr = f"// Exact-pad half slot_1x1 ({cfg.cuts} edge = bare cut)."
    else:
        hdr = (f"// Exact-pad quarter slot_1x1 ({'+'.join(cfg.cuts)} edges "
               f"= bare cuts).")
    return "\n".join([
        f"`ifdef {cfg.define}",
        "",
        hdr,
        "// Pad counts == the slot_1x1 pads that survive on the kept side.",
        "// (analog pads are relocated, see slot config header).",
        "",
        "`ifdef NUM_DVDD_PADS_OVERRIDE",
        "  `define NUM_DVDD_PADS `NUM_DVDD_PADS_OVERRIDE",
        "`else",
        f"  `define NUM_DVDD_PADS {n_dvdd}",
        "`endif",
        "`ifdef NUM_DVSS_PADS_OVERRIDE",
        "  `define NUM_DVSS_PADS `NUM_DVSS_PADS_OVERRIDE",
        "`else",
        f"  `define NUM_DVSS_PADS {n_dvss}",
        "`endif",
        "",
        f"`define NUM_INPUT_PADS {n_in}",
        f"`define NUM_BIDIR_PADS {n_bi}",
        f"`define NUM_ANALOG_PADS {n_an}",
        "",
        "`endif",
        "",
    ])


def main() -> int:
    phys = load_1x1_phys_order()
    out_dir = SLOTS_DIR / "exact"
    out_dir.mkdir(parents=True, exist_ok=True)

    defines_blocks = []
    summary = []
    for cfg in CONFIGS:
        edges, analog_extra = build(cfg, phys)
        placements, counts = renumber(edges, analog_extra)

        yaml_path = SLOTS_DIR / f"slot_{cfg.name}.yaml"
        yaml_path.write_text(emit_yaml(cfg, placements))

        cfg_path = out_dir / f"{cfg.name}_pad_cfg.tcl"
        cfg_path.write_text(emit_pad_cfg(cfg, placements))

        defines_blocks.append(emit_defines_block(cfg, counts))

        total = sum(len(placements[e]) for e in "SNEW")
        exact_total = total - counts["analog"]
        summary.append(
            f"{cfg.name}: die={cfg.die} core={cfg.core} cut={cfg.cuts} "
            f"pads={total} (exact-preserved={exact_total}, "
            f"relocated_analog={counts['analog']}) "
            f"counts={counts}"
        )
        print(f"wrote {yaml_path.relative_to(REPO)}")
        print(f"wrote {cfg_path.relative_to(REPO)}")

    block_path = out_dir / "slot_defines_exact.svh.inc"
    block_path.write_text(
        "// AUTOGENERATED by scripts/generate_exact_3side_configs.py\n"
        "// Paste/keep these blocks in src/slot_defines.svh\n\n"
        + "\n".join(defines_blocks)
    )
    print(f"wrote {block_path.relative_to(REPO)}")
    print()
    for s in summary:
        print(s)
    return 0


if __name__ == "__main__":
    sys.exit(main())
