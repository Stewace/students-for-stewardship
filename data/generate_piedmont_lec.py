"""
Generate LEC classification for the full Piedmont Ecoregion (EPA Level III, Region 45).

Resolution: 0.005° (~500 m at 36°N)
CRS: EPSG:4326 (WGS84)
Extent: -86.5 to -76.5 lon, 32.5 to 39.5 lat

Outputs:
  data/processed/piedmont/dem.tif
  data/processed/piedmont/lec_class.tif
  docs/tiles/piedmont_lec/{z}/{x}/{y}.png   (zoom 8–11)
"""

import math
import sys
from pathlib import Path

import numpy as np
from scipy.ndimage import uniform_filter, gaussian_filter

sys.path.insert(0, str(Path(__file__).parent.parent))

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import reproject, Resampling, calculate_default_transform, transform_bounds

try:
    from PIL import Image
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "Pillow", "-q"])
    from PIL import Image

# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------
LON_MIN, LON_MAX = -86.5, -76.5
LAT_MIN, LAT_MAX = 32.5, 39.5
RES = 0.005          # degrees per pixel (~500 m)
COLS = int((LON_MAX - LON_MIN) / RES)   # 2000
ROWS = int((LAT_MAX - LAT_MIN) / RES)   # 1400
CELL_M = 500.0       # approximate cell size in meters (used for gradients)

OUT_DIR = Path("data/processed/piedmont")
TILE_DIR = Path("docs/tiles/piedmont_lec")

LEC_COLORMAP = {
    1: (198,  40,  40),   # Xeric Ridge
    2: (245, 127,  23),   # Dry-Mesic Slope
    3: ( 85, 139,  47),   # Mesic Slope
    4: ( 21, 101, 192),   # Cove/Hollow
    5: (  0, 105,  92),   # Bottomland
    6: (158, 158, 158),   # Upland Flat
}

# ---------------------------------------------------------------------------
# 1. Generate Piedmont DEM
# ---------------------------------------------------------------------------

