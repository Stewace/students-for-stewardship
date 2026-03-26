"""
Piedmont Ecoregion Raster Classifier
EPA Level III Ecoregion 45

Applies the fitted LDA model to a stack of terrain and soil rasters
to produce a wall-to-wall LEC classification map across the Piedmont.

The classifier:
  1. Loads and aligns all raster layers (DEM derivatives + soil)
  2. Assembles the 10-predictor matrix for every pixel
  3. Runs the LDA discriminant function on each pixel
  4. Writes output rasters:
       lec_class.tif          — predicted LEC class code (1–6)
       lec_confidence.tif     — posterior probability of predicted class
       lec_proba_{class}.tif  — posterior probability per class (optional)
       lec_mahal_{class}.tif  — Mahalanobis distance per class (optional)

Input Raster Stack (all must share CRS, extent, and resolution)
---------------------------------------------------------------
  dem.tif            — Bare-earth DEM (meters, from 3DEP/NEON)
  slope.tif          — Slope angle (degrees)
  aspect.tif         — Aspect (degrees, 0=N clockwise)
  tsi.tif            — Terrain Shape Index (McNab 1989)
  twi.tif            — Topographic Wetness Index (Beven & Kirkby 1979)
  clay_depth.tif     — Depth to clay horizon (cm), from SSURGO
  clay_pct_b.tif     — Clay % in B horizon, from SSURGO
  drainage_class.tif — Soil drainage class (1–7), from SSURGO

Usage
-----
    # Classify full Piedmont using literature model (no field data needed)
    python models/ecoregion_classifier.py \\
        --dem data/terrain/dem.tif \\
        --slope data/terrain/slope.tif \\
        --aspect data/terrain/aspect.tif \\
        --tsi data/terrain/tsi.tif \\
        --twi data/terrain/twi.tif \\
        --clay-depth data/soil/clay_depth.tif \\
        --clay-pct data/soil/clay_pct_b.tif \\
        --drainage data/soil/drainage_class.tif \\
        --model data/models/piedmont_lda.json \\
        --output data/outputs/lec_classification/

    # Write all posterior probability bands
    python models/ecoregion_classifier.py ... --write-proba
"""

import argparse
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

try:
    import rasterio
    from rasterio.transform import Affine
    from rasterio.crs import CRS
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False

from models.terrain_math import (
    folded_aspect,
    heat_load_index,
    landform_index,
    normalize_clay_depth,
    slope_position_index,
    PREDICTOR_NAMES,
    N_PREDICTORS,
)
from models.lda_model import PiedmontLDA, build_literature_model
from models.piedmont_classes import LEC_CLASSES, CLASS_CODES, LEC_COLORS


# ---------------------------------------------------------------------------
# Raster I/O helpers
# ---------------------------------------------------------------------------

def load_raster(path: str) -> Tuple[np.ndarray, dict]:
    """
    Load a single-band GeoTIFF.

    Returns
    -------
    data : np.ndarray (rows, cols) as float32
    profile : rasterio profile dict (CRS, transform, nodata, etc.)
    """
    if not HAS_RASTERIO:
        raise ImportError("rasterio is required. pip install rasterio")
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        profile = src.profile.copy()
        nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
    return data, profile


def write_raster(
    path: str,
    data: np.ndarray,
    profile: dict,
    dtype: str = "float32",
    nodata: float = -9999.0,
) -> None:
    """Write a single-band GeoTIFF."""
    if not HAS_RASTERIO:
        raise ImportError("rasterio is required.")
    out_profile = profile.copy()
    out_profile.update(dtype=dtype, count=1, nodata=nodata, compress="lzw")
    out_data = np.where(np.isnan(data), nodata, data).astype(dtype)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(out_data, 1)
    print(f"  Wrote → {path}")


def write_int_raster(
    path: str,
    data: np.ndarray,
    profile: dict,
    nodata: int = 255,
) -> None:
    """Write an 8-bit integer raster (for class labels)."""
    if not HAS_RASTERIO:
        raise ImportError("rasterio is required.")
    out_profile = profile.copy()
    out_profile.update(dtype="uint8", count=1, nodata=nodata, compress="lzw")
    out_data = np.where(np.isnan(data), nodata, data).astype("uint8")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(out_data, 1)
    print(f"  Wrote → {path}")


# ---------------------------------------------------------------------------
# Predictor stack assembly
# ---------------------------------------------------------------------------

