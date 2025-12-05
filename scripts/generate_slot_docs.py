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


if __name__ == "__main__":
    # Placeholder for main
    print("SlotInfo dataclass created successfully")