def make_piedmont_dem(seed: int = 42) -> np.ndarray:
    """
    Synthetic Piedmont DEM calibrated to EPA Region 45 terrain characteristics.

    Key traits:
    - Elevation: 60-400 m (decreasing W→E from Blue Ridge foothills to Fall Line)
    - NE-SW Appalachian structural grain (ridge orientation ~45°)
    - Ridge spacing: 4-12 km for major ridges
    - Local relief: 20-60 m on hillslopes
    - Dissection increases in the west near Blue Ridge
    - Major river valleys crossing E-W: Roanoke, Dan, Yadkin, Catawba, Broad
    """
    rng = np.random.default_rng(seed)

    # Physical coordinate grids in approximate meters from SW corner
    x = np.linspace(0, COLS * CELL_M, COLS)   # W→E, 0–1,000,000 m
    y = np.linspace(0, ROWS * CELL_M, ROWS)   # S→N, 0–700,000 m
    xx, yy = np.meshgrid(x, y[::-1])          # row 0 = north

    # Lon/lat grids (for geographic features)
    lons = np.linspace(LON_MIN, LON_MAX, COLS)
    lats = np.linspace(LAT_MAX, LAT_MIN, ROWS)   # north-down
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    # --- Elevation gradient: Blue Ridge (W) to Fall Line (E) ---
    # Normalized W→E: 0 = west (high), 1 = east (low)
    lon_frac = (lon_grid - LON_MIN) / (LON_MAX - LON_MIN)
    elev_base = 340 - 280 * lon_frac   # 340 m in W, 60 m in E

    # --- NE-SW ridge structure ---
    ridge_across = (xx + yy) / math.sqrt(2)   # distance across ridges (NW-SE direction)
    ridge_along  = (xx - yy) / math.sqrt(2)   # distance along ridges  (NE-SW direction)

    f_major = 2 * math.pi / (8000 * CELL_M / 500)    # major ridges ~8 km
    f_minor = 2 * math.pi / (3500 * CELL_M / 500)    # minor ridges ~3.5 km
    f_micro = 2 * math.pi / (1400 * CELL_M / 500)    # micro-relief ~1.4 km
    f_along = 2 * math.pi / (12000 * CELL_M / 500)   # along-strike undulation

    # Ridge amplitude decreases east (Piedmont peneplain flattens toward coast)
    amp = 28 + 18 * (1 - lon_frac)

    dem = (
        elev_base
        + amp        * np.sin(f_major * ridge_across)
        + amp * 0.5  * np.sin(f_minor * ridge_across + 1.4)
        + amp * 0.18 * np.sin(f_micro * ridge_across + 0.9)
        + 6.0        * np.sin(f_along * ridge_along  + 0.3)
        + rng.normal(0, 2.5, (ROWS, COLS))
    )

    # --- Major river valleys (approximate centerlines in lon/lat) ---
    # Each entry: (lat_center, lat_slope_per_lon, depth_m, half_width_m)
    # Valley runs roughly E-W with slight tilt
    rivers = [
        # Roanoke R. ~36.7°N, flows E across VA Piedmont
        dict(lat0=36.7,  dlat_dlon=0.03,  depth=22, width=0.12),
        # Dan R. ~36.4°N, NC/VA border
        dict(lat0=36.4,  dlat_dlon=0.02,  depth=18, width=0.10),
        # Yadkin-PeeDee R. ~35.8°N through NC Piedmont
        dict(lat0=35.85, dlat_dlon=-0.01, depth=20, width=0.11),
        # Catawba R. ~35.3°N, NC/SC
        dict(lat0=35.3,  dlat_dlon=-0.04, depth=24, width=0.13),
        # Broad R. ~34.9°N, SC
        dict(lat0=34.9,  dlat_dlon=-0.06, depth=20, width=0.10),
        # Savannah / upper drainage ~34.2°N, GA/SC
        dict(lat0=34.2,  dlat_dlon=-0.02, depth=18, width=0.09),
        # James R. ~37.3°N, central VA
        dict(lat0=37.3,  dlat_dlon=0.05,  depth=20, width=0.11),
        # Appomattox ~37.1°N, VA
        dict(lat0=37.1,  dlat_dlon=0.04,  depth=14, width=0.08),
        # Rappahannock ~38.2°N, N Virginia
        dict(lat0=38.2,  dlat_dlon=0.06,  depth=16, width=0.09),
    ]

    for r in rivers:
        # Valley centerline: lat = lat0 + dlat_dlon * (lon - lon_mid)
        lon_mid = (LON_MIN + LON_MAX) / 2
        lat_center = r['lat0'] + r['dlat_dlon'] * (lon_grid - lon_mid)
        dist_deg = lat_grid - lat_center           # signed lat distance from valley center
        dist_m   = dist_deg * 111000               # convert to meters
        w = r['width'] * 111000                    # half-width in meters
        # Broad floodplain + narrow inner channel
        dem -= r['depth']       * np.exp(-(dist_m**2) / (w**2))
        dem -= r['depth'] * 0.4 * np.exp(-(dist_m**2) / ((w * 0.2)**2))

    # Light smoothing to remove aliasing
    dem = gaussian_filter(dem, sigma=0.7)
    dem = np.clip(dem, 40.0, 450.0)
    return dem.astype("float32")


# ---------------------------------------------------------------------------
# 2. Terrain indices (WGS84 grid, approximate metric distances)
# ---------------------------------------------------------------------------

def compute_slope(dem: np.ndarray, cell_m: float = CELL_M) -> np.ndarray:
    """Horn (1981) slope in degrees."""
    dz_dx = np.zeros_like(dem)
    dz_dy = np.zeros_like(dem)
    dz_dx[1:-1, 1:-1] = (
        (dem[0:-2, 2:] + 2*dem[1:-1, 2:] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[1:-1, 0:-2] + dem[2:, 0:-2])
    ) / (8 * cell_m)
    dz_dy[1:-1, 1:-1] = (
        (dem[2:, 0:-2] + 2*dem[2:, 1:-1] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[0:-2, 1:-1] + dem[0:-2, 2:])
    ) / (8 * cell_m)
    return np.degrees(np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))).astype("float32")


