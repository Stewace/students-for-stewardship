"""
Convert LEC classification and hillshade rasters to Leaflet-compatible
PNG tile pyramids (z/x/y.png) using rasterio + PIL.

No GDAL CLI required — pure Python implementation of XYZ tiling.

Tile scheme: Web Mercator (EPSG:3857), TMS=false (Leaflet default)
Zoom levels: 12–16 for a 15km area at 30m resolution
"""

import math
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.warp import reproject, Resampling, calculate_default_transform
from rasterio.transform import from_bounds

try:
    from PIL import Image
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image

# ---------------------------------------------------------------------------
# Color maps
# ---------------------------------------------------------------------------

LEC_COLORMAP = {
    # class code → (R, G, B)
    1: (198,  40,  40),  # Xeric Ridge — red
    2: (245, 127,  23),  # Dry-Mesic   — orange
    3: ( 85, 139,  47),  # Mesic Slope — green
    4: ( 21, 101, 192),  # Cove/Hollow — blue
    5: (  0, 105,  92),  # Bottomland  — teal
    6: (158, 158, 158),  # Upland Flat — gray
    0: (  0,   0,   0),  # nodata      — black (transparent)
}


def lec_to_rgba(data: np.ndarray, alpha: int = 200) -> np.ndarray:
    """Convert LEC class array to RGBA image array."""
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for code, (r, g, b) in LEC_COLORMAP.items():
        mask = (data == code)
        rgba[mask] = [r, g, b, alpha]
    # Nodata → fully transparent
    nodata_mask = np.isnan(data) | (data < 1) | (data > 6)
    rgba[nodata_mask, 3] = 0
    return rgba


def grayscale_to_rgba(data: np.ndarray, vmin: float = None,
                      vmax: float = None, alpha: int = 180) -> np.ndarray:
    """Convert float array to grayscale RGBA."""
    valid = ~np.isnan(data)
    if vmin is None:
        vmin = data[valid].min() if valid.any() else 0
    if vmax is None:
        vmax = data[valid].max() if valid.any() else 1
    norm = np.clip((data - vmin) / (vmax - vmin + 1e-9), 0, 1)
    gray = (norm * 255).astype(np.uint8)
    rgba = np.stack([gray, gray, gray,
                     np.where(valid, alpha, 0).astype(np.uint8)], axis=-1)
    return rgba


def hillshade_to_rgba(dem: np.ndarray, azimuth: float = 315,
                      altitude: float = 45) -> np.ndarray:
    """Compute hillshade and return RGBA (grayscale with alpha)."""
    az_rad  = math.radians(azimuth)
    alt_rad = math.radians(altitude)
    dy, dx  = np.gradient(dem, 30.0, 30.0)
    slope   = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect  = np.arctan2(-dy, dx)

    hs = (np.sin(alt_rad) * np.cos(slope) +
          np.cos(alt_rad) * np.sin(slope) * np.cos(az_rad - aspect))
    hs = np.clip((hs + 1) / 2, 0, 1)
    gray = (hs * 255).astype(np.uint8)
    alpha = np.full_like(gray, 160)
    return np.stack([gray, gray, gray, alpha], axis=-1)


# ---------------------------------------------------------------------------
# Web Mercator tile math
# ---------------------------------------------------------------------------

TILE_SIZE = 256

def deg2tile(lat_deg: float, lon_deg: float, zoom: int):
    """Convert WGS84 lat/lon to tile x,y at given zoom."""
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def tile_bounds_deg(x: int, y: int, zoom: int):
    """Return (lon_min, lat_min, lon_max, lat_max) for an XYZ tile."""
    n = 2 ** zoom
    lon_min = x / n * 360 - 180
    lon_max = (x + 1) / n * 360 - 180
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1) / n))))
    return lon_min, lat_min, lon_max, lat_max


