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
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


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


def parse_pad_lef(lef_dir: Path) -> dict[str, tuple[float, float]]:
    """Parse LEF files to get pad cell dimensions."""
    pad_sizes = {}

    for lef_file in lef_dir.glob("*.lef"):
        with open(lef_file) as f:
            content = f.read()

        # Extract SIZE X BY Y
        match = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", content)
        if match:
            width = float(match.group(1))
            height = float(match.group(2))
            cell_name = lef_file.stem
            pad_sizes[cell_name] = (width, height)

    return pad_sizes


def validate_geometry(slots: dict[str, SlotInfo], pad_sizes: dict[str, tuple[float, float]]) -> list[str]:
    """Validate slot dimensions against pad geometry."""
    warnings = []

    # Get typical IO pad height (use bi_t as reference)
    io_pad_height = None
    for name, (w, h) in pad_sizes.items():
        if "bi_t" in name or "bi_24t" in name:
            io_pad_height = h
            break

    if io_pad_height is None:
        warnings.append("Could not find IO pad dimensions for validation")
        return warnings

    # Expected core offset = pad height + margin
    # We expect ~350µm pad + ~92µm margin = ~442µm
    expected_min_offset = io_pad_height  # At minimum, pad height

    for name, slot in slots.items():
        # Calculate actual offset from YAML
        # CORE_AREA starts at [442, 442, ...] meaning 442µm offset
        # This is derived from DIE - CORE
        die_width = slot.die_width_um
        core_width = slot.core_width_um
        offset = (die_width - core_width) / 2

        if offset < expected_min_offset:
            warnings.append(
                f"{name}: Core offset ({offset:.0f}µm) is less than pad height ({io_pad_height:.0f}µm)"
            )

    return warnings


REPO = "wafer-space/gf180mcu-project-template"
IMAGE_ARTIFACT_SUFFIX = "_image"
THUMBNAIL_WIDTH = 400
JPEG_QUALITY = 85


def download_images(output_dir: Path) -> bool:
    """Download slot images from latest GitHub Actions run."""
    if not HAS_PIL:
        print("Warning: Pillow not installed, skipping image download")
        return False

    images_dir = output_dir / "images"
    thumbnails_dir = output_dir / "thumbnails"
    images_dir.mkdir(parents=True, exist_ok=True)
    thumbnails_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Get latest successful run
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/actions/runs?branch=main&status=success&per_page=1",
             "-q", ".workflow_runs[0].id"],
            capture_output=True, text=True, check=True
        )
        run_id = result.stdout.strip()
        if not run_id:
            print("No successful runs found")
            return False

        print(f"Downloading images from run {run_id}...")

        # Get artifacts
        result = subprocess.run(
            ["gh", "api", f"repos/{REPO}/actions/runs/{run_id}/artifacts",
             "-q", ".artifacts[].name"],
            capture_output=True, text=True, check=True
        )
        artifacts = [a for a in result.stdout.strip().split("\n") if a.endswith(IMAGE_ARTIFACT_SUFFIX)]

        for artifact_name in artifacts:
            slot_name = artifact_name.replace(IMAGE_ARTIFACT_SUFFIX, "")
            print(f"  Downloading {slot_name}...")

            with tempfile.TemporaryDirectory() as tmp_dir:
                subprocess.run(
                    ["gh", "run", "download", run_id, "-R", REPO, "-n", artifact_name, "-D", tmp_dir],
                    check=True, capture_output=True
                )

                for png_file in Path(tmp_dir).glob("*.png"):
                    variant = "black" if "black" in png_file.name.lower() else "white"
                    new_name = f"{slot_name}_{variant}.png"

                    # Copy full image
                    final_path = images_dir / new_name
                    png_file.rename(final_path)

                    # Create thumbnail
                    thumb_path = thumbnails_dir / f"{slot_name}_{variant}.jpg"
                    with Image.open(final_path) as img:
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                        width, height = img.size
                        if width > THUMBNAIL_WIDTH:
                            ratio = THUMBNAIL_WIDTH / width
                            img = img.resize((THUMBNAIL_WIDTH, int(height * ratio)), Image.Resampling.LANCZOS)
                        img.save(thumb_path, "JPEG", quality=JPEG_QUALITY, optimize=True)

        return True

    except subprocess.CalledProcessError as e:
        print(f"Error downloading images: {e}")
        return False
    except FileNotFoundError:
        print("Error: 'gh' CLI not found. Install GitHub CLI to download images.")
        return False


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


