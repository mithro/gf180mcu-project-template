# Copyright 2025 LibreLane Contributors
#
# PDN configuration for TRUE 3-sided (U-shaped) core rings.
#
# Opt-in is via the standard, schema-validated PDN_CFG key:
#     PDN_CFG: dir::pdn_uring.tcl
# (An earlier attempt used a custom PDN_BARE_EDGES config key; LibreLane v3
# strictly validates config keys and rejects unknown ones, so that approach
# failed at config load. Selecting this script is the LibreLane-sanctioned
# opt-in and leaves existing partial-padring configs — which keep
# pdn_partial.tcl — completely untouched, so they are not regressed.)
#
# Mechanism:
#   1. Source the unmodified pdn_partial.tcl, which builds the normal CLOSED
#      4-sided ring and wires the IO pads via -connect_to_pads. This is the
#      proven-passing partial-padring power topology (PSM-0069 satisfied by
#      the pad-connected ring + internal Metal2/Metal3 mesh + std-cell rails).
#   2. After pdngen has built the network and wired the pads, delete the ring
#      metal/vias sitting in the bare-edge margin. A bare edge has NO IO pads,
#      so no PadDirectConnectionStrap targets its ring bar — removing it loses
#      no power source. The remaining 3 ring sides still collect all pad
#      current and the internal mesh still feeds every cell, so PSM-0069
#      connectivity is preserved while the result is a true U-shaped ring.
#
# Bare edges are AUTO-DETECTED from the per-edge pad lists: an edge whose
# PAD_<side> list is empty has no IO pads and is therefore bare. PAD_NORTH/
# PAD_SOUTH/PAD_EAST/PAD_WEST are standard LibreLane variables exposed to
# OpenROAD tcl as $::env(PAD_<SIDE>) (the same vars the padring/pad_cfg
# scripts consume), so no custom config key is needed.
#
# Licensed under the Apache License, Version 2.0

# 1. Build the normal closed ring + pad connections (unmodified base script).
source [file join [file dirname [file normalize [info script]]] pdn_partial.tcl]

# 2. Remove the bare-edge ring metal after pdngen.
#
# bare_edges: subset of {north south east west} naming edge(s) with no pads.
proc pdn_remove_bare_edge_ring { bare_edges } {
    set block [ord::get_db_block]
    if { $block == "NULL" } {
        return
    }

    # Core-area boundary. The ring is built just OUTSIDE this rectangle
    # (PDK PDN_CORE_RING_*OFFSET = 6um), so any ring/via metal on the bare
    # side of the matching core edge is the bare-edge ring metal.
    set core [$block getCoreArea]
    set core_xlo [$core xMin]
    set core_ylo [$core yMin]
    set core_xhi [$core xMax]
    set core_yhi [$core yMax]

    # Power + ground nets carry the ring.
    set nets [list]
    foreach n [concat $::env(VDD_NETS) $::env(GND_NETS)] {
        set db_net [$block findNet $n]
        if { $db_net != "NULL" } {
            lappend nets $db_net
        }
    }

    set removed 0
    set clipped 0
    set vias_removed 0
    foreach db_net $nets {
        foreach swire [$db_net getSWires] {
            # Snapshot: we mutate the set while iterating.
            set boxes [list]
            foreach sbox [$swire getWires] {
                lappend boxes $sbox
            }
            foreach sbox $boxes {
                set bxlo [$sbox xMin]
                set bylo [$sbox yMin]
                set bxhi [$sbox xMax]
                set byhi [$sbox yMax]
                set is_via [$sbox isVia]
                set is_ring [expr {!$is_via && [$sbox getWireShapeType] eq "RING"}]

                # Vias are only ever destroyed, never clipped.
                if { !$is_via && !$is_ring } {
                    continue
                }

                set delete 0
                set new_coords ""
                foreach edge $bare_edges {
                    switch -- $edge {
                        east {
                            if { $bxhi > $core_xhi } {
                                if { $is_via || $bxlo >= $core_xhi } {
                                    set delete 1
                                } else {
                                    set new_coords [list $bxlo $bylo $core_xhi $byhi]
                                }
                            }
                        }
                        west {
                            if { $bxlo < $core_xlo } {
                                if { $is_via || $bxhi <= $core_xlo } {
                                    set delete 1
                                } else {
                                    set new_coords [list $core_xlo $bylo $bxhi $byhi]
                                }
                            }
                        }
                        north {
                            if { $byhi > $core_yhi } {
                                if { $is_via || $bylo >= $core_yhi } {
                                    set delete 1
                                } else {
                                    set new_coords [list $bxlo $bylo $bxhi $core_yhi]
                                }
                            }
                        }
                        south {
                            if { $bylo < $core_ylo } {
                                if { $is_via || $byhi <= $core_ylo } {
                                    set delete 1
                                } else {
                                    set new_coords [list $bxlo $core_ylo $bxhi $byhi]
                                }
                            }
                        }
                    }
                    if { $delete } {
                        break
                    }
                }

                if { $delete } {
                    odb::dbSBox_destroy $sbox
                    if { $is_via } {
                        incr vias_removed
                    } else {
                        incr removed
                    }
                } elseif { $new_coords ne "" } {
                    # Shorten a perpendicular ring bar so it stops at the core
                    # boundary instead of overhanging into the bare margin.
                    lassign $new_coords nx1 ny1 nx2 ny2
                    if { $nx2 > $nx1 && $ny2 > $ny1 } {
                        set layer [$sbox getTechLayer]
                        odb::dbSBox_destroy $sbox
                        odb::dbSBox_create $swire $layer \
                            $nx1 $ny1 $nx2 $ny2 "RING"
                        incr clipped
                    }
                }
            }
        }
    }

    utl::info PDN 9001 \
        "Partial ring on bare edge(s) \"$bare_edges\": removed $removed ring\
         bar(s), clipped $clipped overhang(s), removed $vias_removed via(s)\
         (no IO pads behind bare edge; redundant ring metal)."
}

