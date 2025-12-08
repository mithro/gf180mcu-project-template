#!/usr/bin/env python3
"""Generate slot configurations with various IO pad arrangements.

This script generates YAML configuration files for different slot sizes
with various pad density and edge arrangements.

Naming scheme: <slotsize>_<density>_<edges>

Density codes (3 chars):
  - def: Default/reference configuration (copies existing slot configs)
  - max: Maximum pads possible for this slot
  - spc: Match 1x1 pad spacing/layout
  - num: Match 1x1 pad count

Edge codes (3 chars):
  - all: All four edges
  - top: Top edge only
  - lft: Left edge only
  - hor: Horizontal edges (top + bottom)
  - ver: Vertical edges (left + right)
  - nwc: Northwest corner (top + left)
  - sec: Southeast corner (bottom + right)

Note: DEF density is only valid with ALL edges (copies the original slot configs).
"""
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///

import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml


# =============================================================================
# Constants from GF180MCU PDK
# =============================================================================

# IO cell dimensions (from LEF files)
IO_CELL_WIDTH = 75.0  # um
IO_CELL_HEIGHT = 350.0  # um

# Corner cell dimensions
CORNER_CELL_SIZE = 355.0  # um (square)

# Seal ring width
SEAL_RING = 26.0  # um on each edge

# Reference 1x1 pad counts (from default slot_1x1.yaml)
REF_1X1_PAD_COUNT = 74  # Total pads in default 1x1 config

# Default pad counts for each slot (from existing slot_*.yaml files)
DEFAULT_PAD_COUNTS = {
    "1x1": 74,
    "0p5x1": 72,
    "1x0p5": 72,
    "0p5x0p5": 56,
}


# =============================================================================
# Type Definitions
# =============================================================================

Edge = Literal["north", "south", "east", "west"]


class Density(Enum):
    """IO pad density modes."""
    DEF = "def"  # Default/reference (matches existing configs)
    MAX = "max"  # Maximum pads possible
    SPC = "spc"  # Match 1x1 spacing/layout
    NUM = "num"  # Match 1x1 pad count


class Edges(Enum):
    """IO pad edge configurations."""
    ALL = "all"  # All four edges
    TOP = "top"  # Top (north) edge only
    LFT = "lft"  # Left (west) edge only
    HOR = "hor"  # Horizontal edges (north + south)
    VER = "ver"  # Vertical edges (east + west)
    NWC = "nwc"  # Northwest corner (north + west)
    SEC = "sec"  # Southeast corner (south + east)

    @property
    def active_edges(self) -> set[Edge]:
        """Return the set of active edges for this configuration."""
        return {
            Edges.ALL: {"north", "south", "east", "west"},
            Edges.TOP: {"north"},
            Edges.LFT: {"west"},
            Edges.HOR: {"north", "south"},
            Edges.VER: {"east", "west"},
            Edges.NWC: {"north", "west"},
            Edges.SEC: {"south", "east"},
        }[self]

    @property
    def description(self) -> str:
        """Human-readable description of this edge configuration."""
        return {
            Edges.ALL: "All four edges",
            Edges.TOP: "Top (north) edge only",
            Edges.LFT: "Left (west) edge only",
            Edges.HOR: "Horizontal edges (north + south)",
            Edges.VER: "Vertical edges (east + west)",
            Edges.NWC: "Northwest corner (north + west)",
            Edges.SEC: "Southeast corner (south + east)",
        }[self]


# =============================================================================
# Slot Definitions
# =============================================================================

@dataclass
class SlotDefinition:
    """Definition of a slot's physical dimensions."""
    name: str
    die_width: int  # um
    die_height: int  # um
    core_x1: int  # um
    core_y1: int  # um
    core_x2: int  # um
    core_y2: int  # um
    verilog_define: str


