# Copyright 2025 LibreLane Contributors
#
# PDN configuration for partial padring designs
# (IO pads on fewer than 4 edges)
#
# For partial padrings, power enters through IO cells on edges with pads.
# The core ring is built CLOSED (4-sided) by add_pdn_ring and connected to
# the IO pad power pins via -connect_to_pads. This is electrically identical
# to the proven-passing partial-padring configuration.
#
# OpenROAD's pdngen has NO native support for a partial/3-sided ring:
#   - src/pdn/src/rings.cpp Rings::makeShapes() unconditionally emits four
#     rectangular RING shapes per net (bottom/top/left/right). There is no
#     per-edge suppression option; core_offsets/pad_offsets only translate it.
#   - src/pdn/src/PdnGen.cc makeRing() calls CoreGrid::setupDirectConnect()
#     then forces setTargetType(RING) on every pad strap, so pad power can
#     ONLY be collected through RING-type shapes. Dropping add_pdn_ring would
#     therefore break -connect_to_pads and the power source for PSM-0069.
#   - -connect_to_pads does NOT delete "floating" ring segments; that
#     behaviour does not exist in pdngen (the old comment here was wrong).
#
# To obtain a true U-shaped (3-sided) ring while keeping the proven
# pad-connect / PSM behaviour, we keep the closed ring during pdngen, then
# (gated by PDN_BARE_EDGES) delete the ring metal that lies in the bare-edge
# margin AFTER pdngen has written it and wired the pads. The bare edge has no
# IO pads, so its ring bar carries no pad connections; removing it leaves a
# U-ring that still collects all pad current on the IO edges, and the internal
# Metal2/Metal3 stripe mesh + std-cell rails still deliver power everywhere
# (PSM-0069 connectivity is satisfied by the mesh, not the bare-edge bar).
#
# PDN_BARE_EDGES: space-separated subset of {north south east west} naming the
# edge(s) with no IO pads. Unset/empty => behave exactly like before (closed
# 4-sided ring), so existing partial-padring configs are NOT regressed.
#
# Adapted from pdn_cfg.tcl
#
# Licensed under the Apache License, Version 2.0