def compute_aspect(dem: np.ndarray, cell_m: float = CELL_M) -> np.ndarray:
    dz_dx = np.zeros_like(dem)
    dz_dy = np.zeros_like(dem)
    dz_dx[1:-1, 1:-1] = (
        (dem[0:-2, 2:] + 2*dem[1:-1, 2:] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[1:-1, 0:-2] + dem[2:, 0:-2])
    ) / (8 * cell_m)
    dz_dy[1:-1, 1:-1] = (
        (dem[2:, 0:-2] + 2*dem[2:, 1:-1] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[0:-2, 1:-1] + dem[0:-2, 2:])
    ) / (8 * cell_m)
    return (np.degrees(np.arctan2(-dz_dy, dz_dx)) % 360).astype("float32")


def compute_tsi(dem: np.ndarray) -> np.ndarray:
    ns = (np.roll(dem,  1, 0) + np.roll(dem, -1, 0) +
          np.roll(dem,  1, 1) + np.roll(dem, -1, 1) +
          np.roll(dem, (1,  1), (0,1)) + np.roll(dem, (-1,-1), (0,1)) +
          np.roll(dem, (1, -1), (0,1)) + np.roll(dem, (-1, 1), (0,1)))
    tsi = ns / 8.0 - dem
    tsi[0,:] = tsi[-1,:] = tsi[:,0] = tsi[:,-1] = 0
    return tsi.astype("float32")


def compute_twi(dem: np.ndarray, slope_deg: np.ndarray, cell_m: float = CELL_M) -> np.ndarray:
    local_mean = uniform_filter(dem, size=5)   # smaller window at 500m (~2.5km)
    area = cell_m * (1.0 + np.maximum(local_mean - dem, 0) * 0.4)
    slope_rad = np.deg2rad(np.maximum(slope_deg, 0.5))
    twi = np.log(area / np.tan(slope_rad))
    return np.clip(twi, 2.0, 16.0).astype("float32")


def compute_soil_proxy(dem, tsi, slope_deg, seed=7):
    """Terrain-derived soil proxies for Piedmont residual soils."""
    rng = np.random.default_rng(seed)
    en = (dem - dem.min()) / (dem.max() - dem.min() + 1e-6)
    tn = (tsi - tsi.min()) / (tsi.max() - tsi.min() + 1e-6)
    clay_d = np.clip(70 - 40*en + 50*tn + rng.normal(0,10,dem.shape), 10, 200).astype("float32")
    clay_p = np.clip(20 -  7*en + 12*tn + rng.normal(0, 4,dem.shape),  8,  55).astype("float32")
    drain  = np.clip( 5 - 3*tn  - 0.6*(1-en) + rng.normal(0,0.4,dem.shape), 1, 7).astype("float32")
    return clay_d, clay_p, drain


# ---------------------------------------------------------------------------
# 3. LEC classification — percentile-based, scale-invariant
# ---------------------------------------------------------------------------

