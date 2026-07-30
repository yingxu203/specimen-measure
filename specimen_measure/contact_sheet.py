"""Combine a folder of overlay PNGs into a single scrollable PDF, so you can
review a whole batch by scrolling through one file instead of opening each
image individually.
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HEADER_HEIGHT = 28


def build_overlay_pdf(overlay_paths: list[Path], output_pdf: Path) -> None:
    if not overlay_paths:
        raise ValueError("No overlay images to combine.")

    pages = []
    for path in sorted(overlay_paths):
        img = Image.open(path).convert("RGB")
        page = Image.new("RGB", (img.width, img.height + HEADER_HEIGHT), (255, 255, 255))
        ImageDraw.Draw(page).text((6, 6), path.stem, fill=(0, 0, 0))
        page.paste(img, (0, HEADER_HEIGHT))
        pages.append(page)

    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(output_pdf, save_all=True, append_images=pages[1:])
