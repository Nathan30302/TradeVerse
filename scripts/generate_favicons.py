#!/usr/bin/env python3
"""
Generate simple TradeVerse favicon PNGs without external dependencies.

Writes:
- app/static/img/favicon-48.png
- app/static/img/favicon-192.png
- app/static/img/favicon-512.png
- app/static/img/favicon.png (alias of 192)
"""

from __future__ import annotations

import os
import struct
import zlib
from typing import List, Tuple


def _png_pack(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def write_png(path: str, w: int, h: int, rgba: List[Tuple[int, int, int, int]]) -> None:
    if len(rgba) != w * h:
        raise ValueError("rgba length mismatch")

    # Build raw scanlines (filter byte 0 per row)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = rgba[y * w : (y + 1) * w]
        for r, g, b, a in row:
            raw.extend(bytes((r & 255, g & 255, b & 255, a & 255)))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8-bit RGBA
    data = b"\x89PNG\r\n\x1a\n" + _png_pack(b"IHDR", ihdr)
    data += _png_pack(b"IDAT", zlib.compress(bytes(raw), level=9))
    data += _png_pack(b"IEND", b"")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def draw_tv_icon(size: int) -> List[Tuple[int, int, int, int]]:
    """Return RGBA pixels for a minimal TV monogram."""
    bg = (15, 23, 42, 255)  # #0f172a
    fg = (248, 250, 252, 255)  # near-white
    accent = (34, 211, 238, 255)  # cyan

    w = h = size
    px: List[Tuple[int, int, int, int]] = [bg] * (w * h)

    def rect(x0: int, y0: int, x1: int, y1: int, c: Tuple[int, int, int, int]) -> None:
        x0c, y0c = max(0, x0), max(0, y0)
        x1c, y1c = min(w, x1), min(h, y1)
        for yy in range(y0c, y1c):
            base = yy * w
            for xx in range(x0c, x1c):
                px[base + xx] = c

    # Simple geometry based on size
    m = size // 8  # margin
    stroke = max(2, size // 24)

    # "T"
    t_x0 = m
    t_x1 = size // 2 + stroke
    t_y0 = m
    t_y1 = size - m
    rect(t_x0, t_y0, t_x1, t_y0 + stroke * 2, fg)  # top bar
    rect((t_x0 + t_x1) // 2 - stroke, t_y0, (t_x0 + t_x1) // 2 + stroke, t_y1 - m, fg)  # stem

    # "V"
    v_x0 = size // 2 - stroke
    v_x1 = size - m
    v_y0 = m
    v_y1 = size - m
    # Draw two diagonal-ish legs using thin rectangles in steps (cheap and readable at small sizes)
    steps = size // 10
    for i in range(steps + 1):
        # left leg
        lx = v_x0 + (i * (size // 6)) // max(1, steps)
        ly = v_y0 + (i * (v_y1 - v_y0)) // max(1, steps)
        rect(lx, ly, lx + stroke, ly + stroke * 2, fg)
        # right leg
        rx = v_x1 - (i * (size // 6)) // max(1, steps) - stroke
        ry = v_y0 + (i * (v_y1 - v_y0)) // max(1, steps)
        rect(rx, ry, rx + stroke, ry + stroke * 2, fg)

    # Accent "chart up" line in the lower-right
    ax0 = size - m - size // 3
    ay0 = size - m - size // 3
    rect(ax0, ay0 + stroke * 3, ax0 + stroke, ay0 + stroke * 8, accent)
    rect(ax0 + stroke, ay0 + stroke * 6, ax0 + stroke * 5, ay0 + stroke * 7, accent)
    rect(ax0 + stroke * 5, ay0 + stroke * 2, ax0 + stroke * 6, ay0 + stroke * 7, accent)

    return px


def main() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(root, "app", "static", "img")
    for sz in (48, 192, 512):
        p = os.path.join(out_dir, f"favicon-{sz}.png")
        write_png(p, sz, sz, draw_tv_icon(sz))

    # Alias expected path(s)
    # base.html and manifest currently reference /static/img/favicon.png
    alias = os.path.join(out_dir, "favicon.png")
    write_png(alias, 192, 192, draw_tv_icon(192))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