def tile_bounds_merc(x: int, y: int, zoom: int):
    """Return (xmin, ymin, xmax, ymax) in Web Mercator (m) for a tile."""
    n = 2 ** zoom
    R = 6378137.0  # WGS84 equatorial radius
    half = math.pi * R
    tile_m = 2 * half / n
    xmin = -half + x * tile_m
    xmax = xmin + tile_m
    ymax = half - y * tile_m
    ymin = ymax - tile_m
    return xmin, ymin, xmax, ymax


# ---------------------------------------------------------------------------
# Reproject raster to Web Mercator memory array
# ---------------------------------------------------------------------------

def raster_to_merc(
    src_path: str,
    merc_bounds: tuple,   # (xmin, ymin, xmax, ymax) in EPSG:3857
    out_width: int = None,
    out_height: int = None,
    resampling=Resampling.nearest,
) -> np.ndarray:
    """
    Reproject and crop a raster to Web Mercator, returning a float32 array.
    merc_bounds must fully cover the tile area.
    """
    xmin, ymin, xmax, ymax = merc_bounds
    if out_width is None:
        out_width = TILE_SIZE
    if out_height is None:
        out_height = TILE_SIZE

    dst_crs = CRS.from_epsg(3857)
    dst_transform = from_bounds(xmin, ymin, xmax, ymax, out_width, out_height)

    with rasterio.open(src_path) as src:
        dst_data = np.zeros((out_height, out_width), dtype=np.float32)
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_data,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            resampling=resampling,
            src_nodata=src.nodata,
            dst_nodata=np.nan,
        )
    return dst_data


# ---------------------------------------------------------------------------
# Tile generator
# ---------------------------------------------------------------------------

def get_raster_wgs84_bounds(src_path: str):
    """Return (lon_min, lat_min, lon_max, lat_max) for a raster."""
    from rasterio.warp import transform_bounds
    with rasterio.open(src_path) as src:
        bounds = transform_bounds(src.crs, CRS.from_epsg(4326), *src.bounds)
    return bounds  # (lon_min, lat_min, lon_max, lat_max)


def generate_tiles(
    raster_path: str,
    output_dir: str,
    layer_type: str = "lec",     # "lec" | "hillshade" | "dem"
    zoom_levels: list = None,
    alpha: int = 200,
) -> int:
    """
    Generate a complete XYZ tile pyramid for a raster layer.

    Parameters
    ----------
    raster_path : input GeoTIFF
    output_dir : root directory for tiles/{z}/{x}/{y}.png
    layer_type : colorization mode
    zoom_levels : list of zoom levels to generate
    alpha : tile opacity (0-255)

    Returns total tile count.
    """
    if zoom_levels is None:
        zoom_levels = [12, 13, 14, 15]

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Get raster extent in WGS84
    lon_min, lat_min, lon_max, lat_max = get_raster_wgs84_bounds(raster_path)
    print(f"  Raster bounds: {lon_min:.4f},{lat_min:.4f} → {lon_max:.4f},{lat_max:.4f}")

    total_tiles = 0

    for zoom in zoom_levels:
        # Find tile range covering the raster
        tx_min, ty_max = deg2tile(lat_min, lon_min, zoom)
        tx_max, ty_min = deg2tile(lat_max, lon_max, zoom)

        # Clamp to valid range
        n = 2 ** zoom
        tx_min = max(0, tx_min - 1)
        tx_max = min(n - 1, tx_max + 1)
        ty_min = max(0, ty_min - 1)
        ty_max = min(n - 1, ty_max + 1)

        n_tiles = (tx_max - tx_min + 1) * (ty_max - ty_min + 1)
        print(f"  z={zoom}: tiles [{tx_min},{ty_min}] → [{tx_max},{ty_max}]"
              f"  ({n_tiles} tiles)")

        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                tile_path = out / str(zoom) / str(tx) / f"{ty}.png"
                tile_path.parent.mkdir(parents=True, exist_ok=True)

                merc_bounds = tile_bounds_merc(tx, ty, zoom)
                try:
                    data = raster_to_merc(
                        raster_path, merc_bounds,
                        resampling=(Resampling.nearest if layer_type == "lec"
                                    else Resampling.bilinear),
                    )
                except Exception:
                    # Tile fully outside raster → transparent
                    img = Image.fromarray(np.zeros((TILE_SIZE, TILE_SIZE, 4),
                                                   dtype=np.uint8), "RGBA")
                    img.save(tile_path)
                    continue

                # Colorize
                if layer_type == "lec":
                    rgba = lec_to_rgba(data, alpha=alpha)
                elif layer_type == "hillshade":
                    rgba = grayscale_to_rgba(data, vmin=0, vmax=255, alpha=alpha)
                else:
                    rgba = grayscale_to_rgba(data, alpha=alpha)

                # If entire tile is transparent, save a tiny placeholder
                if rgba[:, :, 3].sum() == 0:
                    img = Image.fromarray(
                        np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8), "RGBA")
                else:
                    img = Image.fromarray(rgba, "RGBA")

                img.save(tile_path, "PNG", optimize=True)
                total_tiles += 1

        print(f"    z={zoom}: {total_tiles} tiles written so far")

    return total_tiles


