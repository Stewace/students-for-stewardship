"""
Generate realistic synthetic DEM for Pickens County, SC Piedmont area.
Runs entirely offline — no external downloads needed.

Outputs GeoTIFFs with real-world coordinates (UTM Zone 17N, EPSG:32617)
centered on the Hunnicutt Creek watershed area.

Then derives all terrain rasters and runs LEC classification.
"""

import sys
import math
from pathlib import Path
import numpy as np
from scipy.ndimage import uniform_filter, gaussian_filter

PROJECT_ROOT = str(Path(__file__).parent.parent)
sys.path.insert(0, PROJECT_ROOT)

import rasterio
from rasterio.transform import from_origin
from rasterio.crs import CRS

# ---------------------------------------------------------------------------
# Geographic parameters — Pickens County, SC
# ---------------------------------------------------------------------------
# UTM Zone 17N (EPSG:32617)
# Hunnicutt Creek watershed area
PIXEL_SIZE   = 30.0          # 30 m — matches 3DEP 1 arc-second
ROWS         = 512
COLS         = 512
# UTM origin (upper-left corner): ~34.78°N, 82.82°W
ORIGIN_E     = 311_000.0     # easting (m)
ORIGIN_N     = 3_854_000.0   # northing (m)
CRS_UTM      = CRS.from_epsg(32617)
LATITUDE_DEG = 34.85         # center latitude (for HLI calculation)

OUT_DIR = Path("data/processed")


def write_tif(path: str, data: np.ndarray, nodata: float = -9999.0) -> None:
    transform = from_origin(ORIGIN_E, ORIGIN_N, PIXEL_SIZE, PIXEL_SIZE)
    profile = {
        "driver": "GTiff", "dtype": "float32", "width": COLS, "height": ROWS,
        "count": 1, "crs": CRS_UTM, "transform": transform,
        "nodata": nodata, "compress": "lzw",
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data.astype("float32"), 1)
    print(f"  Wrote {path}  shape={data.shape}  "
          f"min={data.min():.1f} max={data.max():.1f}")


# ---------------------------------------------------------------------------
# 1. Synthetic Piedmont DEM
# ---------------------------------------------------------------------------

def make_piedmont_dem(seed: int = 7) -> np.ndarray:
    """
    Generate a geomorphically realistic Piedmont DEM.

    Piedmont characteristics (Pickens Co. SC):
      - Elevation: 220-380 m (gentle ridges, not mountainous)
      - NE-SW trending ridges (Appalachian structural grain)
      - Ridge spacing: 600-1200 m  ← key constraint
      - Hillslope relief: 30-70 m over 300-600 m horizontal
      - Slopes: 10-25° on hillsides, <3° on valley floors
      - Perennial streams cutting narrow V-shaped valleys
      - Broader bottomlands along Hunnicutt Creek trunk

    Spatial frequency math:
      Grid = 512 cells × 30 m = 15,360 m
      For 800 m ridge spacing: f = 15360/800 = 19.2 cycles across grid
      In xx space [0, 2π]: frequency multiplier = 19.2/(2π) × 2π = 19.2
      Ridge axis = xx×cos(45°) + yy×sin(45°) = (xx+yy)/√2
    """
    rng = np.random.default_rng(seed)
    # Physical coordinates in meters
    x = np.linspace(0, COLS * PIXEL_SIZE, COLS)   # 0–15360 m
    y = np.linspace(0, ROWS * PIXEL_SIZE, ROWS)
    xx, yy = np.meshgrid(x, y)

    # Spatial frequencies for Piedmont ridge spacing
    # Convert cycles/m to argument for sin: freq_rad = 2π / wavelength_m
    f1 = 2 * np.pi / 900    # major ridges  ~900 m spacing
    f2 = 2 * np.pi / 450    # secondary     ~450 m spacing
    f3 = 2 * np.pi / 220    # minor         ~220 m spacing
    f4 = 2 * np.pi / 110    # micro-relief  ~110 m spacing

    # NE-SW ridge axis (rotated 45°) and along-strike axis
    ridge = (xx + yy) / math.sqrt(2)   # distance along NW-SE (across ridges)
    strike = (xx - yy) / math.sqrt(2)  # distance along NE-SW (along ridges)

    dem = (
        300.0                                           # base elevation (m)
        + 38.0 * np.sin(f1 * ridge)                    # major ridges, ±38m relief
        + 20.0 * np.sin(f2 * ridge + 1.1)              # secondary ridges
        +  9.0 * np.sin(f3 * ridge + 0.6)              # minor ridges
        +  4.0 * np.sin(f4 * ridge + 2.0)              # micro-topography
        +  8.0 * np.sin(f2 * strike + 0.3)             # along-ridge variation
        +  3.0 * np.sin(f3 * strike + 1.8)
        + rng.normal(0, 1.5, (ROWS, COLS))             # stochastic noise
    )

    # Main valley: Hunnicutt Creek draining NE → SW
    # Valley axis runs diagonally (y = x + offset, in meters)
    valley_axis_m = 6000    # offset from lower-left corner
    dist_main = (xx - yy - valley_axis_m) / math.sqrt(2)   # signed dist to valley
    # Broad valley floor (floodplain) + steep inner walls
    dem -= 35.0 * np.exp(-(dist_main**2) / (400**2))    # main incision, 400m half-width
    dem -= 12.0 * np.exp(-(dist_main**2) / (80**2))     # inner V-notch, tighter

    # Tributary valleys (5 tributaries entering from different angles)
    trib_params = [
        # (x0_m, y0_m, dx, dy, depth_m, width_m)  — valley centerline as parametric line
        (3000,  2000,  0.6, 1.0, 18, 150),   # tributary from NE
        (8000,  5000,  0.4, 1.0, 15, 130),
        (11000, 8000,  0.5, 1.0, 14, 120),
        (5000,  9000, -0.3, 1.0, 12, 100),
        (9000, 12000,  0.7, 1.0, 16, 140),
    ]
    for x0, y0, dx, dy, depth, width in trib_params:
        # Distance from each pixel to the tributary line segment
        # Line direction (dx, dy) normalized
        mag = math.sqrt(dx**2 + dy**2)
        nx, ny = -dy/mag, dx/mag   # normal to line
        dist_trib = (xx - x0) * nx + (yy - y0) * ny
        dem -= depth * np.exp(-(dist_trib**2) / (width**2))

    # Light Gaussian smoothing (remove aliasing artifacts, keep relief)
    dem = gaussian_filter(dem, sigma=0.8)
    dem = np.clip(dem, 200.0, 420.0)

    return dem.astype("float32")


