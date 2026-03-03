#!/usr/bin/env python3
"""Regenerate icon.icns from icon.png. Run from project root or build/."""

from pathlib import Path

from PIL import Image

# Resolve paths relative to this script
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
ASSETS_DIR = PROJECT_ROOT / "src" / "tpv2garmin" / "assets"
PNG_PATH = ASSETS_DIR / "icon.png"
ICNS_PATH = ASSETS_DIR / "icon.icns"


def main() -> None:
    if not PNG_PATH.exists():
        raise SystemExit(f"Source not found: {PNG_PATH}")

    img = Image.open(PNG_PATH)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img.save(ICNS_PATH)
    print(f"Created {ICNS_PATH}")


if __name__ == "__main__":
    main()
