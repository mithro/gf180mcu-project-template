#!/usr/bin/env python3
"""Create a thumbnail from an image file."""
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///

import sys
from pathlib import Path

from PIL import Image


def create_thumbnail(input_path: str, output_path: str, max_width: int = 400) -> None:
    """Create a thumbnail of the input image."""
    img = Image.open(input_path)
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    w, h = img.size
    if w > max_width:
        img = img.resize((max_width, int(h * max_width / w)), Image.Resampling.LANCZOS)
    img.save(output_path, "JPEG", quality=85)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input_image> <output_thumbnail>", file=sys.stderr)
        sys.exit(1)
    create_thumbnail(sys.argv[1], sys.argv[2])