def generate_html(
    slots: dict[str, SlotInfo],
    output_path: Path,
    images_dir: Path | None = None,
) -> None:
    """Generate HTML file with slot information for GitHub Pages."""
    slot_order = ["1x1", "0p5x1", "1x0p5", "0p5x0p5"]
    sorted_names = sorted(slots.keys(), key=lambda x: slot_order.index(x) if x in slot_order else 99)

    # Base width for 1x1 slot cards (in pixels)
    base_width = 280

    # Check which images exist
    def get_image_path(name: str, variant: str) -> str | None:
        if images_dir is None:
            return None
        thumb = images_dir / "thumbnails" / f"{name}_{variant}.jpg"
        if thumb.exists():
            return f"thumbnails/{name}_{variant}.jpg"
        return None

    generated_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GF180MCU Slot Sizes - wafer.space</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
        }}
        h1 {{ text-align: center; margin-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #666; margin-bottom: 30px; }}
        .subtitle a {{ color: #0066cc; text-decoration: none; }}
        .section {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            margin: 0 auto 20px auto;
            max-width: 1200px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .section h2 {{ margin: 0 0 20px 0; text-align: center; }}
        .slots-grid {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: center;
        }}
        .slot-card {{
            background: #fafafa;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
        }}
        .slot-card h3 {{ margin: 0 0 10px 0; font-size: 1.1em; }}
        .slot-card .dims {{ font-size: 0.85em; color: #666; margin-bottom: 10px; }}
        .slot-card .specs {{ font-size: 0.8em; text-align: left; }}
        .slot-card .specs dt {{ font-weight: bold; color: #555; }}
        .slot-card .specs dd {{ margin: 0 0 8px 0; }}
        .slot-card img {{
            display: block;
            margin: 10px auto;
            border-radius: 4px;
            cursor: pointer;
        }}
        .slot-card img:hover {{ opacity: 0.9; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th, td {{
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #e0e0e0;
        }}
        th {{ background: #f5f5f5; font-weight: 600; }}
        .download-link {{
            display: inline-block;
            margin-top: 20px;
            padding: 10px 20px;
            background: #0066cc;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }}
        .download-link:hover {{ background: #0055aa; }}
        .modal {{
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0; top: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.9);
        }}
        .modal img {{
            max-width: 95%; max-height: 95%;
            margin: auto;
            position: absolute;
            top: 50%; left: 50%;
            transform: translate(-50%, -50%);
        }}
        .modal .close {{
            position: absolute;
            top: 20px; right: 35px;
            color: white;
            font-size: 40px;
            cursor: pointer;
        }}
    </style>
</head>
<body>
    <h1>GF180MCU Slot Sizes</h1>
    <p class="subtitle">
        wafer.space Project Template |
        <a href="https://github.com/wafer-space/gf180mcu-project-template">GitHub</a> |
        Generated: {generated_time}
    </p>

    <div class="section">
        <h2>Available Slots</h2>
        <div class="slots-grid">
"""

    for name in sorted_names:
        slot = slots[name]
        # Scale card width based on slot dimensions
        scale = 1.0
        if "0p5" in name and "x0p5" not in name:
            scale = 0.5 if name.startswith("0p5") else 1.0
        elif name == "0p5x0p5":
            scale = 0.5

        card_width = int(base_width * scale)
        img_width = int(200 * scale)

        img_html = ""
        img_path = get_image_path(name, "white")
        if img_path:
            full_img = f"images/{name}_white.png"
            img_html = f'<img src="{img_path}" alt="{slot.label}" width="{img_width}" onclick="openModal(\'{full_img}\')">'

        html += f"""            <div class="slot-card" style="width: {card_width}px;">
                <h3>{slot.label}</h3>
                <div class="dims">{slot.die_width_mm:.2f}mm × {slot.die_height_mm:.2f}mm</div>
                {img_html}
                <dl class="specs">
                    <dt>Usable Area</dt>
                    <dd>{slot.core_width_mm:.2f}mm × {slot.core_height_mm:.2f}mm ({slot.core_area_mm2:.2f}mm²)</dd>
                    <dt>Utilization</dt>
                    <dd>{slot.utilization_pct:.0f}%</dd>
                    <dt>Total IOs</dt>
                    <dd>{slot.io_total} (bidir: {slot.io_bidir}, in: {slot.io_inputs}, analog: {slot.io_analog})</dd>
                </dl>
            </div>
"""

    html += """        </div>
    </div>

    <div class="section">
        <h2>Detailed Specifications</h2>
        <table>
            <thead>
                <tr>
                    <th>Slot</th>
                    <th>Die Size</th>
                    <th>Usable Area</th>
                    <th>Utilization</th>
                    <th>Bidir</th>
                    <th>Inputs</th>
                    <th>Analog</th>
                    <th>Power</th>
                </tr>
            </thead>
            <tbody>
"""

    for name in sorted_names:
        slot = slots[name]
        html += f"""                <tr>
                    <td>{slot.label}</td>
                    <td>{slot.die_width_mm:.2f}mm × {slot.die_height_mm:.2f}mm</td>
                    <td>{slot.core_width_mm:.2f}mm × {slot.core_height_mm:.2f}mm ({slot.core_area_mm2:.2f}mm²)</td>
                    <td>{slot.utilization_pct:.0f}%</td>
                    <td>{slot.io_bidir}</td>
                    <td>{slot.io_inputs}</td>
                    <td>{slot.io_analog}</td>
                    <td>{slot.io_power_pairs} pairs</td>
                </tr>
"""

    html += """            </tbody>
        </table>
        <div style="text-align: center;">
            <a href="slots.json" class="download-link">Download JSON</a>
        </div>
    </div>

    <div id="imageModal" class="modal" onclick="closeModal()">
        <span class="close">&times;</span>
        <img id="modalImage">
    </div>

    <script>
        function openModal(src) {
            document.getElementById('imageModal').style.display = 'block';
            document.getElementById('modalImage').src = src;
        }
        function closeModal() {
            document.getElementById('imageModal').style.display = 'none';
        }
        document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
    </script>
</body>
</html>
"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Generated: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate slot documentation with usable area calculations"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("gh-pages"),
        help="Output directory for generated files (default: gh-pages)",
    )
    parser.add_argument(
        "--slots-dir",
        type=Path,
        default=None,
        help="Directory containing slot YAML files (default: librelane/slots)",
    )
    parser.add_argument(
        "--download-images",
        action="store_true",
        help="Download slot images from latest GitHub Actions run",
    )

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent.parent
    slots_dir = args.slots_dir or (script_dir / "librelane" / "slots")
    output_dir = args.output_dir

    if not slots_dir.exists():
        print(f"Error: Slots directory not found: {slots_dir}")
        return 1

    # Load and generate
    print(f"Loading slots from: {slots_dir}")
    slots = load_all_slots(slots_dir)

    if not slots:
        print("Error: No slot configurations found")
        return 1

    print(f"Found {len(slots)} slot configurations")

    # Validate against pad geometry if available
    pdk_io_dir = script_dir / "gf180mcu" / "gf180mcuD" / "libs.ref" / "gf180mcu_fd_io" / "lef"
    if pdk_io_dir.exists():
        print(f"Validating against pad geometry from: {pdk_io_dir}")
        pad_sizes = parse_pad_lef(pdk_io_dir)
        warnings = validate_geometry(slots, pad_sizes)
        for warning in warnings:
            print(f"  WARNING: {warning}")
        if not warnings:
            print("  Validation passed: geometry consistent")
    else:
        print("Note: PDK not found, skipping geometry validation")

    # Download images if requested
    if args.download_images:
        print("Downloading images from GitHub Actions...")
        if download_images(output_dir):
            print("Images downloaded successfully")
        else:
            print("Image download failed or skipped")

    # Generate outputs
    generate_json(slots, output_dir / "slots.json")
    generate_markdown(slots, output_dir / "SLOTS.md")
    generate_html(slots, output_dir / "index.html", images_dir=output_dir)

    print(f"\nAll outputs written to: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