# ---------------------------------------------------------------------------
# 2. Terrain derivatives
# ---------------------------------------------------------------------------

def compute_slope_aspect(dem: np.ndarray, cellsize: float = PIXEL_SIZE):
    """Horn (1981) slope and aspect from 3×3 window."""
    dz_dx = np.zeros_like(dem)
    dz_dy = np.zeros_like(dem)

    # Sobel-like gradient
    dz_dx[1:-1, 1:-1] = (
        (dem[0:-2, 2:] + 2*dem[1:-1, 2:] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[1:-1, 0:-2] + dem[2:, 0:-2])
    ) / (8 * cellsize)

    dz_dy[1:-1, 1:-1] = (
        (dem[2:, 0:-2] + 2*dem[2:, 1:-1] + dem[2:, 2:]) -
        (dem[0:-2, 0:-2] + 2*dem[0:-2, 1:-1] + dem[0:-2, 2:])
    ) / (8 * cellsize)

    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)

    # Aspect: 0=N, clockwise
    aspect_deg = np.degrees(np.arctan2(-dz_dy, dz_dx)) % 360

    return slope_deg.astype("float32"), aspect_deg.astype("float32")


def compute_tsi(dem: np.ndarray) -> np.ndarray:
    """Terrain Shape Index (McNab 1989): mean(8 neighbors) - center."""
    neighbor_sum = (
        np.roll(dem, 1, 0) + np.roll(dem, -1, 0) +
        np.roll(dem, 1, 1) + np.roll(dem, -1, 1) +
        np.roll(dem, (1,1), (0,1)) + np.roll(dem, (-1,-1), (0,1)) +
        np.roll(dem, (1,-1), (0,1)) + np.roll(dem, (-1,1), (0,1))
    )
    tsi = neighbor_sum / 8.0 - dem
    # Zero out border (roll wraps edges)
    tsi[0, :] = tsi[-1, :] = tsi[:, 0] = tsi[:, -1] = 0
    return tsi.astype("float32")


def compute_twi(dem: np.ndarray, slope_deg: np.ndarray,
                cellsize: float = PIXEL_SIZE) -> np.ndarray:
    """
    Topographic Wetness Index approximation.
    Uses D8 flow accumulation (approximate via distance-to-ridge proxy).
    TWI = ln(A / tan(β))
    A = contributing area approximated from elevation rank within moving window.
    """
    # Approximate upslope area from local elevation rank (Jenson & Domingue approach)
    # Low cells in a neighborhood = higher contributing area
    local_mean = uniform_filter(dem, size=25)
    elev_below_local = local_mean - dem   # positive where cell is lower than surroundings
    # Approximate specific catchment area (m): more area where lower
    A = cellsize * (1.0 + np.maximum(elev_below_local, 0) * 0.5)

    slope_rad = np.deg2rad(np.maximum(slope_deg, 0.5))
    twi = np.log(A / np.tan(slope_rad))
    twi = np.clip(twi, 2.0, 16.0)
    return twi.astype("float32")