# Define the four standard slot sizes
SLOTS = {
    "1x1": SlotDefinition(
        name="1x1",
        die_width=3932,
        die_height=5122,
        core_x1=442,
        core_y1=442,
        core_x2=3490,
        core_y2=4680,
        verilog_define="SLOT_1X1",
    ),
    "0p5x1": SlotDefinition(
        name="0p5x1",
        die_width=1936,
        die_height=5122,
        core_x1=442,
        core_y1=442,
        core_x2=1494,
        core_y2=4680,
        verilog_define="SLOT_0P5X1",
    ),
    "1x0p5": SlotDefinition(
        name="1x0p5",
        die_width=3932,
        die_height=2531,
        core_x1=442,
        core_y1=442,
        core_x2=3490,
        core_y2=2089,
        verilog_define="SLOT_1X0P5",
    ),
    "0p5x0p5": SlotDefinition(
        name="0p5x0p5",
        die_width=1936,
        die_height=2531,
        core_x1=442,
        core_y1=442,
        core_x2=1494,
        core_y2=2089,
        verilog_define="SLOT_0P5X0P5",
    ),
}


# =============================================================================
# Pad Calculation Functions
# =============================================================================

def calculate_max_pads_per_edge(slot: SlotDefinition) -> dict[str, int]:
    """Calculate maximum number of pads that can fit on each edge.

    North/South edges: (die_width - 2*corner) / io_width
    East/West edges: (die_height - 2*corner) / io_width

    Note: IO cells are placed with their 75um side along the edge.
    """
    ns_available = slot.die_width - 2 * CORNER_CELL_SIZE
    ew_available = slot.die_height - 2 * CORNER_CELL_SIZE

    return {
        "north": int(ns_available / IO_CELL_WIDTH),
        "south": int(ns_available / IO_CELL_WIDTH),
        "east": int(ew_available / IO_CELL_WIDTH),
        "west": int(ew_available / IO_CELL_WIDTH),
    }


def get_1x1_max_pads() -> dict[str, int]:
    """Get maximum pads per edge for 1x1 slot (reference for spacing)."""
    return calculate_max_pads_per_edge(SLOTS["1x1"])


def calculate_pads_for_density(
    slot: SlotDefinition,
    density: Density,
    edges: Edges,
) -> tuple[int, dict[str, int]]:
    """Calculate total pads and per-edge distribution for a given density mode.

    Args:
        slot: Slot definition
        density: Density mode (def, max, spc, num)
        edges: Edge configuration

    Returns:
        Tuple of (total_pads, pads_per_edge_dict)
    """
    max_pads = calculate_max_pads_per_edge(slot)
    ref_1x1_max = get_1x1_max_pads()
    active = edges.active_edges

    if density == Density.DEF:
        # Use default pad count for this slot, distributed across active edges
        target_total = DEFAULT_PAD_COUNTS[slot.name]
        total_capacity = sum(max_pads[e] for e in active)

        # Don't exceed what we can actually fit
        target_total = min(target_total, total_capacity)

        # Distribute proportionally based on edge capacity
        pads_per_edge = {}
        remaining = target_total
        edge_list = sorted(active)

        for i, e in enumerate(edge_list):
            if i == len(edge_list) - 1:
                pads_per_edge[e] = remaining
            else:
                ratio = max_pads[e] / total_capacity
                edge_count = int(target_total * ratio)
                pads_per_edge[e] = min(edge_count, max_pads[e])
                remaining -= pads_per_edge[e]

    elif density == Density.MAX:
        # Use maximum pads that fit on each active edge
        pads_per_edge = {e: max_pads[e] for e in active}

    elif density == Density.SPC:
        # Match 1x1 spacing - use 1x1 max counts but limited by slot size
        pads_per_edge = {}
        for e in active:
            pads_per_edge[e] = min(max_pads[e], ref_1x1_max[e])

    elif density == Density.NUM:
        # Match 1x1 total pad count, distributed across active edges
        # Scale the reference count proportionally across active edges
        total_ref = REF_1X1_PAD_COUNT
        total_capacity = sum(max_pads[e] for e in active)

        # Don't exceed what we can actually fit
        target_total = min(total_ref, total_capacity)

        # Distribute proportionally based on edge capacity
        pads_per_edge = {}
        remaining = target_total
        edge_list = sorted(active)  # Consistent ordering

        for i, e in enumerate(edge_list):
            if i == len(edge_list) - 1:
                # Last edge gets remainder
                pads_per_edge[e] = remaining
            else:
                # Proportional distribution
                ratio = max_pads[e] / total_capacity
                edge_count = int(target_total * ratio)
                pads_per_edge[e] = min(edge_count, max_pads[e])
                remaining -= pads_per_edge[e]

    total = sum(pads_per_edge.values())
    return total, pads_per_edge


