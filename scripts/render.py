#!/usr/bin/env python3
"""Render draft slides to JPEG.

For every drafts/<carousel>/slides/NN.html this writes
drafts/<carousel>/NN.jpg at exactly 1080 x 1350 pixels, using headless
Chrome for the picture and Pillow for the JPEG.

Usage: python3 scripts/render.py [carousel-folder-name ...]
With no names, every folder in drafts/ is rendered.
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "drafts"
WIDTH, HEIGHT = 1080, 1350
# The window is taller than the slide, and the top-left 1080 x 1350 is kept.
# Headless Chrome does not always give the page the full window height.
WINDOW_HEIGHT = HEIGHT + 250


def find_chrome():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("ERROR: Chrome was not found")


def render(chrome, html, jpg):
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "shot.png"
        subprocess.run(
            [
                chrome,
                "--headless=new",
                "--no-sandbox",
                "--disable-gpu",
                "--hide-scrollbars",
                "--force-device-scale-factor=1",
                f"--window-size={WIDTH},{WINDOW_HEIGHT}",
                "--virtual-time-budget=10000",
                f"--user-data-dir={tmp}/profile",
                f"--screenshot={png}",
                html.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        with Image.open(png) as shot:
            if shot.width < WIDTH or shot.height < HEIGHT:
                sys.exit(
                    f"ERROR: {html.name} rendered at {shot.width} x {shot.height}; "
                    f"needs at least {WIDTH} x {HEIGHT}"
                )
            slide = shot.convert("RGB").crop((0, 0, WIDTH, HEIGHT))
            slide.save(jpg, "JPEG", quality=92, subsampling=0, optimize=True)


def main():
    chrome = find_chrome()
    wanted = set(sys.argv[1:])
    folders = sorted(p for p in DRAFTS.iterdir() if p.is_dir()) if DRAFTS.is_dir() else []
    count = 0
    for folder in folders:
        if wanted and folder.name not in wanted:
            continue
        for html in sorted((folder / "slides").glob("*.html")):
            jpg = folder / f"{html.stem}.jpg"
            render(chrome, html, jpg)
            count += 1
            print(f"rendered drafts/{folder.name}/{jpg.name}")
    print(f"{count} slide(s) rendered.")


if __name__ == "__main__":
    main()
