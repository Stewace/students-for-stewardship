"""
Terrain Analysis Pipeline for Landscape Ecosystem Classification (LEC)
Piedmont of South Carolina — Hunnicutt Creek Watershed

Uses WhiteboxTools to compute all terrain indices needed for the
discriminant analysis classification.

Usage:
    python terrain_analysis.py --dem path/to/dem.tif --output path/to/output/
"""

import argparse
import os
from pathlib import Path

import whitebox

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# WhiteboxTools instance — set verbose=False to suppress per-tool output
wbt = whitebox.WhiteboxTools()
wbt.verbose = False


def run_terrain_analysis(dem_path: str, output_dir: str) -> dict:
    """
    Compute all terrain indices needed for LEC discriminant analysis.

    Parameters
    ----------
    dem_path : str
        Path to input DEM GeoTIFF (projected CRS, meters)
    output_dir : str
        Directory where output rasters will be written

    Returns
    -------
    dict
        Paths to all generated output rasters
    """
    dem = str(Path(dem_path).resolve())
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    outputs = {}

    print(f"Input DEM: {dem}")
    print(f"Output directory: {out}\n")

    # ------------------------------------------------------------------
    # 1. Slope (degrees)
    # ------------------------------------------------------------------
    slope_path = str(out / "slope.tif")
    print("Computing slope...")
    wbt.slope(dem, slope_path, zfactor=1.0, units="degrees")
    outputs["slope"] = slope_path

    # ------------------------------------------------------------------
    # 2. Aspect (degrees, 0 = north, clockwise)
    # ------------------------------------------------------------------
    aspect_path = str(out / "aspect.tif")
    print("Computing aspect...")
    wbt.aspect(dem, aspect_path)
    outputs["aspect"] = aspect_path

    # ------------------------------------------------------------------
    # 3. Terrain Shape Index (TSI) — McNab 1989
    #    Positive = concave (hollow), Negative = convex (ridge)
    # ------------------------------------------------------------------
    tsi_path = str(out / "terrain_shape_index.tif")
    print("Computing Terrain Shape Index (TSI)...")
    wbt.terrain_ruggedness_index(dem, tsi_path)  # use TRI as TSI proxy
    # Note: WhiteboxTools terrain_shape_index tool available in WBT Pro
    # For open version, approximate TSI with difference from mean neighbor:
    _tsi_approx(dem, tsi_path, out)
    outputs["tsi"] = tsi_path

    # ------------------------------------------------------------------
    # 4. Topographic Position Index (TPI) — closely related to LI
    # ------------------------------------------------------------------
    tpi_path = str(out / "topographic_position_index.tif")
    print("Computing Topographic Position Index (TPI / Landform Index)...")
    wbt.topographic_position_index(dem, tpi_path, inner_radius=1, outer_radius=5)
    outputs["tpi"] = tpi_path

    # ------------------------------------------------------------------
    # 5. Profile Curvature
    # ------------------------------------------------------------------
    profile_curv_path = str(out / "profile_curvature.tif")
    print("Computing profile curvature...")
    wbt.profile_curvature(dem, profile_curv_path)
    outputs["profile_curvature"] = profile_curv_path

    # ------------------------------------------------------------------
    # 6. Plan Curvature
    # ------------------------------------------------------------------
    plan_curv_path = str(out / "plan_curvature.tif")
    print("Computing plan curvature...")
    wbt.plan_curvature(dem, plan_curv_path)
    outputs["plan_curvature"] = plan_curv_path

    # ------------------------------------------------------------------
    # 7. Elevation (raw — useful as a predictor variable)
    # ------------------------------------------------------------------
    outputs["elevation"] = dem

    # ------------------------------------------------------------------
    # 8. Hillshade (for visualization only — not used in classification)
    # ------------------------------------------------------------------
    hillshade_path = str(out / "hillshade.tif")
    print("Computing hillshade (visualization)...")
    wbt.hillshade(dem, hillshade_path, azimuth=315.0, altitude=45.0)
    outputs["hillshade"] = hillshade_path

    print("\nTerrain analysis complete.")
    for key, path in outputs.items():
        print(f"  {key:25s} → {path}")

    return outputs


def _tsi_approx(dem: str, output_path: str, work_dir: Path):
    """
    Approximate Terrain Shape Index using focal mean difference.
    TSI = focal_mean(neighborhood) - center_cell_value
    Uses WhiteboxTools mean filter as a proxy.
    """
    mean_path = str(work_dir / "_focal_mean_temp.tif")
    wbt.mean_filter(dem, mean_path, filterx=3, filtery=3)

    # Subtract DEM from focal mean → positive = concave, negative = convex
    wbt.subtract(mean_path, dem, output_path)

    # Clean up temp file
    if os.path.exists(mean_path):
        os.remove(mean_path)


def compute_folded_aspect(aspect_raster: str, output_path: str):
    """
    Transform circular aspect to linear 'heat load' index.

    Folded aspect (Beers et al. 1966):
        folded = |180 - |aspect - 225||
        0 = SW (hottest, most xeric)
        180 = NE (coolest, most mesic)

    This is needed for linear discriminant analysis because raw aspect
    is circular (0° and 360° are the same direction).
    """
    import numpy as np
    import rasterio

    with rasterio.open(aspect_raster) as src:
        aspect = src.read(1).astype(float)
        profile = src.profile

    nodata = profile.get("nodata", -9999)
    valid = aspect != nodata

    folded = np.full_like(aspect, nodata)
    folded[valid] = np.abs(180 - np.abs(aspect[valid] - 225))

    profile.update(dtype="float32")
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(folded.astype("float32"), 1)

    print(f"Folded aspect written to: {output_path}")


def build_predictor_stack(terrain_outputs: dict, soil_rasters: dict) -> dict:
    """
    Assemble all predictor rasters into a documented stack.

    Parameters
    ----------
    terrain_outputs : dict
        Output from run_terrain_analysis()
    soil_rasters : dict
        Paths to soil attribute rasters, e.g.:
        {
          "clay_depth_cm": "path/to/clay_depth.tif",
          "clay_pct_b": "path/to/clay_pct_b.tif",
          "drainage_class": "path/to/drainage.tif"
        }

    Returns
    -------
    dict
        Full predictor stack with all variable paths
    """
    stack = {
        # Terrain predictors (from DEM)
        "elevation": terrain_outputs["elevation"],
        "slope": terrain_outputs["slope"],
        "aspect_folded": terrain_outputs.get("aspect_folded"),
        "tsi": terrain_outputs["tsi"],
        "tpi": terrain_outputs["tpi"],
        "profile_curvature": terrain_outputs["profile_curvature"],
        "plan_curvature": terrain_outputs["plan_curvature"],
        # Soil predictors (from SSURGO, rasterized)
        "clay_depth_cm": soil_rasters.get("clay_depth_cm"),
        "clay_pct_b": soil_rasters.get("clay_pct_b"),
        "drainage_class": soil_rasters.get("drainage_class"),
    }
    return {k: v for k, v in stack.items() if v is not None}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compute terrain indices for LEC classification"
    )
    parser.add_argument("--dem", required=True, help="Path to input DEM GeoTIFF")
    parser.add_argument(
        "--output", required=True, help="Directory to write output rasters"
    )
    args = parser.parse_args()

    terrain = run_terrain_analysis(args.dem, args.output)

    # Compute folded aspect (needed for LDA)
    folded_path = str(Path(args.output) / "aspect_folded.tif")
    compute_folded_aspect(terrain["aspect"], folded_path)
    terrain["aspect_folded"] = folded_path
