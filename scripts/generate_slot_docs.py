#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml", "Pillow"]
# ///
"""
Generate slot documentation with usable area calculations.

Usage:
    uv run scripts/generate_slot_docs.py --output-dir gh-pages/
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml


@dataclass
class SlotInfo:
    """Information about a slot size."""

    name: str  # "1x1", "0p5x1", etc.
    label: str  # "1×1 (Full)"

    # Die area (total slot size) in microns
    die_width_um: int
    die_height_um: int

    # Core area (usable area inside padring) in microns
    core_width_um: int
    core_height_um: int

    # IO counts
    io_bidir: int = 0
    io_inputs: int = 0
    io_analog: int = 0
    io_power_pairs: int = 0

    @property
    def die_width_mm(self) -> float:
        return self.die_width_um / 1000

    @property
    def die_height_mm(self) -> float:
        return self.die_height_um / 1000

    @property
    def die_area_mm2(self) -> float:
        return self.die_width_mm * self.die_height_mm

    @property
    def core_width_mm(self) -> float:
        return self.core_width_um / 1000

    @property
    def core_height_mm(self) -> float:
        return self.core_height_um / 1000

    @property
    def core_area_mm2(self) -> float:
        return self.core_width_mm * self.core_height_mm

    @property
    def utilization_pct(self) -> float:
        if self.die_area_mm2 == 0:
            return 0.0
        return (self.core_area_mm2 / self.die_area_mm2) * 100

    @property
    def io_total(self) -> int:
        return self.io_bidir + self.io_inputs + self.io_analog + (self.io_power_pairs * 2)


# Slot labels mapping
SLOT_LABELS = {
    "1x1": "1×1 (Full)",
    "0p5x1": "0.5×1 (Half Width)",
    "1x0p5": "1×0.5 (Half Height)",
    "0p5x0p5": "0.5×0.5 (Quarter)",
}


def parse_slot_yaml(yaml_path: Path) -> SlotInfo:
    """Parse a slot YAML file and extract slot information."""
    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    # Extract slot name from filename (e.g., "slot_1x1.yaml" -> "1x1")
    name = yaml_path.stem.replace("slot_", "")
    label = SLOT_LABELS.get(name, name)

    # Parse DIE_AREA: [x1, y1, x2, y2]
    die_area = data.get("DIE_AREA", [0, 0, 0, 0])
    die_width_um = die_area[2] - die_area[0]
    die_height_um = die_area[3] - die_area[1]

    # Parse CORE_AREA: [x1, y1, x2, y2]
    core_area = data.get("CORE_AREA", [0, 0, 0, 0])
    core_width_um = core_area[2] - core_area[0]
    core_height_um = core_area[3] - core_area[1]

    # Count IOs from pad lists
    io_bidir = 0
    io_inputs = 0
    io_analog = 0
    io_power_pairs = 0

    for direction in ["PAD_SOUTH", "PAD_EAST", "PAD_NORTH", "PAD_WEST"]:
        pads = data.get(direction, [])
        for pad in pads:
            pad_str = str(pad)
            if "bidir" in pad_str:
                io_bidir += 1
            elif "inputs" in pad_str or pad_str in ("clk_pad", "rst_n_pad"):
                io_inputs += 1
            elif "analog" in pad_str:
                io_analog += 1
            elif "dvdd_pads" in pad_str:
                io_power_pairs += 1
            # dvss_pads are counted with dvdd as pairs

    return SlotInfo(
        name=name,
        label=label,
        die_width_um=die_width_um,
        die_height_um=die_height_um,
        core_width_um=core_width_um,
        core_height_um=core_height_um,
        io_bidir=io_bidir,
        io_inputs=io_inputs,
        io_analog=io_analog,
        io_power_pairs=io_power_pairs,
    )


def load_all_slots(slots_dir: Path) -> dict[str, SlotInfo]:
    """Load all slot configurations from a directory."""
    slots = {}
    for yaml_file in sorted(slots_dir.glob("slot_*.yaml")):
        slot = parse_slot_yaml(yaml_file)
        slots[slot.name] = slot
    return slots


def generate_json(slots: dict[str, SlotInfo], output_path: Path) -> None:
    """Generate JSON file with slot information."""
    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "slots": {},
    }

    # Sort by slot order: 1x1 first
    slot_order = ["1x1", "0p5x1", "1x0p5", "0p5x0p5"]
    sorted_names = sorted(slots.keys(), key=lambda x: slot_order.index(x) if x in slot_order else 99)

    for name in sorted_names:
        slot = slots[name]
        data["slots"][name] = {
            "label": slot.label,
            "die": {
                "width_um": slot.die_width_um,
                "height_um": slot.die_height_um,
                "width_mm": round(slot.die_width_mm, 3),
                "height_mm": round(slot.die_height_mm, 3),
                "area_mm2": round(slot.die_area_mm2, 2),
            },
            "core": {
                "width_um": slot.core_width_um,
                "height_um": slot.core_height_um,
                "width_mm": round(slot.core_width_mm, 3),
                "height_mm": round(slot.core_height_mm, 3),
                "area_mm2": round(slot.core_area_mm2, 2),
            },
            "utilization_pct": round(slot.utilization_pct, 1),
            "io": {
                "bidir": slot.io_bidir,
                "inputs": slot.io_inputs,
                "analog": slot.io_analog,
                "power_pairs": slot.io_power_pairs,
                "total": slot.io_total,
            },
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"Generated: {output_path}")


def generate_markdown(slots: dict[str, SlotInfo], output_path: Path) -> None:
    """Generate Markdown file with slot information."""
    lines = [
        "# GF180MCU Slot Sizes",
        "",
        "This document describes the available slot sizes for wafer.space projects.",
        "",
        "## Slot Dimensions",
        "",
        "| Slot | Die Size | Usable Area | Utilization | Total IOs |",
        "|------|----------|-------------|-------------|-----------|",
    ]

    slot_order = ["1x1", "0p5x1", "1x0p5", "0p5x0p5"]
    sorted_names = sorted(slots.keys(), key=lambda x: slot_order.index(x) if x in slot_order else 99)

    for name in sorted_names:
        slot = slots[name]
        die_size = f"{slot.die_width_mm:.2f}mm × {slot.die_height_mm:.2f}mm"
        core_size = f"{slot.core_width_mm:.2f}mm × {slot.core_height_mm:.2f}mm ({slot.core_area_mm2:.2f}mm²)"
        util = f"{slot.utilization_pct:.0f}%"
        ios = str(slot.io_total)
        lines.append(f"| {slot.label} | {die_size} | {core_size} | {util} | {ios} |")

    lines.extend([
        "",
        "## IO Breakdown",
        "",
        "| Slot | Bidirectional | Inputs | Analog | Power Pairs |",
        "|------|---------------|--------|--------|-------------|",
    ])

    for name in sorted_names:
        slot = slots[name]
        lines.append(
            f"| {slot.label} | {slot.io_bidir} | {slot.io_inputs} | {slot.io_analog} | {slot.io_power_pairs} |"
        )

    lines.extend([
        "",
        "## Notes",
        "",
        "- **Die Size**: Total slot dimensions including sealring (26µm per side)",
        "- **Usable Area**: CORE_AREA where standard cells can be placed (inside padring)",
        "- **Utilization**: Ratio of usable area to total die area",
        "- **Power Pairs**: Each pair consists of one DVDD and one DVSS pad",
        "",
        f"*Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*",
        "",
    ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    print(f"Generated: {output_path}")


if __name__ == "__main__":
    script_dir = Path(__file__).parent.parent
    slots_dir = script_dir / "librelane" / "slots"
    output_dir = script_dir / "gh-pages"

    slots = load_all_slots(slots_dir)
    generate_json(slots, output_dir / "slots.json")
    generate_markdown(slots, output_dir / "SLOTS.md")