source $::env(SCRIPTS_DIR)/openroad/common/io.tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
foreach vdd $::env(VDD_NETS) gnd $::env(GND_NETS) {
    if { $vdd != $::env(VDD_NET)} {
        lappend secondary $vdd

        set db_net [[ord::get_db_block] findNet $vdd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }

    if { $gnd != $::env(GND_NET)} {
        lappend secondary $gnd

        set db_net [[ord::get_db_block] findNet $gnd]
        if {$db_net == "NULL"} {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary


if { $::env(PDN_MULTILAYER) == 1 } {

    set arg_list [list]
    if { $::env(PDN_ENABLE_PINS) } {
        lappend arg_list -pins "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
    }

    define_pdn_grid \
        -name stdcell_grid \
        -starts_with POWER \
        -voltage_domain CORE \
        {*}$arg_list

    set arg_list [list]
    append_if_equals arg_list PDN_EXTEND_TO "core_ring" -extend_to_core_ring
    append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary

    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_VERTICAL_LAYER) \
        -width $::env(PDN_VWIDTH) \
        -pitch $::env(PDN_VPITCH) \
        -offset $::env(PDN_VOFFSET) \
        -spacing $::env(PDN_VSPACING) \
        -starts_with POWER \
        {*}$arg_list

    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_HORIZONTAL_LAYER) \
        -width $::env(PDN_HWIDTH) \
        -pitch $::env(PDN_HPITCH) \
        -offset $::env(PDN_HOFFSET) \
        -spacing $::env(PDN_HSPACING) \
        -starts_with POWER \
        {*}$arg_list

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
} else {

    set arg_list [list]
    if { $::env(PDN_ENABLE_PINS) } {
        lappend arg_list -pins "$::env(PDN_VERTICAL_LAYER)"
    }

    define_pdn_grid \
        -name stdcell_grid \
        -starts_with POWER \
        -voltage_domain CORE \
        {*}$arg_list

    set arg_list [list]
    append_if_equals arg_list PDN_EXTEND_TO "core_ring" -extend_to_core_ring
    append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary

    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_VERTICAL_LAYER) \
        -width $::env(PDN_VWIDTH) \
        -pitch $::env(PDN_VPITCH) \
        -offset $::env(PDN_VOFFSET) \
        -spacing $::env(PDN_VSPACING) \
        -starts_with POWER \
        {*}$arg_list
}

# Adds the standard cell rails if enabled.
if { $::env(PDN_ENABLE_RAILS) == 1 } {
    add_pdn_stripe \
        -grid stdcell_grid \
        -layer $::env(PDN_RAIL_LAYER) \
        -width $::env(PDN_RAIL_WIDTH) \
        -followpins

    add_pdn_connect \
        -grid stdcell_grid \
        -layers "$::env(PDN_RAIL_LAYER) $::env(PDN_VERTICAL_LAYER)"
}


# Adds the core ring if enabled.
# The ring is always built CLOSED here so add_pdn_ring -connect_to_pads can
# collect pad power through RING shapes (see file header). The bare-edge bar
# is removed later by pdn_remove_bare_edge_ring (gated by PDN_BARE_EDGES).
if { $::env(PDN_CORE_RING) == 1 } {
    if { $::env(PDN_MULTILAYER) == 1 } {
        set arg_list [list]
        append_if_flag arg_list PDN_CORE_RING_ALLOW_OUT_OF_DIE -allow_out_of_die
        append_if_flag arg_list PDN_CORE_RING_CONNECT_TO_PADS -connect_to_pads
        append_if_equals arg_list PDN_EXTEND_TO "boundary" -extend_to_boundary

        set pdn_core_vertical_layer $::env(PDN_VERTICAL_LAYER)
        set pdn_core_horizontal_layer $::env(PDN_HORIZONTAL_LAYER)

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] } {
            set pdn_core_vertical_layer $::env(PDN_CORE_VERTICAL_LAYER)
        }

        if { [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            set pdn_core_horizontal_layer $::env(PDN_CORE_HORIZONTAL_LAYER)
        }

        add_pdn_ring \
            -grid stdcell_grid \
            -layers "$pdn_core_vertical_layer $pdn_core_horizontal_layer" \
            -widths "$::env(PDN_CORE_RING_VWIDTH) $::env(PDN_CORE_RING_HWIDTH)" \
            -spacings "$::env(PDN_CORE_RING_VSPACING) $::env(PDN_CORE_RING_HSPACING)" \
            -core_offset "$::env(PDN_CORE_RING_VOFFSET) $::env(PDN_CORE_RING_HOFFSET)" \
            {*}$arg_list

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"
        }

        if { [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_HORIZONTAL_LAYER) $::env(PDN_VERTICAL_LAYER)"
        }

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] && [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            add_pdn_connect \
                -grid stdcell_grid \
                -layers "$::env(PDN_CORE_VERTICAL_LAYER) $::env(PDN_CORE_HORIZONTAL_LAYER)"
        }

        # Power delivery for partial padrings relies on:
        # 1. The closed core ring + -connect_to_pads collecting pad power
        #    through RING shapes on every edge that has IO pads.
        # 2. The internal Metal2/Metal3 stripe mesh distributing power across
        #    the whole core (independent of the ring).
        # 3. Standard-cell Metal1 rails tapping the stripe mesh.
        # The bare-edge ring bar (no pads behind it) is redundant metal and is
        # deleted post-pdngen by pdn_remove_bare_edge_ring when PDN_BARE_EDGES
        # is set, yielding a true U-shaped ring without losing any power source.

    } else {
        throw APPLICATION "PDN_CORE_RING cannot be used when PDN_MULTILAYER is set to false."
    }
}

