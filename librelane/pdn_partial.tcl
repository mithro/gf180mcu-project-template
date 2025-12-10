# Copyright 2025 LibreLane Contributors
#
# PDN configuration for partial padring designs
# (IO pads on fewer than 4 edges)
#
# This script creates the core ring WITHOUT -connect_to_pads to avoid
# the issue where ring segments on edges without pads are removed as
# "floating". Power is delivered through IO filler cells which have
# DVDD/DVSS power pins that connect to the ring via metal overlap.
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
# For partial padrings, we do NOT use -connect_to_pads to avoid
# floating segment removal on edges without pads.
if { $::env(PDN_CORE_RING) == 1 } {
    if { $::env(PDN_MULTILAYER) == 1 } {
        set arg_list [list]
        append_if_flag arg_list PDN_CORE_RING_ALLOW_OUT_OF_DIE -allow_out_of_die
        # NOTE: Intentionally NOT using -connect_to_pads for partial padrings
        # append_if_flag arg_list PDN_CORE_RING_CONNECT_TO_PADS -connect_to_pads
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

        # For partial padrings: Create explicit connections from core ring to IO pad power pins
        # on edges that have pads. This bridges the gap between the ring and IO cells.
        #
        # The IO cells have DVDD/DVSS power pins on Metal3/4/5 at the edge facing the core.
        # We add Metal3 stripes that extend from just inside the core ring to beyond the
        # core boundary, overlapping with the IO cell power pins.
        #
        # Geometry:
        # - IO cells are 350µm deep (from die edge towards core)
        # - Core margin with IO is typically 442µm
        # - Core ring is at core_offset (e.g., 20µm) inside core boundary
        # - We need stripes from ring position to where IO cell power pins are (~380-440µm from die edge)

        puts "PDN_PARTIAL: Starting ring-to-pad connection logic"

        # Get die and core dimensions using proper ODB API
        set block [ord::get_db_block]

        set die_rect [$block getDieArea]
        set die_llx [$die_rect xMin]
        set die_lly [$die_rect yMin]
        set die_urx [$die_rect xMax]
        set die_ury [$die_rect yMax]

        set core_rect [$block getCoreArea]
        set core_llx [$core_rect xMin]
        set core_lly [$core_rect yMin]
        set core_urx [$core_rect xMax]
        set core_ury [$core_rect yMax]

        # Ring dimensions for reference
        set ring_voffset $::env(PDN_CORE_RING_VOFFSET)
        set ring_hoffset $::env(PDN_CORE_RING_HOFFSET)
        set ring_vwidth $::env(PDN_CORE_RING_VWIDTH)
        set ring_hwidth $::env(PDN_CORE_RING_HWIDTH)

        # Stripe width for connections (matches ring width for good overlap)
        set conn_stripe_width 10.0
        # Stripe pitch (dense to ensure overlap with IO cell power pins)
        set conn_stripe_pitch 75.0
        # Number of stripes (enough to cover the IO cell power pin distribution)
        set conn_stripe_count 5

        # Define a grid for ring-to-pad connections
        define_pdn_grid \
            -name pad_conn_grid \
            -starts_with POWER \
            -voltage_domain CORE

        # Determine which edges have pads by comparing die/core margins
        # Edges with IO pads have large margins (~350-450µm for IO cells)
        # Edges without pads have small margins (~100-150µm)
        # GF180MCU uses database units of 2000 per µm (0.5nm resolution)
        # Threshold: 300µm = 300 * 2000 = 600000 database units
        set pad_margin_threshold 600000.0

        set margin_west [expr {$core_llx - $die_llx}]
        set margin_east [expr {$die_urx - $core_urx}]
        set margin_south [expr {$core_lly - $die_lly}]
        set margin_north [expr {$die_ury - $core_ury}]

        set has_west_pads [expr {$margin_west > $pad_margin_threshold}]
        set has_east_pads [expr {$margin_east > $pad_margin_threshold}]
        set has_south_pads [expr {$margin_south > $pad_margin_threshold}]
        set has_north_pads [expr {$margin_north > $pad_margin_threshold}]

        puts "PDN: Die area: ($die_llx, $die_lly) to ($die_urx, $die_ury)"
        puts "PDN: Core area: ($core_llx, $core_lly) to ($core_urx, $core_ury)"
        puts "PDN: Margins - W:$margin_west E:$margin_east S:$margin_south N:$margin_north"
        puts "PDN: Edges with pads - W:$has_west_pads E:$has_east_pads S:$has_south_pads N:$has_north_pads"

        # Add connection stripes for each edge that has pads
        # Note: add_pdn_stripe parameters (offset, width, pitch) are in MICRONS
        # The offset is measured from the grid boundary (which defaults to die area)

        # For horizontal stripes (Metal3): offset is from bottom
        # For vertical stripes (Metal2): offset is from left
        # Use offset matching the standard grid offset to align with main stripes
        set stripe_offset 50.0

        # West/East edges: horizontal stripes on Metal3
        if { $has_west_pads || $has_east_pads } {
            if { $has_west_pads } {
                puts "PDN: Adding ring-to-pad connections on WEST edge"
            }
            if { $has_east_pads } {
                puts "PDN: Adding ring-to-pad connections on EAST edge"
            }
            add_pdn_stripe \
                -grid pad_conn_grid \
                -layer Metal3 \
                -width $conn_stripe_width \
                -pitch $conn_stripe_pitch \
                -offset $stripe_offset \
                -starts_with POWER \
                -extend_to_boundary
        }

        # North/South edges: vertical stripes on Metal2
        if { $has_north_pads || $has_south_pads } {
            if { $has_north_pads } {
                puts "PDN: Adding ring-to-pad connections on NORTH edge"
            }
            if { $has_south_pads } {
                puts "PDN: Adding ring-to-pad connections on SOUTH edge"
            }
            add_pdn_stripe \
                -grid pad_conn_grid \
                -layer Metal2 \
                -width $conn_stripe_width \
                -pitch $conn_stripe_pitch \
                -offset $stripe_offset \
                -starts_with POWER \
                -extend_to_boundary
        }

        # Connect the pad_conn_grid stripes to the core ring layers
        add_pdn_connect \
            -grid pad_conn_grid \
            -layers "Metal2 Metal3"

        if { [info exists ::env(PDN_CORE_VERTICAL_LAYER)] } {
            add_pdn_connect \
                -grid pad_conn_grid \
                -layers "Metal2 $::env(PDN_CORE_VERTICAL_LAYER)"
        }

        if { [info exists ::env(PDN_CORE_HORIZONTAL_LAYER)] } {
            add_pdn_connect \
                -grid pad_conn_grid \
                -layers "Metal3 $::env(PDN_CORE_HORIZONTAL_LAYER)"
        }

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
