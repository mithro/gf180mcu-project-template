# Slot Usable Area Documentation Generator

**Date:** 2025-12-05
**Status:** Approved

## Problem Statement

Users need to know the "usable area" (the yellow region inside the padring) for each slot size. Currently, only the total die dimensions are displayed. The usable area determines how much space is available for user logic, SRAM, and other components.

## Goals

1. Calculate usable area for each slot type (1x1, 0.5x1, 1x0.5, 0.5x0.5)
2. Display in both mm and µm formats
3. Include IO counts (bidir, inputs, analog, power)
4. Generate documentation for GitHub Pages
5. Validate consistency across data sources

## Data Sources

### 1. YAML Files (Primary)
Location: `librelane/slots/slot_*.yaml`

Contains:
- `DIE_AREA: [x1, y1, x2, y2]` - total slot dimensions in µm
- `CORE_AREA: [x1, y1, x2, y2]` - usable area bounds in µm
- `PAD_SOUTH/EAST/NORTH/WEST: [...]` - pad instance lists

### 2. LEF Files (Validation)
Location: `gf180mcu/gf180mcuD/libs.ref/gf180mcu_fd_io/lef/*.lef`

Contains:
- Pad cell dimensions (`SIZE X BY Y`)
- Used to compute expected core area from geometry

### 3. GDS Files (Ground Truth)
Source: CI artifacts from successful builds

Contains:
- Actual layout geometry
- Used to measure true core area bounds

## Validation Strategy

Cross-check all three sources:
```
core_from_yaml ≈ core_from_geometry ≈ core_from_gds
```

If values differ by more than 1µm, log a warning with the discrepancy.

## Data Model

```python
@dataclass
class SlotInfo:
    name: str                    # "1x1", "0p5x1", etc.
    label: str                   # "1×1 (Full)"

    # Die area (total slot size)
    die_width_um: int
    die_height_um: int

    # Core area (usable area inside padring)
    core_width_um: int
    core_height_um: int

    # IO counts
    io_bidir: int
    io_inputs: int
    io_analog: int
    io_power_pairs: int

    # Computed properties
    @property
    def die_area_mm2(self) -> float
    @property
    def core_area_mm2(self) -> float
    @property
    def utilization_pct(self) -> float
```

## Output Formats

### JSON (`slots.json`)
Machine-readable format for programmatic access:
```json
{
  "generated_at": "2025-12-05T10:30:00Z",
  "slots": {
    "1x1": {
      "label": "1×1 (Full)",
      "die": {"width_um": 3932, "height_um": 5122, "area_mm2": 20.13},
      "core": {"width_um": 3048, "height_um": 4238, "area_mm2": 12.92},
      "utilization_pct": 64.2,
      "io": {"bidir": 40, "inputs": 12, "analog": 2, "power_pairs": 8}
    }
  }
}
```

### Markdown (`SLOTS.md`)
Human-readable table:
| Slot | Die Size | Usable Area | Utilization | IOs |
|------|----------|-------------|-------------|-----|
| 1×1 (Full) | 3.93mm × 5.12mm | 3.05mm × 4.24mm (12.92mm²) | 64% | 62 |

### HTML (`index.html`)
GitHub Pages ready with:
- Visual cards showing slot images
- Detailed specs on hover/click
- Download link for JSON
- Light/dark background variants

## Script Architecture

```
scripts/generate_slot_docs.py
├── SlotInfo dataclass
├── parse_slot_yaml(path) → SlotInfo
├── parse_pad_lef(path) → pad dimensions
├── measure_gds_core(path) → actual bounds (optional)
├── validate_consistency() → warnings
├── count_ios(yaml) → IO breakdown
├── generate_json(slots) → slots.json
├── generate_markdown(slots) → SLOTS.md
├── generate_html(slots, images) → index.html
└── main() → orchestrate all outputs
```

## Dependencies

- `pyyaml` - parse slot YAML configs
- `klayout` - measure GDS geometry (optional, graceful fallback)
- `Pillow` - image thumbnail generation

## CLI Usage

```bash
# Generate all outputs to gh-pages/
uv run scripts/generate_slot_docs.py --output-dir gh-pages/

# Include images from CI artifacts
uv run scripts/generate_slot_docs.py --output-dir gh-pages/ --download-images
```

## CI/CD Integration

```yaml
jobs:
  generate-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Generate slot documentation
        run: uv run scripts/generate_slot_docs.py --output-dir gh-pages/

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          publish_dir: ./gh-pages
```

Triggers:
- On push to main (after successful build)
- On workflow_dispatch (manual)

## Future Enhancements

- Maximum SRAM capacity per slot
- Standard cell count estimates at different utilizations
- Interactive capacity calculator
- Comparison with other PDKs/foundries

## Current Slot Dimensions (Reference)

| Slot | DIE_AREA (µm) | CORE_AREA offset | Pad Height |
|------|---------------|------------------|------------|
| 1x1 | 3932 × 5122 | 442 per side | ~350 |
| 0.5x1 | 1936 × 5122 | 442 per side | ~350 |
| 1x0.5 | 3932 × 2531 | 442 per side | ~350 |
| 0.5x0.5 | 1936 × 2531 | 442 per side | ~350 |

Note: DIE_AREA includes 26µm sealring on each side.