define_pdn_grid \
    -macro \
    -default \
    -name macro \
    -starts_with POWER \
    -halo "$::env(PDN_HORIZONTAL_HALO) $::env(PDN_VERTICAL_HALO)"

add_pdn_connect \
    -grid macro \
    -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"

# SRAM macro

define_pdn_grid \
    -macro \
    -instances i_chip_core.sram \
    -name sram_macro \
    -starts_with POWER \
    -halo "$::env(PDN_HORIZONTAL_HALO) $::env(PDN_VERTICAL_HALO)"

add_pdn_connect \
    -grid sram_macro \
    -layers "$::env(PDN_VERTICAL_LAYER) $::env(PDN_HORIZONTAL_LAYER)"

add_pdn_connect \
    -grid sram_macro \
    -layers "$::env(PDN_VERTICAL_LAYER) Metal3"

# Add stripes on W/E edges of SRAM
add_pdn_stripe \
    -grid sram_macro \
    -layer Metal4 \
    -width 2.36 \
    -offset 1.18 \
    -spacing 0.28 \
    -pitch 426.86 \
    -starts_with GROUND \
    -number_of_straps 2

# Since the above stripes block the top level PDN at Metal4, add some more stripes
# to improve the PDN's integrity and ensure a better connection for the macro.
add_pdn_stripe \
    -grid sram_macro \
    -layer Metal4 \
    -width 4.00 \
    -offset 65.93 \
    -spacing 0.28 \
    -pitch 50 \
    -starts_with GROUND \
    -number_of_straps 7

# ---------------------------------------------------------------------------
# True 3-sided (U-shaped) core ring support.
#
# OpenROAD's add_pdn_ring always builds a CLOSED 4-sided ring (verified in
# src/pdn/src/rings.cpp Rings::makeShapes). We let it build closed so that
# add_pdn_ring -connect_to_pads can collect pad power through RING shapes
# (src/pdn/src/PdnGen.cc makeRing -> setupDirectConnect -> setTargetType RING).
# AFTER pdngen has written the ring and wired the pads, we delete the ring
# metal sitting in the bare-edge margin (the edge with no IO pads). Because
# that edge has no pads, no PadDirectConnectionStraps target its bar, so its
# removal does not remove any power source. The remaining 3 ring sides still
# collect all pad current and the internal Metal2/Metal3 mesh + std-cell
# rails still feed every cell, so PSM-0069 connectivity is preserved.
#
# Strategy: define the "bare margin" as the region strictly beyond the
# core-area boundary on the bare side. Everything pdngen put there only
# served the (now unwanted) bare-edge ring bar:
#   - RING bars wholly in the margin (the bare-side bar itself) -> destroyed.
#   - RING bars straddling the boundary (perpendicular bar overhang past the
#     bare-side corners) -> destroyed and recreated clipped to the boundary.
#   - Any special-net SBox VIA in the margin -> destroyed (it only stitched
#     the removed bare metal; the kept U-ring's corner/grid vias are on the
#     IO-pad sides, never in the bare margin).
# Stripes / followpins / pad-connect straps inside the core are untouched.

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

# Wrap pdngen so the bare-edge ring metal is removed after the network has
# been built and the pads wired. Gated by PDN_BARE_EDGES so configs that do
# not set it keep the unchanged closed-ring behaviour (no regression).
if { [info exists ::env(PDN_BARE_EDGES)] && \
     [string trim $::env(PDN_BARE_EDGES)] != "" } {
    rename pdngen pdn_real_pdngen
    proc pdngen { args } {
        set rc [uplevel 1 [list pdn_real_pdngen {*}$args]]
        # Only post-process a real build (skip -reset/-ripup/-report_only/etc).
        set is_build 1
        foreach a $args {
            if { $a in {-reset -ripup -report_only -check_only} } {
                set is_build 0
            }
        }
        if { $is_build } {
            pdn_remove_bare_edge_ring [string trim $::env(PDN_BARE_EDGES)]
        }
        return $rc
    }
}