# Auto-detect bare edges from the PLACED IO pad instances in odb.
#
# The PAD_<side> config lists are NOT exposed as $::env at the GeneratePDN
# step (they exist at the PadRing step, which is why pad_cfg.tcl can read
# them, but not here) — relying on them made every edge look empty and
# deleted the entire ring. Instead, classify each placed pad-type instance
# by which die-edge margin band its centre falls in: an edge with zero pad
# instances has no padring and is therefore bare.
#
# Bands are defined relative to the core rectangle (pads sit between the die
# boundary and the core). Corner cells fall OUTSIDE the core on both axes
# and so match no single edge band — they are naturally excluded.
proc pdn_detect_bare_edges {} {
    set block [ord::get_db_block]
    if { $block == "NULL" } {
        return [list]
    }
    set core [$block getCoreArea]
    set cxlo [$core xMin]
    set cylo [$core yMin]
    set cxhi [$core xMax]
    set cyhi [$core yMax]

    array set count {north 0 south 0 east 0 west 0}
    foreach inst [$block getInsts] {
        set master [$inst getMaster]
        set type [$master getType]
        # PAD, PAD_INPUT/OUTPUT/INOUT/POWER/SPACER/AREAIO all start "PAD".
        if { ![string match -nocase "PAD*" $type] } {
            continue
        }
        set bb [$inst getBBox]
        set ix [expr {([$bb xMin] + [$bb xMax]) / 2}]
        set iy [expr {([$bb yMin] + [$bb yMax]) / 2}]

        if { $iy < $cylo && $ix >= $cxlo && $ix <= $cxhi } {
            incr count(south)
        } elseif { $iy > $cyhi && $ix >= $cxlo && $ix <= $cxhi } {
            incr count(north)
        } elseif { $ix < $cxlo && $iy >= $cylo && $iy <= $cyhi } {
            incr count(west)
        } elseif { $ix > $cxhi && $iy >= $cylo && $iy <= $cyhi } {
            incr count(east)
        }
    }

    set bare [list]
    foreach edge {north south east west} {
        if { $count($edge) == 0 } {
            lappend bare $edge
        }
    }
    utl::info PDN 9003 \
        "pdn_uring.tcl pad census N=$count(north) S=$count(south)\
         E=$count(east) W=$count(west) -> bare edge(s): \"$bare\"."
    return $bare
}

# Wrap pdngen so the bare-edge ring metal is removed after the network has
# been built and the pads wired. Only post-process a real build (skip
# -reset/-ripup/-report_only/-check_only invocations).
rename pdngen pdn_real_pdngen
proc pdngen { args } {
    set rc [uplevel 1 [list pdn_real_pdngen {*}$args]]
    set is_build 1
    foreach a $args {
        if { $a in {-reset -ripup -report_only -check_only} } {
            set is_build 0
        }
    }
    if { $is_build } {
        set bare [pdn_detect_bare_edges]
        set n [llength $bare]
        # Safety: a valid chip always has pads on >= 3 edges, so at most 2
        # edges can legitimately be bare (3-side -> 1, quarter -> 2). If
        # detection reports >= 3 bare edges it is a detection failure;
        # removing that much ring would destroy power connectivity
        # (PSM-0069). Fall back to the proven closed ring instead.
        if { $n == 0 } {
            utl::info PDN 9002 \
                "pdn_uring.tcl: no bare edge detected; keeping closed\
                 4-sided ring (nothing to do)."
        } elseif { $n >= 3 } {
            utl::warn PDN 9004 \
                "pdn_uring.tcl: $n bare edges detected (\"$bare\") — implausible\
                 (a chip needs pads on >= 3 edges). Treating as a detection\
                 failure and KEEPING the closed 4-sided ring to preserve\
                 power connectivity."
        } else {
            pdn_remove_bare_edge_ring $bare
        }
    }
    return $rc
}