def build_predictor_stack(
    slope: np.ndarray,
    aspect: np.ndarray,
    tsi: np.ndarray,
    twi: np.ndarray,
    elevation: np.ndarray,
    clay_depth: np.ndarray,
    clay_pct_b: np.ndarray,
    drainage_class: np.ndarray,
    latitude_deg: float = 34.85,
    chunk_size: int = 100_000,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Assemble the (N, 10) predictor matrix from raster arrays.

    All input arrays must have the same shape (rows, cols).

    Returns
    -------
    X : np.ndarray (rows*cols, N_PREDICTORS)  — predictor matrix
    valid_mask : np.ndarray (rows*cols,) bool  — True where data is valid
    """
    shape = slope.shape
    n = shape[0] * shape[1]

    # Flatten all rasters
    s   = slope.reshape(-1).astype(float)
    a   = aspect.reshape(-1).astype(float)
    t   = tsi.reshape(-1).astype(float)
    w   = twi.reshape(-1).astype(float)
    e   = elevation.reshape(-1).astype(float)
    cd  = clay_depth.reshape(-1).astype(float)
    cp  = clay_pct_b.reshape(-1).astype(float)
    dr  = drainage_class.reshape(-1).astype(float)

    # Valid mask: any NaN in any band → invalid pixel
    valid = (
        np.isfinite(s) & np.isfinite(a) & np.isfinite(t) &
        np.isfinite(w) & np.isfinite(e) & np.isfinite(cd) &
        np.isfinite(cp) & np.isfinite(dr)
    )

    # Derived terrain metrics
    fa  = folded_aspect(a)
    hli = heat_load_index(s, a, latitude_deg)
    li  = landform_index(t, s)

    # Slope position: normalize elevation within valid pixels
    e_valid = e[valid]
    e_min = e_valid.min() if len(e_valid) > 0 else 0.0
    e_max = e_valid.max() if len(e_valid) > 0 else 1.0
    sp  = slope_position_index(e, e_min, e_max)

    cd_norm = normalize_clay_depth(cd)

    X = np.column_stack([s, fa, hli, t, li, w, sp, cd_norm, cp, dr])

    # Zero out invalid rows (they'll be masked in output)
    X[~valid] = np.nan

    return X, valid, shape


# ---------------------------------------------------------------------------
# Core classifier function
# ---------------------------------------------------------------------------

def classify_raster_stack(
    model: PiedmontLDA,
    slope: np.ndarray,
    aspect: np.ndarray,
    tsi: np.ndarray,
    twi: np.ndarray,
    elevation: np.ndarray,
    clay_depth: np.ndarray,
    clay_pct_b: np.ndarray,
    drainage_class: np.ndarray,
    latitude_deg: float = 34.85,
    batch_size: int = 500_000,
) -> Dict[str, np.ndarray]:
    """
    Apply the LDA model to a multi-band raster stack.

    Returns a dict of output arrays (all same shape as input rasters):
      'lec_class'          — predicted class code (float, NaN where invalid)
      'confidence'         — posterior probability of predicted class
      'proba_1' … 'proba_6' — per-class posterior probabilities
      'mahal_1' … 'mahal_6' — per-class Mahalanobis D²
    """
    print("Building predictor stack...")
    X, valid, shape = build_predictor_stack(
        slope, aspect, tsi, twi, elevation,
        clay_depth, clay_pct_b, drainage_class,
        latitude_deg=latitude_deg,
    )

    n_valid = valid.sum()
    print(f"  Valid pixels: {n_valid:,} / {valid.size:,} "
          f"({100*n_valid/valid.size:.1f}%)")

    # Outputs
    labels_flat   = np.full(X.shape[0], np.nan)
    conf_flat     = np.full(X.shape[0], np.nan)
    proba_flat    = np.full((X.shape[0], len(CLASS_CODES)), np.nan)
    mahal_flat    = np.full((X.shape[0], len(CLASS_CODES)), np.nan)

    # Classify in batches to keep memory manageable
    valid_idx = np.where(valid)[0]
    n_batches = (n_valid + batch_size - 1) // batch_size

    print(f"Classifying {n_valid:,} pixels in {n_batches} batch(es)...")
    for i in range(n_batches):
        start = i * batch_size
        end   = min(start + batch_size, n_valid)
        idx   = valid_idx[start:end]

        X_batch = X[idx]
        lbl, proba, D2 = model.predict_with_confidence(X_batch)

        labels_flat[idx]    = lbl
        conf_flat[idx]      = proba.max(axis=1)
        proba_flat[idx]     = proba
        mahal_flat[idx]     = D2

        pct = 100 * end / n_valid
        print(f"  Batch {i+1}/{n_batches}: {end:,} pixels ({pct:.0f}%)")

    # Reshape to 2D
    results = {
        "lec_class":  labels_flat.reshape(shape),
        "confidence": conf_flat.reshape(shape),
    }
    for k_idx, code in enumerate(CLASS_CODES):
        results[f"proba_{code}"]  = proba_flat[:, k_idx].reshape(shape)
        results[f"mahal_{code}"]  = mahal_flat[:, k_idx].reshape(shape)

    # Set invalid pixels to NaN
    inv = ~valid.reshape(shape)
    for arr in results.values():
        arr[inv] = np.nan

    return results


# ---------------------------------------------------------------------------
# Summary statistics
# ---------------------------------------------------------------------------

def classification_summary(lec_class: np.ndarray, confidence: np.ndarray) -> None:
    """Print area and confidence statistics for a classification result."""
    print("\n=== Classification Summary ===")
    valid = np.isfinite(lec_class)
    total_valid = valid.sum()

    print(f"{'Class':<35} {'Pixels':>10} {'% Area':>8} {'Med.Conf':>10}")
    print("-" * 65)

    for code in CLASS_CODES:
        mask = (lec_class == code)
        n = mask.sum()
        pct = 100 * n / total_valid if total_valid > 0 else 0
        med_conf = np.nanmedian(confidence[mask]) if n > 0 else np.nan
        name = LEC_CLASSES[code]
        print(f"  {code} {name:<32} {n:>10,} {pct:>7.1f}% {med_conf:>9.3f}")

    print("-" * 65)
    overall_conf = np.nanmedian(confidence[valid])
    print(f"  {'Overall':36} {total_valid:>10,} {'100.0%':>8} {overall_conf:>9.3f}")

    low_conf = (confidence[valid] < 0.5).sum()
    print(f"\n  Low-confidence pixels (<50%): {low_conf:,} "
          f"({100*low_conf/total_valid:.1f}%)")


# ---------------------------------------------------------------------------
# Full pipeline: load → classify → write
# ---------------------------------------------------------------------------

def run_classification_pipeline(
    dem_path: str,
    slope_path: str,
    aspect_path: str,
    tsi_path: str,
    twi_path: str,
    clay_depth_path: str,
    clay_pct_path: str,
    drainage_path: str,
    output_dir: str,
    model_path: Optional[str] = None,
    latitude_deg: float = 34.85,
    write_proba: bool = False,
    write_mahal: bool = False,
) -> None:
    """
    Full end-to-end LEC classification pipeline.

    Loads all rasters, runs classification, writes outputs.
    """
    print("=" * 60)
    print("Piedmont LEC Classification Pipeline")
    print("=" * 60)

    # --- Load model ---
    if model_path and Path(model_path).exists():
        print(f"\nLoading model from {model_path}...")
        model = PiedmontLDA.load(model_path)
    else:
        print("\nNo saved model found — building from literature parameters...")
        model = build_literature_model(save_path=model_path)
    print(f"Model: {model}")

    # --- Load rasters ---
    print("\nLoading rasters...")
    dem,   profile = load_raster(dem_path)
    slope, _       = load_raster(slope_path)
    aspect, _      = load_raster(aspect_path)
    tsi,   _       = load_raster(tsi_path)
    twi,   _       = load_raster(twi_path)
    clay_d, _      = load_raster(clay_depth_path)
    clay_p, _      = load_raster(clay_pct_path)
    drain,  _      = load_raster(drainage_path)

    shapes = {
        "dem": dem.shape, "slope": slope.shape, "aspect": aspect.shape,
        "tsi": tsi.shape, "twi": twi.shape,
    }
    if len(set(shapes.values())) > 1:
        print("WARNING: raster shapes differ:", shapes)
        print("All layers must be aligned. Use gdalwarp to resample.")
        raise ValueError("Mismatched raster extents/resolutions")

    print(f"  Raster shape: {dem.shape[0]} rows × {dem.shape[1]} cols")
    print(f"  Total pixels: {dem.size:,}")

    # --- Classify ---
    results = classify_raster_stack(
        model, slope, aspect, tsi, twi, dem,
        clay_d, clay_p, drain,
        latitude_deg=latitude_deg,
    )

    # --- Summary ---
    classification_summary(results["lec_class"], results["confidence"])

    # --- Write outputs ---
    print(f"\nWriting outputs to {output_dir}/")
    out = Path(output_dir)

    write_int_raster(
        str(out / "lec_class.tif"),
        results["lec_class"],
        profile,
    )
    write_raster(
        str(out / "lec_confidence.tif"),
        results["confidence"],
        profile,
    )

    if write_proba:
        for code in CLASS_CODES:
            write_raster(
                str(out / f"lec_proba_class{code}.tif"),
                results[f"proba_{code}"],
                profile,
            )

    if write_mahal:
        for code in CLASS_CODES:
            write_raster(
                str(out / f"lec_mahal_class{code}.tif"),
                results[f"mahal_{code}"],
                profile,
            )

    # Write class legend CSV
    legend_rows = [{"code": c, "name": LEC_CLASSES[c], "color": LEC_COLORS[c]}
                   for c in CLASS_CODES]
    import csv
    legend_path = out / "lec_legend.csv"
    with open(legend_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["code", "name", "color"])
        writer.writeheader()
        writer.writerows(legend_rows)
    print(f"  Wrote → {legend_path}")

    print("\nClassification complete.")


# ---------------------------------------------------------------------------
# Simulate classification on synthetic terrain (for testing w/o real rasters)
# ---------------------------------------------------------------------------

def simulate_piedmont_landscape(
    rows: int = 200,
    cols: int = 300,
    seed: int = 42,
) -> Dict[str, np.ndarray]:
    """
    Generate a synthetic Piedmont landscape for testing the classifier
    without real raster data.

    Creates a realistic rolling Piedmont terrain with:
      - Ridge-valley topography
      - Correlated terrain metrics
      - SSURGO-representative soil patterns
    """
    rng = np.random.default_rng(seed)

    # Base elevation: gentle ridges trending NE-SW
    x = np.linspace(0, 4 * np.pi, cols)
    y = np.linspace(0, 3 * np.pi, rows)
    xx, yy = np.meshgrid(x, y)

    # Piedmont: 100–400m elevation range
    dem = (
        200.0
        + 80.0  * np.sin(xx * 0.7 + yy * 0.4)
        + 40.0  * np.sin(xx * 1.5 - yy * 0.8)
        + 20.0  * np.sin(xx * 3.0 + yy * 2.0)
        + rng.normal(0, 5, (rows, cols))
    )
    dem = np.clip(dem, 80, 450).astype(float)

    # Slope: derived from DEM gradient
    dy, dx = np.gradient(dem, 30.0, 30.0)  # 30m pixels
    slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
    slope = np.clip(slope, 0, 55).astype(float)

    # Aspect: from gradient
    aspect = np.degrees(np.arctan2(-dy, dx)) % 360
    aspect = aspect.astype(float)

    # TSI: correlated with local terrain concavity
    from scipy.ndimage import uniform_filter
    dem_smooth = uniform_filter(dem, size=3)
    tsi = (dem_smooth - dem).astype(float)

    # TWI: high in valleys, low on ridges
    # Approximate: low elevation + gentle slope → high TWI
    elev_norm = (dem - dem.min()) / (dem.max() - dem.min())
    twi = (
        8.0
        - 5.0 * elev_norm
        - 0.15 * slope
        + 2.0 * (tsi / (tsi.std() + 1))
        + rng.normal(0, 0.8, (rows, cols))
    )
    twi = np.clip(twi, 2, 16).astype(float)

    # Clay depth: deeper in valleys, shallower on ridges
    clay_depth = (
        80.0
        - 50.0 * elev_norm
        + 40.0 * (tsi / (tsi.std() + 1))
        + rng.normal(0, 15, (rows, cols))
    )
    clay_depth = np.clip(clay_depth, 10, 200).astype(float)

    # Clay pct B horizon: higher in valleys
    clay_pct = (
        22.0
        - 8.0 * elev_norm
        + rng.normal(0, 5, (rows, cols))
    )
    clay_pct = np.clip(clay_pct, 5, 55).astype(float)

    # Drainage class: wetter in valleys (lower number = wetter)
    drain = (
        5.5
        - 2.5 * (1 - elev_norm)
        + rng.normal(0, 0.5, (rows, cols))
    )
    drain = np.clip(drain, 1, 7).astype(float)

    return {
        "dem": dem,
        "slope": slope,
        "aspect": aspect,
        "tsi": tsi,
        "twi": twi,
        "clay_depth": clay_depth,
        "clay_pct_b": clay_pct,
        "drainage_class": drain,
    }


def run_simulation(output_dir: str = "data/outputs/simulation/") -> None:
    """
    Run a full classification on a simulated Piedmont landscape.
    Use this to verify the model and visualize output without real data.
    """
    print("Generating synthetic Piedmont landscape...")
    try:
        from scipy.ndimage import uniform_filter
    except ImportError:
        print("scipy required for simulation. pip install scipy")
        return

    layers = simulate_piedmont_landscape(rows=300, cols=400)
    print(f"  Shape: {layers['dem'].shape}")

    print("Building literature model...")
    model = build_literature_model()

    print("Classifying simulated landscape...")
    results = classify_raster_stack(
        model,
        layers["slope"], layers["aspect"], layers["tsi"], layers["twi"],
        layers["dem"], layers["clay_depth"], layers["clay_pct_b"],
        layers["drainage_class"],
        latitude_deg=34.85,
    )

    classification_summary(results["lec_class"], results["confidence"])

    try:
        import matplotlib.pyplot as plt
        from models.piedmont_classes import LEC_COLORS
        import matplotlib.patches as mpatches
        import matplotlib.colors as mcolors

        fig, axes = plt.subplots(1, 3, figsize=(16, 5))

        # DEM
        ax = axes[0]
        im = ax.imshow(layers["dem"], cmap="terrain")
        plt.colorbar(im, ax=ax, label="Elevation (m)")
        ax.set_title("DEM — Simulated Piedmont")

        # LEC classification
        ax = axes[1]
        cmap_colors = ["white"] + [LEC_COLORS[c] for c in CLASS_CODES]
        bounds = [0] + [c - 0.5 for c in CLASS_CODES] + [CLASS_CODES[-1] + 0.5]
        cmap = mcolors.ListedColormap(cmap_colors)
        norm = mcolors.BoundaryNorm(bounds, cmap.N)
        lec_plot = results["lec_class"].copy()
        lec_plot[np.isnan(lec_plot)] = 0
        ax.imshow(lec_plot, cmap=cmap, norm=norm)
        patches = [mpatches.Patch(color=LEC_COLORS[c], label=f"{c}: {LEC_CLASSES[c]}")
                   for c in CLASS_CODES]
        ax.legend(handles=patches, fontsize=7, loc="lower right")
        ax.set_title("LEC Classification")

        # Confidence
        ax = axes[2]
        im = ax.imshow(results["confidence"], cmap="RdYlGn", vmin=0, vmax=1)
        plt.colorbar(im, ax=ax, label="Posterior Probability")
        ax.set_title("Classification Confidence")

        plt.tight_layout()
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        plot_path = f"{output_dir}/simulation_map.png"
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        print(f"\nMap saved → {plot_path}")
        plt.close()
    except ImportError:
        print("matplotlib not installed — skipping visualization")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Classify Piedmont landscape into LEC classes"
    )
    parser.add_argument("--simulate", action="store_true",
                        help="Run on synthetic landscape (no real rasters needed)")
    parser.add_argument("--dem",       type=str, help="Path to DEM raster")
    parser.add_argument("--slope",     type=str, help="Path to slope raster")
    parser.add_argument("--aspect",    type=str, help="Path to aspect raster")
    parser.add_argument("--tsi",       type=str, help="Path to TSI raster")
    parser.add_argument("--twi",       type=str, help="Path to TWI raster")
    parser.add_argument("--clay-depth",type=str, help="Path to clay depth raster")
    parser.add_argument("--clay-pct",  type=str, help="Path to clay % raster")
    parser.add_argument("--drainage",  type=str, help="Path to drainage class raster")
    parser.add_argument("--model",     type=str,
                        default="data/models/piedmont_lda.json")
    parser.add_argument("--output",    type=str,
                        default="data/outputs/lec_classification/")
    parser.add_argument("--latitude",  type=float, default=34.85)
    parser.add_argument("--write-proba",  action="store_true")
    parser.add_argument("--write-mahal",  action="store_true")
    args = parser.parse_args()

    if args.simulate:
        run_simulation(output_dir=args.output)
    elif args.dem:
        required = ["dem", "slope", "aspect", "tsi", "twi",
                    "clay_depth", "clay_pct", "drainage"]
        run_classification_pipeline(
            dem_path=args.dem, slope_path=args.slope, aspect_path=args.aspect,
            tsi_path=args.tsi, twi_path=args.twi,
            clay_depth_path=args.clay_depth, clay_pct_path=args.clay_pct,
            drainage_path=args.drainage,
            output_dir=args.output, model_path=args.model,
            latitude_deg=args.latitude,
            write_proba=args.write_proba, write_mahal=args.write_mahal,
        )
    else:
        parser.print_help()
