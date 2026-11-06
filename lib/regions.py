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
    # Same frame as the Atlantic seasonal maps. This is the map frame, not the MDR.
    "atlantic": (240.0, -5.0, 358.0, 40.0),
}

# Hurricane Main Development Region. Drawn on Atlantic SST and rainfall maps
# and on the global SST and velocity-potential maps. Not the Atlantic map frame.
MDR_BOUNDS = (280.0, 10.0, 340.0, 20.0)

# (name, region key or None, latitude offset in degrees). A positive offset
# sits above the north edge. A negative offset sits below the south edge.
# Niño 3.4 overlaps Niño 4 in longitude, so its label goes below the box
# instead of sitting beside the Niño 4 label.
_LABELS = (
    ("Niño 4", "nino4", 2.0),
    ("Niño 3.4", "nino34", -2.0),
    ("Niño 3", "nino3", 2.0),
    ("Niño 1+2", "nino12", 2.0),
    ("IOD-W", "iodw", 2.0),
    ("IOD-E", "iode", 2.0),
    ("Atlantic MDR", None, 2.0),
)


def _placed_labels(
    names: tuple[str, ...] | None = None,
) -> list[tuple[str, float, float, str]]:
    """Return text, longitude, latitude, and vertical alignment for each label."""
    placed = []
    for text, key, offset in _LABELS:
        if names is not None and text not in names:
            continue
        if key is None:
            west, south, east, north = MDR_BOUNDS
        else:
            west, south, east, north = REGIONS[key]
        lon = (west + east) / 2.0
        if offset < 0:
            placed.append((text, lon, south + offset, "top"))
        else:
            placed.append((text, lon, north + offset, "bottom"))
    return placed


def region_label_anchors(names: tuple[str, ...] | None = None) -> list[tuple[str, float, float]]:
    """Geographic points for labels centered on each box.

    Most labels sit above the north edge. Niño 3.4 sits below its south edge.
    """
    return [(text, lon, lat) for text, lon, lat, _align in _placed_labels(names)]


def add_mdr_outline(ax, linewidth: float = 3):
    """Draw the Main Development Region. The caller chooses the map extent."""
    import cartopy.crs as ccrs
    from cartopy.feature import ShapelyFeature
    from shapely.geometry import box

    west, south, east, north = MDR_BOUNDS
    feature = ShapelyFeature(
        [box(west, south, east, north)],
        ccrs.PlateCarree(),
        facecolor="none",
        edgecolor="k",
    )
    ax.add_feature(feature, linewidth=linewidth, zorder=22)
    return feature


def draw_region_labels(ax, names: tuple[str, ...] | None = None, fontsize: float = 18) -> None:
    """Label climate regions in geographic coordinates.

    Pass names=("Atlantic MDR",) on the Atlantic SST and rainfall maps. The
    default set is the global SST and velocity-potential set. There is no
    separate "3.4" or "12" token: Niño 4 names the Niño 4 box, and Niño 1+2
    is one label. Niño 3.4 is drawn below its box.
    """
    import cartopy.crs as ccrs

    for text, lon, lat, align in _placed_labels(names):
        ax.text(
            lon,
            lat,
            text,
            horizontalalignment="center",
            verticalalignment=align,
            transform=ccrs.PlateCarree(),
            color="white",
            weight="bold",
            fontsize=fontsize,
            zorder=30,
            clip_on=True,
            bbox=dict(
                facecolor="#000000",
                alpha=0.5,
                edgecolor="black",
                boxstyle="square",
                pad=0.1,
            ),
        )


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
    """Write one dBASE III record. pyshp expects the 0x0D terminator at byte 64."""
    value = name.encode("ascii")[:32].ljust(32)
    field = bytearray(32)
    field[0:4] = b"NAME"
    field[11:12] = b"C"
    field[16] = 32
    header = bytearray(32)
    header[0] = 0x03
    header[1:4] = bytes((26, 10, 29))
    header[4:8] = struct.pack("<I", 1)
    header[8:10] = struct.pack("<H", 65)
    header[10:12] = struct.pack("<H", 33)
    record = b" " + value
    path.write_bytes(bytes(header) + bytes(field) + b"\r" + record)


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