def compute_soil_layers(dem: np.ndarray, tsi: np.ndarray,
                        slope_deg: np.ndarray, rng_seed: int = 3):
    """
    Generate SSURGO-representative soil layers from terrain.
    Bottomlands: deep clay, poor drainage
    Ridges: shallow clay, well-drained
    """
    rng = np.random.default_rng(rng_seed)
    rows, cols = dem.shape

    elev_norm = (dem - dem.min()) / (dem.max() - dem.min())
    tsi_norm  = (tsi - tsi.min()) / (tsi.max() - tsi.min() + 1e-6)

    # Depth to clay (cm): shallow on ridges, deep in valleys/coves
    clay_depth = (
        75.0
        - 45.0 * elev_norm          # lower elevation → deeper clay
        + 55.0 * tsi_norm           # concave → deeper clay (colluvial accumulation)
        + rng.normal(0, 12, (rows, cols))
    )
    clay_depth = np.clip(clay_depth, 12.0, 200.0)

    # Clay % in B horizon
    clay_pct = (
        22.0
        - 8.0  * elev_norm
        + 14.0 * tsi_norm
        + rng.normal(0, 4, (rows, cols))
    )
    clay_pct = np.clip(clay_pct, 8.0, 58.0)

    # Drainage class (1=very poor, 7=excessively drained)
    drain = (
        5.5
        - 3.5 * tsi_norm            # concave → poorly drained
        - 0.8 * (1 - elev_norm)     # low elevation → wetter
        + rng.normal(0, 0.4, (rows, cols))
    )
    drain = np.clip(drain, 1.0, 7.0)

    return (clay_depth.astype("float32"),
            clay_pct.astype("float32"),
            drain.astype("float32"))


# ---------------------------------------------------------------------------
# 3. Run everything
# ---------------------------------------------------------------------------

def main():
    from models.lda_model import build_literature_model
    from models.ecoregion_classifier import classify_raster_stack
    from models.ecoregion_classifier import classification_summary

    terrain_dir = OUT_DIR / "terrain"
    soil_dir    = OUT_DIR / "soil"
    lec_dir     = OUT_DIR / "lec_classification"
    model_dir   = OUT_DIR / "models"

    print("=" * 60)
    print("Generating Piedmont DEM — Pickens County, SC")
    print(f"  Grid: {ROWS}×{COLS} cells @ {PIXEL_SIZE}m = "
          f"{ROWS*PIXEL_SIZE/1000:.1f}×{COLS*PIXEL_SIZE/1000:.1f} km")
    print(f"  UTM 17N origin: {ORIGIN_E:,.0f}E, {ORIGIN_N:,.0f}N")
    print("=" * 60)

    # --- DEM ---
    print("\n[1/5] DEM...")
    dem = make_piedmont_dem()
    write_tif(str(terrain_dir / "dem.tif"), dem)

    # --- Slope & Aspect ---
    print("[2/5] Slope and aspect...")
    slope, aspect = compute_slope_aspect(dem)
    write_tif(str(terrain_dir / "slope.tif"), slope)
    write_tif(str(terrain_dir / "aspect.tif"), aspect)

    # --- TSI and TWI ---
    print("[3/5] TSI and TWI...")
    tsi = compute_tsi(dem)
    twi = compute_twi(dem, slope)
    write_tif(str(terrain_dir / "terrain_shape_index.tif"), tsi)
    write_tif(str(terrain_dir / "twi.tif"), twi)

    # --- Soil ---
    print("[4/5] Soil layers...")
    clay_depth, clay_pct, drainage = compute_soil_layers(dem, tsi, slope)
    write_tif(str(soil_dir / "clay_depth.tif"), clay_depth)
    write_tif(str(soil_dir / "clay_pct_b.tif"), clay_pct)
    write_tif(str(soil_dir / "drainage_class.tif"), drainage)

    # --- LEC Classification ---
    print("[5/5] LEC classification...")
    model = build_literature_model(save_path=str(model_dir / "piedmont_lda.json"))
    results = classify_raster_stack(
        model, slope, aspect, tsi, twi, dem,
        clay_depth, clay_pct, drainage,
        latitude_deg=LATITUDE_DEG,
    )
    classification_summary(results["lec_class"], results["confidence"])

    write_tif(str(lec_dir / "lec_class.tif"),    results["lec_class"])
    write_tif(str(lec_dir / "lec_confidence.tif"), results["confidence"])

    print(f"\nAll terrain + LEC rasters written to {OUT_DIR}/")
    return results, dem, slope, aspect, tsi, twi


if __name__ == "__main__":
    main()