def distribute_pads_with_power(
    total_pads: int,
    power_ratio: float = 0.15,
) -> tuple[int, int]:
    """Calculate signal and power pad counts for a given total.

    Args:
        total_pads: Total number of pad positions available
        power_ratio: Target ratio of power pads (default 15%)

    Returns:
        Tuple of (signal_pads, power_pads)
    """
    # Reserve 2 pads for clk and rst_n
    available = total_pads - 2

    # Calculate power pads (rounded up to even number for VDD/VSS pairs)
    power_pads = int(available * power_ratio)
    if power_pads % 2 == 1:
        power_pads += 1

    signal_pads = available - power_pads

    return signal_pads, power_pads


# =============================================================================
# Pad Generation Functions
# =============================================================================

def generate_edge_pads(
    edge_pad_count: int,
    signal_count: int,
    power_count: int,
    bidir_start: int,
    vdd_start: int,
    vss_start: int,
    include_clk_rst: bool = False,
    reverse: bool = False,
) -> tuple[list[str], int, int, int]:
    """Generate pads for a single edge with interspersed power.

    Args:
        edge_pad_count: Number of pads to place on this edge
        signal_count: Number of signal pads to place
        power_count: Number of power pads to place
        bidir_start: Starting index for bidir pads
        vdd_start: Starting index for VDD pads
        vss_start: Starting index for VSS pads
        include_clk_rst: Whether to include clk and rst_n pads
        reverse: Whether to reverse the pad order

    Returns:
        Tuple of (pad_list, next_bidir, next_vdd, next_vss)
    """
    pads = []

    # Add clk/rst if requested
    if include_clk_rst:
        pads.extend(["clk_pad", "rst_n_pad"])
        signal_count -= 2  # These take 2 signal pad slots

    # Distribute power pads evenly among signal pads
    if power_count > 0 and signal_count > 0:
        signals_per_power = signal_count // (power_count + 1)

        bidir_idx = bidir_start
        vdd_idx = vdd_start
        vss_idx = vss_start
        power_placed = 0
        signal_placed = 0

        while signal_placed < signal_count or power_placed < power_count:
            # Place some signal pads
            for _ in range(min(signals_per_power, signal_count - signal_placed)):
                pads.append(f'bidir\\\\[{bidir_idx}\\\\].pad')
                bidir_idx += 1
                signal_placed += 1

            # Place a power pad pair if we have more
            if power_placed < power_count:
                if power_placed % 2 == 0:
                    pads.append(f'dvss_pads\\\\[{vss_idx}\\\\].pad')
                    vss_idx += 1
                else:
                    pads.append(f'dvdd_pads\\\\[{vdd_idx}\\\\].pad')
                    vdd_idx += 1
                power_placed += 1

        # Place remaining signals
        while signal_placed < signal_count:
            pads.append(f'bidir\\\\[{bidir_idx}\\\\].pad')
            bidir_idx += 1
            signal_placed += 1
    else:
        # No power pads, just signals
        bidir_idx = bidir_start
        vdd_idx = vdd_start
        vss_idx = vss_start

        for _ in range(signal_count):
            pads.append(f'bidir\\\\[{bidir_idx}\\\\].pad')
            bidir_idx += 1

    if reverse:
        # Keep clk/rst at start if present, reverse the rest
        if include_clk_rst:
            pads = pads[:2] + list(reversed(pads[2:]))
        else:
            pads = list(reversed(pads))

    return pads, bidir_idx, vdd_idx, vss_idx


