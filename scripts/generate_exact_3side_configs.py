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

Pads across / past the bare cut edge are dropped, and so is any pad whose
slot_1x1 coordinate does not fit on the smaller die -- nothing is ever
relocated to a non-slot_1x1 coordinate, so *every* emitted pad keeps its exact
slot_1x1 (x, y).  slot_1x1's two analog pads sit on the NORTH far corner,
which no half/quarter cut retains, so exact slots simply have no analog pads;
the core-unused ``analog_PAD`` port is dropped via ``NO_ANALOG_PADS`` so its
width never collapses to ``[-1:0]`` (cf. commit 8e74c56).
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
        # East margin shrunk from 442 -> 166: NE+SE corners are destroyed
        # in pad_cfg.tcl, so the 355um corner clearance is no longer needed
        # on the bare east edge. 166um still leaves room for the power ring
        # (57um) + buffer (~8um) + the IO_EAST row strip (75+26um) which
        # make_io_sites reserves at x=[1865,1940].
        core=[442, 442, 1800, 4680],
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
        # North margin shrunk from 442 -> 161: same rationale as 0p5x1_3side
        # for the east case (NW+NE corners destroyed; clearance to IO_NORTH
        # strip at y=[2460,2535]).
        core=[442, 442, 3490, 2400],
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
        # Both bare-edge margins shrunk: east 442 -> 166 (NE+SE corners
        # destroyed) and north 442 -> 161 (NW+NE corners destroyed). Only
        # the SW corner survives, so only the SW edges retain the 442um
        # corner clearance.
        core=[442, 442, 1800, 2400],
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

    Returns edges[edge] = list of {kind, off, src, ord} for every slot_1x1
    pad whose exact coordinate still fits on the smaller die.  Pads whose
    slot_1x1 coordinate falls in the cut-away region are dropped; nothing is
    relocated, so every emitted pad is coordinate-exact.  (slot_1x1's analog
    pads sit on the NORTH far corner that no cut retains -> no analog pads.)

    Per-end limit relaxation
    ------------------------
    Each kept edge has two endpoints (low/high in along-axis coords). The
    pad-clearance limit at each end depends on whether the corner cell at
    that end is destroyed:

      - Kept corner: pad must clear ``SEAL + CORNER`` (~381um) -- the IO
        corner cell physically occupies that strip.
      - Destroyed corner: pad need only clear ``SEAL`` (~26um) -- the
        corner cell has been destroyed and the IO row extends straight
        to ``die_dim - SEAL`` via ``IO_<side>_EXT_*`` rows (see PAD_CFG).

    A corner is destroyed iff its OTHER adjacent edge is bare (in
    ``cfg.cuts``). With this relaxation the kept edges admit ~2 additional
    slot_1x1 pads each (the ones that previously fell inside the
    now-deleted corner clearance band) -- see image #6 review.
    """
    die_w, die_h = cfg.die[2], cfg.die[3]
    edges = {"S": [], "N": [], "E": [], "W": []}
    # For each edge, the perpendicular edges at its low / high endpoints.
    # S/N edges run along X (low=west end, high=east end).
    # W/E edges run along Y (low=south end, high=north end).
    perp = {
        "S": ("W", "E"),
        "N": ("W", "E"),
        "W": ("S", "N"),
        "E": ("S", "N"),
    }
    for e in "SNEW":
        if e in cfg.cuts:
            continue
        dim = die_w if e in "SN" else die_h
        perp_lo, perp_hi = perp[e]
        # Corner at the low end is destroyed iff the perpendicular edge there
        # is bare (e.g. S-edge SW corner is destroyed iff W is in cuts).
        lo_destroyed = perp_lo in cfg.cuts
        hi_destroyed = perp_hi in cfg.cuts
        lo_limit = SEAL if lo_destroyed else (SEAL + CORNER)
        hi_limit = (dim - SEAL) if hi_destroyed else (dim - SEAL - CORNER)
        for i, nm in enumerate(phys[e]):
            off = _offset(e, i)
            if lo_limit - 1e-6 <= off and off + IO_W <= hi_limit + 1e-6:
                edges[e].append(
                    {"kind": _kind(nm), "off": off, "src": nm, "ord": i}
                )

    return edges


def renumber(edges: dict):
    """Assign contiguous per-type indices and produce the final per-edge
    ordered placement lists (matching the RTL generate loops).

    Each placement is {inst, ord1x1}, where ``ord1x1`` is the pad's ordinal
    index along its edge in the FULL slot_1x1 padring (used by the PAD_CFG to
    replay the stock cur_pos arithmetic for byte-identical placement).  Every
    placed pad is coordinate-exact -- there are no relocated pads."""
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

    for e in "SNEW":
        for p in sorted(edges[e], key=lambda d: d["off"]):
            placements[e].append(
                {"inst": inst_for(p["kind"]), "ord1x1": p["ord"]}
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
    a("# Every pad is pinned (via a custom PAD_CFG) to the EXACT (x,y) it")
    a("# occupies in a real slot_1x1 build.  slot_1x1's analog pads sit on")
    a("# the cut-away corner, so this slot has NO analog pads (the core-")
    a("# unused analog_PAD port is dropped via NO_ANALOG_PADS).")
    a("FP_SIZING: absolute")
    a(f"DIE_AREA: {cfg.die}")
    a(f"CORE_AREA: {cfg.core}")
    a("")
    a(f'VERILOG_DEFINES: ["{cfg.define}"]')
    a("")
    a(f"# Partial padring ({n_sides}-sided): use the partial PDN script.")
    a("# The exact-pad variant wraps pdn_partial.tcl with a pre-PDN destroy")
    a("# of wafer_space_logo (whose Metal5 OBS at the NE corner otherwise")
    a("# collides with the bare-edge IO row extension fillers).")
    a("PDN_CFG: dir::pdn_partial_exact.tcl")
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
    # Compute which IO rows need to be EXTENDED into the destroyed-corner
    # area so that lx_place's `place_pad -row IO_<side>` (which enforces
    # row containment, see [PAD-0119]) accepts the new edge-most pads
    # admitted by the asymmetric per-end clearance limits in build().
    # An edge needs extension iff at least one of its endpoint corners
    # will be destroyed (its perpendicular edge is bare).
    perp_map = {"S": ("W", "E"), "N": ("W", "E"),
                "W": ("S", "N"), "E": ("S", "N")}
    row_extensions = []  # list of (row_name, new_lo_um, new_hi_um)
    for e in "SNEW":
        if e in cfg.cuts:
            continue  # bare edge: no IO row, nothing to extend
        perp_lo, perp_hi = perp_map[e]
        lo_destroyed = perp_lo in cfg.cuts
        hi_destroyed = perp_hi in cfg.cuts
        if not lo_destroyed and not hi_destroyed:
            continue  # both corners kept: original row geometry is fine
        dim = cfg.die[2] if e in "SN" else cfg.die[3]
        new_lo = SEAL if lo_destroyed else (SEAL + CORNER)
        new_hi = (dim - SEAL) if hi_destroyed else (dim - SEAL - CORNER)
        row_extensions.append((ROW[e], new_lo, new_hi))
    if row_extensions:
        a("# ---- Extend IO rows into destroyed-corner area ----------------------")
        a("# Each kept edge that has a destroyed adjacent corner needs its IO row")
        a("# to physically span up to (dim - SEAL) at that end, so that pads near")
        a("# the corner pass place_pad's row-containment check (PAD-0119). We do")
        a("# this BEFORE lx_place: destroy the make_io_sites-created row and")
        a("# recreate it (same name, same site / orient / direction / Y-or-X")
        a("# perpendicular coord) with the extended origin + num_sites. The")
        a("# bare-edge corner cells are still placed by place_corners (below)")
        a("# and immediately destroyed; place_io_fill then packs fillers across")
        a("# the freed corner area inside the now-larger row.")
        a("set _row_extensions [list \\")
        for name, lo_um, hi_um in row_extensions:
            a(f"    [list {name} {lo_um} {hi_um}] \\")
        a("]")
        a("foreach _ext_data $_row_extensions {")
        a("    lassign $_ext_data _name _new_lo_um _new_hi_um")
        a("    set _orig_row \"NULL\"")
        a("    foreach _r [$block getRows] {")
        a("        if {[$_r getName] eq $_name} { set _orig_row $_r; break }")
        a("    }")
        a('    if {$_orig_row eq "NULL"} {')
        a('        puts stderr "\\[ERROR\\] exact PAD_CFG: row $_name not found"')
        a("        exit 1")
        a("    }")
        a("    set _site [$_orig_row getSite]")
        a("    set _orient [$_orig_row getOrient]")
        a("    set _dir [$_orig_row getDirection]")
        a("    set _bb [$_orig_row getBBox]")
        a("    set _spacing [$_orig_row getSpacing]")
        a("    set _units [$block getDefUnits]")
        a("    set _new_lo_dbu [expr {round($_new_lo_um * $_units)}]")
        a("    set _new_hi_dbu [expr {round($_new_hi_um * $_units)}]")
        a('    if {$_dir eq "HORIZONTAL"} {')
        a("        set _perp_dbu [$_bb yMin]")
        a("        set _new_origin_x $_new_lo_dbu")
        a("        set _new_origin_y $_perp_dbu")
        a("    } else {")
        a("        set _perp_dbu [$_bb xMin]")
        a("        set _new_origin_x $_perp_dbu")
        a("        set _new_origin_y $_new_lo_dbu")
        a("    }")
        a("    set _new_num_sites [expr {($_new_hi_dbu - $_new_lo_dbu) "
          "/ $_spacing}]")
        a("    odb::dbRow_destroy $_orig_row")
        a("    odb::dbRow_create $block $_name $_site $_new_origin_x "
          "$_new_origin_y \\")
        a("        $_orient $_dir $_new_num_sites $_spacing")
        a('    puts "\\[INFO\\] Extended $_name to span ${_new_lo_um}-${_new_hi_um}um '
          '(origin=($_new_origin_x,$_new_origin_y), $_new_num_sites sites, '
          'dir=$_dir orient=$_orient)"')
        a("}")
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
            a(f'lx_place $block {key} {ROW[e]} {idx} '
              f'[lindex $cp_{e} {p["ord1x1"]}]'
              f'  ;# {p["inst"].replace(chr(92)*2, "")} '
              f'@ 1x1 ordinal {p["ord1x1"]}')
        a("")
    a('puts "\\[INFO\\] Placing corner cells…"')
    a("place_corners $::env(PAD_CORNER)")
    a("")
    # NOTE: the `wafer_space_logo` cleanup that prevents the 357 Magic
    # Illegal Overlap errors lives in librelane/pdn_partial_exact.tcl, not
    # here. LibreLane runs PadRing (this step) BEFORE ManualMacroPlacement;
    # destroying the logo from inside pad_cfg.tcl deletes the instance
    # before MMP can place it, and the manual_macro_placement placer
    # exits(1) with "Declared macros not instantiated in design:
    # wafer_space_logo". GeneratePDN -- which sources pdn_partial_exact.tcl
    # for the exact-pad slots -- runs AFTER MMP, so the destroy lands in
    # the right phase. Exact configs therefore set
    # PDN_CFG: dir::pdn_partial_exact.tcl (see emit_yaml).
    # Drop corner cells + skip filler-row creation on the bare cut edge(s).
    # OpenROAD's `place_corners` always places one corner per die corner; for
    # cut edges there is no IO row to abut to on the bare side, so the
    # resulting corner cell + filler row is isolated silicon waste. After
    # `place_corners`, locate each corner cell by its bbox centre relative to
    # the die centre and destroy the ones that sit on a bare edge. Then skip
    # `place_io_fill` for the bare edge's row, leaving that side clean.
    bare_letters = list(cfg.cuts)  # e.g. "NE" -> ["N", "E"]
    bare_words = [
        {"N": "north", "S": "south", "E": "east", "W": "west"}[ltr]
        for ltr in bare_letters
    ]
    bare_tcl = " ".join(f'"{w}"' for w in bare_words)
    a("# Drop the bare-edge corner cell(s): no IO row abuts them, they would")
    a("# just be isolated structures on the bare cut edge.")
    a(f"set _bare_edges [list {bare_tcl}]")
    a("set _xmid [expr {([lindex $::env(DIE_AREA) 0] + "
      "[lindex $::env(DIE_AREA) 2]) / 2.0}]")
    a("set _ymid [expr {([lindex $::env(DIE_AREA) 1] + "
      "[lindex $::env(DIE_AREA) 3]) / 2.0}]")
    a("set _units [$block getDefUnits]")
    a("# Identify bare-edge corner cells AND remember their bbox + side BEFORE")
    a("# destroying them -- the bbox is the freed silicon strip we will later")
    a("# fill with IO row fillers so the row visually extends to the die edge.")
    a("set _bare_corner_data [list]")
    a("foreach _inst [$block getInsts] {")
    a("    if { [[$_inst getMaster] getName] ne $::env(PAD_CORNER) } "
      "{ continue }")
    a("    set _bb [$_inst getBBox]")
    a("    set _cx [expr {([$_bb xMin] + [$_bb xMax]) / 2.0 / $_units}]")
    a("    set _cy [expr {([$_bb yMin] + [$_bb yMax]) / 2.0 / $_units}]")
    a("    set _is_north [expr {$_cy > $_ymid}]")
    a("    set _is_east  [expr {$_cx > $_xmid}]")
    a("    set _drop 0")
    a("    foreach _edge $_bare_edges {")
    a("        switch -- $_edge {")
    a("            east  { if { $_is_east }      { set _drop 1 } }")
    a("            west  { if { ! $_is_east }    { set _drop 1 } }")
    a("            north { if { $_is_north }     { set _drop 1 } }")
    a("            south { if { ! $_is_north }   { set _drop 1 } }")
    a("        }")
    a("        if { $_drop } { break }")
    a("    }")
    a("    if { $_drop } {")
    a("        lappend _bare_corner_data [list [$_bb xMin] [$_bb yMin] \\")
    a("            [$_bb xMax] [$_bb yMax] $_is_north $_inst]")
    a("    }")
    a("}")
    a("set _destroyed 0")
    a("foreach _data $_bare_corner_data {")
    a("    odb::dbInst_destroy [lindex $_data 5]")
    a("    incr _destroyed")
    a("}")
    a('puts "\\[INFO\\] Bare-edge corner cleanup (bare: $_bare_edges): '
      'destroyed $_destroyed corner cell(s)."')
    a("")
    a("# (Rows on the destroyed-corner side were already EXTENDED in place")
    a("# before lx_place, so place_io_fill on the main row name automatically")
    a("# fills the freed corner area too -- no separate IO_<side>_EXT_* rows.)")
    a("")
    a('puts "\\[INFO\\] Placing filler cells…"')
    a("# Skip `place_io_fill` on bare-edge rows: no pads + no corners on")
    a("# that row means filler cells would be the only content, which is")
    a("# pure waste on a cut edge.")
    a("foreach _row {IO_NORTH IO_SOUTH IO_WEST IO_EAST} {")
    a("    set _edge_lc [string tolower [string range $_row 3 end]]")
    a("    if { [lsearch -exact $_bare_edges $_edge_lc] >= 0 } {")
    a('        puts "\\[INFO\\] Skipping place_io_fill on $_row (bare cut edge)"')
    a("        continue")
    a("    }")
    a("    place_io_fill -row $_row {*}$::env(PAD_FILLERS)")
    a("}")
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
        "// slot_1x1's analog pads sit in the cut-away corner and cannot be",
        "// coordinate-preserved, so this slot has no analog pads; "
        "NO_ANALOG_PADS",
        "// drops the (core-unused) analog port so its width never goes -1:0.",
        "",
        "`define NO_ANALOG_PADS",
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
        edges = build(cfg, phys)
        placements, counts = renumber(edges)

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
