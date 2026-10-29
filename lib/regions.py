#!/usr/bin/env python3
"""Write the public climate-region outlines used on the seasonal maps.

The boxes are the published Niño, IOD, and shared Atlantic domains. Nothing
here comes from a private shapefile. Longitudes are 0..360, matching the maps.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

# west, south, east, north
REGIONS: dict[str, tuple[float, float, float, float]] = {
    "nino12": (270.0, -10.0, 280.0, 0.0),
    "nino3": (210.0, -5.0, 270.0, 5.0),
    "nino34": (190.0, -5.0, 240.0, 5.0),
    "nino4": (160.0, -5.0, 210.0, 5.0),
    "iodw": (50.0, -10.0, 70.0, 10.0),
    "iode": (90.0, -10.0, 110.0, 0.0),
    # Same frame as the Atlantic seasonal maps.
    "atlantic": (240.0, -5.0, 358.0, 40.0),
}


def _box_ring(west: float, south: float, east: float, north: float) -> list[tuple[float, float]]:
    return [
        (west, south),
        (east, south),
        (east, north),
        (west, north),
        (west, south),
    ]


def _write_shp(path: Path, ring: list[tuple[float, float]]) -> None:
    xs = [point[0] for point in ring]
    ys = [point[1] for point in ring]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    content = struct.pack("<i", 5)
    content += struct.pack("<4d", *bbox)
    content += struct.pack("<2i", 1, len(ring))
    content += struct.pack("<i", 0)
    for x_coord, y_coord in ring:
        content += struct.pack("<2d", x_coord, y_coord)
    record_number = 1
    content_words = len(content) // 2
    record = struct.pack(">2i", record_number, content_words) + content

    file_words = (100 + len(record)) // 2
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, file_words)
    header += struct.pack("<2i", 1000, 5)
    header += struct.pack("<8d", bbox[0], bbox[1], bbox[2], bbox[3], 0, 0, 0, 0)
    path.write_bytes(header + record)


def _write_shx(path: Path, shp_path: Path) -> None:
    content_size = shp_path.stat().st_size - 100
    header = struct.pack(">7i", 9994, 0, 0, 0, 0, 0, (100 + 8) // 2)
    header += struct.pack("<2i", 1000, 5)
    header += struct.pack("<8d", 0, 0, 0, 0, 0, 0, 0, 0)
    # Offset of the first record, in 16-bit words. The shapefile header is 50 words.
    record = struct.pack(">2i", 50, content_size // 2)
    path.write_bytes(header + record)


def _write_dbf(path: Path, name: str) -> None:
    field = b"NAME" + b"\x00" * 7 + b"C" + struct.pack("<I", 1) + struct.pack("<B", 32) + b"\x00" * 15
    header = bytearray(32)
    header[0] = 3
    header[8:10] = struct.pack("<H", 1)
    header[10:12] = struct.pack("<H", 32 + 32 + 1)
    header[12:14] = struct.pack("<H", 33)
    body = b" " + name.encode("ascii")[:32].ljust(32) + b"\x1a"
    path.write_bytes(bytes(header) + field + b"\r" + body)


def write_regions(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, bounds in REGIONS.items():
        folder = out_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        shp_path = folder / f"{name}.shp"
        _write_shp(shp_path, _box_ring(*bounds))
        _write_shx(folder / f"{name}.shx", shp_path)
        _write_dbf(folder / f"{name}.dbf", name)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write public climate-region shapefiles.")
    parser.add_argument("--out", required=True, help="Directory that will contain one folder per region.")
    args = parser.parse_args()
    write_regions(Path(args.out))
    print(f"Wrote {len(REGIONS)} region outlines to {args.out}")


if __name__ == "__main__":
    main()