# =============================================================================
# YAML Generation
# =============================================================================

def generate_config_yaml(
    slot: SlotDefinition,
    density: Density,
    edges: Edges,
    output_dir: Path,
) -> Path:
    """Generate a YAML configuration file for a slot/density/edges combination.

    Args:
        slot: Slot definition
        density: Density mode
        edges: Edge configuration
        output_dir: Directory to write the YAML file

    Returns:
        Path to the generated file
    """
    active_edges = edges.active_edges
    total_pads, pads_per_edge = calculate_pads_for_density(slot, density, edges)
    signal_pads, power_pads = distribute_pads_with_power(total_pads)

    # Distribute signal and power pads across edges proportionally
    edge_signal = {}
    edge_power = {}
    for e in active_edges:
        ratio = pads_per_edge[e] / total_pads if total_pads > 0 else 0
        edge_signal[e] = int(signal_pads * ratio)
        edge_power[e] = int(power_pads * ratio)

    # Build the YAML structure
    yaml_data = {
        "FP_SIZING": "absolute",
        "DIE_AREA": [0, 0, slot.die_width, slot.die_height],
        "CORE_AREA": [slot.core_x1, slot.core_y1, slot.core_x2, slot.core_y2],
        "VERILOG_DEFINES": [slot.verilog_define],
    }

    # Generate pads for each edge
    bidir_idx = 0
    vdd_idx = 0
    vss_idx = 0

    # Determine which edge gets clk/rst (prefer south, then first active)
    clk_rst_edge = None
    if "south" in active_edges:
        clk_rst_edge = "south"
    else:
        for edge in ["west", "east", "north"]:
            if edge in active_edges:
                clk_rst_edge = edge
                break

    # Generate pads for each cardinal direction
    for direction, edge_name in [
        ("PAD_SOUTH", "south"),
        ("PAD_EAST", "east"),
        ("PAD_NORTH", "north"),
        ("PAD_WEST", "west"),
    ]:
        if edge_name in active_edges:
            reverse = edge_name in ("north", "west")
            pads, bidir_idx, vdd_idx, vss_idx = generate_edge_pads(
                pads_per_edge[edge_name],
                edge_signal[edge_name],
                edge_power[edge_name],
                bidir_idx, vdd_idx, vss_idx,
                include_clk_rst=(clk_rst_edge == edge_name),
                reverse=reverse,
            )
            yaml_data[direction] = pads
        else:
            yaml_data[direction] = []

    # Generate filename: slot_<size>_<density>_<edges>.yaml
    filename = f"slot_{slot.name}_{density.value}_{edges.value}.yaml"
    output_path = output_dir / filename

    # Write YAML with comments
    density_desc = {
        Density.DEF: "Default density",
        Density.MAX: "Maximum density",
        Density.SPC: "1x1 spacing",
        Density.NUM: "1x1 pad count",
    }[density]

    with open(output_path, "w") as f:
        f.write(f"# {density_desc}, {edges.description}\n")
        f.write(f"# Slot: {slot.name}, Density: {density.value}, Edges: {edges.value}\n")
        f.write(f"# Total pads: {total_pads} (signal: {signal_pads}, power: {power_pads})\n")
        f.write("#\n")
        f.write("# Floorplanning\n")

        f.write(f"FP_SIZING: {yaml_data['FP_SIZING']}\n")
        f.write(f"DIE_AREA: {yaml_data['DIE_AREA']}\n")
        f.write(f"CORE_AREA: {yaml_data['CORE_AREA']}\n")
        f.write(f"\n")
        f.write(f"VERILOG_DEFINES: {yaml_data['VERILOG_DEFINES']}\n")
        f.write(f"\n")
        f.write("# Pad instances for the padring\n")

        for edge in ["PAD_SOUTH", "PAD_EAST", "PAD_NORTH", "PAD_WEST"]:
            pads = yaml_data[edge]
            if pads:
                f.write(f"{edge}: [\n")
                for i, pad in enumerate(pads):
                    comma = "," if i < len(pads) - 1 else ""
                    if pad in ("clk_pad", "rst_n_pad"):
                        f.write(f"    {pad}{comma}\n")
                    else:
                        f.write(f'    "{pad}"{comma}\n')
                f.write("]\n\n")
            else:
                f.write(f"{edge}: []\n\n")

    return output_path