def lec_classify_regional(slope, aspect, tsi, twi, dem) -> np.ndarray:
    """
    Scale-invariant LEC classification based on relative terrain position.

    At 500m resolution absolute slope values are ~6× lower than at 30m, so
    the LDA model (calibrated on 30m data) cannot distinguish classes.
    Instead we use percentile ranks — ecologically valid because LEC classes
    are fundamentally about *relative* landscape position.

    Priority (highest overwrites lowest):
        6 Upland Flat  → low slope, moderate terrain (default)
        3 Mesic Slope  → moderate slope, moderate concavity, mesic aspect
        2 Dry-Mesic    → moderate slope, convex, xeric aspect
        4 Cove/Hollow  → concave, high TWI, any slope
        5 Bottomland   → very low slope, very high TWI (valley floors)
        1 Xeric Ridge  → high slope, convex, high elevation
    """
    from scipy.stats import rankdata

    rows, cols = slope.shape
    n = rows * cols

    def pct(arr):
        return rankdata(arr.ravel(), method='average').reshape(rows, cols) / n

    sp = pct(slope)   # high = steeper
    tp = pct(tsi)     # high = more concave (cove/hollow), low = convex (ridge)
    wp = pct(twi)     # high = wetter / more flow accumulation
    ep = pct(dem)     # high = higher elevation

    # Folded aspect (Beers 1966): 0° = SW (xeric), 180° = NE (mesic)
    fa = np.abs(180.0 - np.abs(aspect - 225.0))
    fa_p = pct(fa)    # high = mesic (N/NE-facing)

    lec = np.full((rows, cols), 6, dtype=np.float32)   # default: Upland Flat

    # 3. Mesic Slope: sloped, moderate concavity, mesic/N-facing
    lec[(sp > 0.35) & (sp < 0.80) & (tp > 0.35) & (fa_p > 0.50)] = 3

    # 2. Dry-Mesic Slope: moderate slope, slightly convex, xeric aspect
    lec[(sp > 0.40) & (sp < 0.82) & (tp > 0.20) & (tp < 0.55) & (fa_p < 0.50)] = 2

    # 4. Cove/Hollow: concave terrain, high moisture accumulation
    lec[(tp > 0.65) & (wp > 0.55) & (sp > 0.12) & (sp < 0.78)] = 4

    # 5. Bottomland: valley floors — very low slope, very high TWI
    lec[(wp > 0.93) & (sp < 0.18)] = 5

    # 1. Xeric Ridge: high elevation, convex, steepest terrain
    lec[(sp > 0.74) & (tp < 0.28) & (ep > 0.58)] = 1

    return lec


# ---------------------------------------------------------------------------
# 4. Write GeoTIFF (WGS84)
# ---------------------------------------------------------------------------

