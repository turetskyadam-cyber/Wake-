#!/usr/bin/env python3
"""Generate WAKE PWA icons from Untitled_design.png — white background, as-is."""

from PIL import Image
import os

SRC = "/root/.claude/uploads/0d4249be-1ccc-5233-bb8d-77926d7591b1/d43f1813-Untitled_design.png"

os.makedirs("icons", exist_ok=True)
src = Image.open(SRC).convert("RGBA")

sizes = [
    (512, "icons/icon-512.png"),
    (192, "icons/icon-192.png"),
    (180, "icons/apple-touch-icon.png"),
    (32,  "icons/favicon-32.png"),
]

for size, path in sizes:
    img = src.resize((size, size), Image.LANCZOS)
    img.save(path, "PNG", optimize=True)
    print(f"  {size:>4}px → {path}  ({os.path.getsize(path)//1024}KB)")

print("Done.")