# =============================================================================
# Main
# =============================================================================

def copy_default_config(slot_name: str, output_dir: Path) -> Path:
    """Copy the original slot config file as the def_all variant.

    Args:
        slot_name: Name of the slot (e.g., "1x1", "0p5x0p5")
        output_dir: Directory to write the copied file

    Returns:
        Path to the copied file
    """
    slots_dir = output_dir.parent
    source = slots_dir / f"slot_{slot_name}.yaml"
    dest = output_dir / f"slot_{slot_name}_def_all.yaml"

    # Copy and prepend a comment explaining this is a copy
    with open(source, "r") as f:
        content = f.read()

    with open(dest, "w") as f:
        f.write(f"# Default density, All four edges\n")
        f.write(f"# Copied from slot_{slot_name}.yaml (the original default configuration)\n")
        f.write(f"# Slot: {slot_name}, Density: def, Edges: all\n")
        f.write(f"#\n")
        f.write(content)

    return dest


def main() -> None:
    """Generate all slot configuration variants."""
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "librelane" / "slots" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating slot configurations in: {output_dir}")
    print()
    print("Naming scheme: <slotsize>_<density>_<edges>")
    print("  Density: def (default), max (maximum), spc (1x1 spacing), num (1x1 count)")
    print("  Edges:   all, top, lft (left), hor (horizontal), ver (vertical), nwc (NW corner), sec (SE corner)")
    print()

    generated_files = []

    for slot_name, slot in SLOTS.items():
        max_pads = calculate_max_pads_per_edge(slot)
        print(f"Slot: {slot_name}")
        print(f"  Max pads per edge: N/S={max_pads['north']}, E/W={max_pads['east']}")

        for density in Density:
            for edges in Edges:
                # Skip invalid combinations for 1x1 slot:
                # - spc (1x1 spacing) is meaningless for 1x1 itself
                # - num (1x1 count) is equivalent to def for 1x1
                if slot_name == "1x1" and density in (Density.SPC, Density.NUM):
                    continue

                # DEF density is only valid with ALL edges
                # (it copies the original config which uses all edges)
                if density == Density.DEF and edges != Edges.ALL:
                    continue

                # For DEF + ALL, copy the original config file
                if density == Density.DEF and edges == Edges.ALL:
                    output_path = copy_default_config(slot_name, output_dir)
                    generated_files.append(output_path)
                    print(f"  - {density.value}_{edges.value}: (copied original) -> {output_path.name}")
                    continue

                total, _ = calculate_pads_for_density(slot, density, edges)
                output_path = generate_config_yaml(slot, density, edges, output_dir)
                generated_files.append(output_path)

                print(f"  - {density.value}_{edges.value}: {total} pads -> {output_path.name}")

    print()
    print(f"Generated {len(generated_files)} configuration files.")

    # Print summary for CI integration
    print()
    print("Configuration names for CI matrix:")
    config_names = sorted(set(
        f.stem.replace("slot_", "") for f in generated_files
    ))
    print(f"  {config_names}")


if __name__ == "__main__":
    main()
