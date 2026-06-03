# Copyright 2026 LibreLane Contributors
#
# PDN configuration for *exact-pad* partial padring designs.
#
# Wraps pdn_partial.tcl with one piece of pre-PDN cleanup that is specific to
# the exact-pad bare-corner slots: destroy the `wafer_space_logo` instance.
#
# Why here (PDN step), not in PAD_CFG (PadRing step)?
# ---------------------------------------------------
# LibreLane runs steps in this order: ... PadRing (16) -> CheckMacroAntenna
# (17) -> ManualMacroPlacement (18) -> ... -> GeneratePDN (where this script
# runs) -> ... Destroying the logo at PadRing kills the instance BEFORE
# ManualMacroPlacement tries to place it, and the manual_macro_placement
# placer then exits(1) with "Declared macros not instantiated in design:
# wafer_space_logo" (see /nix/store/.../librelane/scripts/odbpy/placers.py).
# GeneratePDN runs AFTER ManualMacroPlacement, so by the time this script
# fires the logo has been placed -- and we can safely destroy it before any
# DRC/extraction step sees the layout.
#
# Why destroy at all?
# -------------------
# The `gf180mcu_ws_ip__logo` macro (143.25um x 143.25um, full-area Metal5
# OBS, placed at (die_w - 169.25, die_h - 169.25) by config.yaml MACROS)
# sits squarely inside the NE corner cell's 355x355 footprint. When the
# bare-edge generator destroys the NE corner and `place_io_fill` packs
# filler cells across the freed corner strip, the fillers' Metal5
# collides with the logo's Metal5 OBS -- producing ~357 Magic Illegal
# Overlap errors per build at DRC time. (This used to be misdiagnosed as
# "IO_NORTH extension known-broken / MX-orient bug"; see commit history.)
#
# LVS-safety
# ----------
# The logo's Verilog module is empty (`module gf180mcu_ws_ip__logo;`, no
# ports, no nets) and `LVS_FLATTEN_CELLS` already lists the cell, so
# netgen flattens the netlist reference to nothing -- destroying just the
# layout instance is LVS-safe: extracted spice has no logo, flattened
# netlist has no logo, both sides match. `IGNORE_DISCONNECTED_MODULES`
# already lists the logo cell too, so disconnect warnings stay suppressed.
#
# Licensed under the Apache License, Version 2.0

set _block [ord::get_db_block]
if { $_block ne "NULL" } {
    set _logo_inst [$_block findInst wafer_space_logo]
    if { $_logo_inst ne "NULL" } {
        odb::dbInst_destroy $_logo_inst
        puts "\[INFO\] pdn_partial_exact: destroyed wafer_space_logo\
              instance (avoids NE-corner Metal5 collision with bare-edge\
              IO row extension fillers)."
    } else {
        puts "\[INFO\] pdn_partial_exact: wafer_space_logo instance not\
              found (already absent) -- nothing to do."
    }
}

# Continue with the standard partial-padring PDN topology.
source [file join [file dirname [file normalize [info script]]] \
        pdn_partial.tcl]
