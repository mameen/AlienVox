"""Generate placeholder tray icon PNGs (32x32).

Run once: python -m src.resources.icons.generate
Outputs: idle.png, speaking.png, error.png in this directory.

These are intentionally minimal geometric placeholders; replace with
real icon assets before shipping.
"""
import pathlib
import struct
import zlib

_DIR = pathlib.Path(__file__).parent


def _png(pixels_rgba: list[tuple[int, int, int, int]], size: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for y in range(size):
        raw += b"\x00"
        for x in range(size):
            r, g, b, a = pixels_rgba[y * size + x]
            raw += bytes([r, g, b, a])

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def _circle_pixels(r: int, g: int, b: int, size: int = 32) -> list[tuple[int, int, int, int]]:
    cx = cy = size / 2
    radius = size / 2 - 2
    pixels = []
    for y in range(size):
        for x in range(size):
            dist = ((x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2) ** 0.5
            a = 255 if dist <= radius else 0
            pixels.append((r, g, b, a))
    return pixels


def generate() -> None:
    icons = {
        "idle.png":     _circle_pixels(80, 80, 200),   # muted blue
        "speaking.png": _circle_pixels(60, 180, 80),   # green
        "error.png":    _circle_pixels(200, 60, 60),   # red
    }
    for name, pixels in icons.items():
        (_DIR / name).write_bytes(_png(pixels, 32))
        print(f"  wrote {name}")


if __name__ == "__main__":
    generate()