def write_tif(path: str, data: np.ndarray) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    transform = from_origin(LON_MIN, LAT_MAX, RES, RES)
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": COLS, "height": ROWS,
        "count": 1, "crs": CRS.from_epsg(4326), "transform": transform,
        "nodata": -9999.0, "compress": "lzw",
    }
    with rasterio.open(str(path), "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)
    print(f"  {path}  shape={data.shape}  min={data.min():.1f} max={data.max():.1f}")


# ---------------------------------------------------------------------------
# 5. Tile generation (fast: precompute Mercator raster per zoom)
# ---------------------------------------------------------------------------

TILE_SIZE = 256

def deg2tile(lat_deg, lon_deg, zoom):
    lat_r = math.radians(lat_deg)
    n = 2 ** zoom
    x = int((lon_deg + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_r) + 1 / math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y


def tile_bounds_merc(x, y, zoom):
    n = 2 ** zoom
    R = 6378137.0
    half = math.pi * R
    tile_m = 2 * half / n
    xmin = -half + x * tile_m
    xmax = xmin + tile_m
    ymax = half - y * tile_m
    ymin = ymax - tile_m
    return xmin, ymin, xmax, ymax


def lec_to_rgba(data, alpha=210):
    h, w = data.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    for code, (r, g, b) in LEC_COLORMAP.items():
        mask = (data == code)
        rgba[mask] = [r, g, b, alpha]
    nodata = np.isnan(data) | (data < 1) | (data > 6)
    rgba[nodata, 3] = 0
    return rgba


def generate_tiles(lec_path: str, out_dir: str, zoom_levels=(8, 9, 10, 11), alpha=210):
    """Generate XYZ tile pyramid from a WGS84 GeoTIFF."""
    from rasterio.transform import from_bounds as fb

    out = Path(out_dir)
    dst_crs = CRS.from_epsg(3857)

    total = 0
    for zoom in zoom_levels:
        tx_min, ty_max = deg2tile(LAT_MIN, LON_MIN, zoom)
        tx_max, ty_min = deg2tile(LAT_MAX, LON_MAX, zoom)
        n = 2 ** zoom
        tx_min = max(0, tx_min - 1)
        tx_max = min(n - 1, tx_max + 1)
        ty_min = max(0, ty_min - 1)
        ty_max = min(n - 1, ty_max + 1)
        n_tiles = (tx_max - tx_min + 1) * (ty_max - ty_min + 1)
        print(f"  z={zoom}: {n_tiles} tiles", flush=True)

        with rasterio.open(lec_path) as src:
            for tx in range(tx_min, tx_max + 1):
                for ty in range(ty_min, ty_max + 1):
                    xmin, ymin, xmax, ymax = tile_bounds_merc(tx, ty, zoom)
                    dst_transform = fb(xmin, ymin, xmax, ymax, TILE_SIZE, TILE_SIZE)
                    dst_data = np.full((TILE_SIZE, TILE_SIZE), np.nan, dtype=np.float32)
                    try:
                        reproject(
                            source=rasterio.band(src, 1),
                            destination=dst_data,
                            src_transform=src.transform,
                            src_crs=src.crs,
                            dst_transform=dst_transform,
                            dst_crs=dst_crs,
                            resampling=Resampling.nearest,
                            src_nodata=src.nodata,
                            dst_nodata=np.nan,
                        )
                    except Exception:
                        pass

                    rgba = lec_to_rgba(dst_data, alpha=alpha)
                    tile_path = out / str(zoom) / str(tx) / f"{ty}.png"
                    tile_path.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(rgba, "RGBA").save(tile_path, "PNG", optimize=True)
                    total += 1

        print(f"    z={zoom}: {total} tiles written so far")

    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Piedmont LEC Classification — EPA Region 45")
    print(f"  Grid: {ROWS}×{COLS} @ {RES}° (~{CELL_M:.0f}m)")
    print(f"  Extent: {LON_MIN}–{LON_MAX}°W, {LAT_MIN}–{LAT_MAX}°N")
    print("=" * 60)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\n[1/4] Generating Piedmont DEM...")
    dem = make_piedmont_dem()
    write_tif(str(OUT_DIR / "dem.tif"), dem)

    print("\n[2/4] Terrain indices...")
    slope  = compute_slope(dem)
    aspect = compute_aspect(dem)
    tsi    = compute_tsi(dem)
    twi    = compute_twi(dem, slope)
    print(f"  slope: {slope.min():.1f}–{slope.max():.1f}°")
    print(f"  twi:   {twi.min():.2f}–{twi.max():.2f}")

    print("\n[3/4] LEC classification (percentile-based, scale-invariant)...")
    lec = lec_classify_regional(slope, aspect, tsi, twi, dem)
    write_tif(str(OUT_DIR / "lec_class.tif"), lec)

    unique, counts = np.unique(lec[lec > 0].astype(int), return_counts=True)
    labels = {1:"Xeric Ridge", 2:"Dry-Mesic", 3:"Mesic", 4:"Cove/Hollow", 5:"Bottomland", 6:"Upland Flat"}
    total_px = counts.sum()
    for u, c in zip(unique, counts):
        print(f"  Class {u} {labels.get(u,'?'):15s}: {c:7d} px  ({100*c/total_px:.1f}%)")

    print("\n[4/4] Generating tiles (zoom 8–11)...")
    lec_path = str(OUT_DIR / "lec_class.tif")
    n = generate_tiles(lec_path, str(TILE_DIR), zoom_levels=[8, 9, 10, 11], alpha=215)
    print(f"\n  Total tiles: {n}")
    print(f"  Tiles → {TILE_DIR}/")


if __name__ == "__main__":
    main()