# ---------------------------------------------------------------------------
# Generate hillshade from DEM (in memory)
# ---------------------------------------------------------------------------

def generate_hillshade_tif(dem_path: str, out_path: str) -> None:
    """Compute hillshade and save as GeoTIFF with same metadata as DEM."""
    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(float)
        profile = src.profile.copy()

    az, alt = 315, 45
    az_r, alt_r = math.radians(az), math.radians(alt)
    dy, dx = np.gradient(dem, 30.0, 30.0)
    slope  = np.arctan(np.sqrt(dx**2 + dy**2))
    aspect = np.arctan2(-dy, dx)
    hs = (np.sin(alt_r) * np.cos(slope) +
          np.cos(alt_r) * np.sin(slope) * np.cos(az_r - aspect))
    hs = np.clip((hs + 1) / 2 * 255, 0, 255).astype(np.float32)

    profile.update(dtype="float32", nodata=-9999)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(hs, 1)
    print(f"  Hillshade → {out_path}  min={hs.min():.0f} max={hs.max():.0f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    project_root = Path(__file__).parent.parent
    terrain_dir = project_root / "data" / "processed" / "terrain"
    lec_dir     = project_root / "data" / "processed" / "lec_classification"
    tiles_dir   = project_root / "map-system" / "stack" / "leaflet" / "tiles"

    print("=" * 60)
    print("Generating Leaflet map tiles")
    print("=" * 60)

    # 1. Hillshade TIF
    print("\n[1/3] Computing hillshade...")
    hs_path = str(terrain_dir / "hillshade.tif")
    generate_hillshade_tif(str(terrain_dir / "dem.tif"), hs_path)

    # 2. LEC classification tiles
    print("\n[2/3] LEC classification tiles...")
    n = generate_tiles(
        raster_path=str(lec_dir / "lec_class.tif"),
        output_dir=str(tiles_dir / "lec_classified"),
        layer_type="lec",
        zoom_levels=[12, 13, 14, 15],
        alpha=210,
    )
    print(f"  Total LEC tiles: {n}")

    # 3. Hillshade tiles
    print("\n[3/3] Hillshade tiles...")
    n2 = generate_tiles(
        raster_path=hs_path,
        output_dir=str(tiles_dir / "hillshade"),
        layer_type="hillshade",
        zoom_levels=[12, 13, 14, 15],
        alpha=160,
    )
    print(f"  Total hillshade tiles: {n2}")

    print(f"\nTiles written to: {tiles_dir}/")
    print("Start map server with:")
    print("  cd map-system/stack/leaflet && python -m http.server 8080")


if __name__ == "__main__":
    main()
