"""
Master Pipeline — LEC + Rosgen Classification
Hunnicutt Creek Watershed, Piedmont SC

Runs the complete analysis from raw DEM to classified map in one command.

Usage:
    python run_pipeline.py --dem data/processed/dem/dem_utm.tif [options]

For a quick test run with default settings:
    python run_pipeline.py --dem data/processed/dem/dem_utm.tif --output data/processed/

Advanced:
    python run_pipeline.py \
      --dem data/processed/dem/dem_1m_utm.tif \
      --dem-10m data/processed/dem/dem_10m_utm.tif \
      --output data/processed/ \
      --stream-threshold 500 \
      --xs-spacing 50 \
      --field-data data/field/plots/field_measurements.csv \
      --skip-terrain   # if terrain rasters already exist
"""

import argparse
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Import pipeline modules
# ---------------------------------------------------------------------------

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from map_system.stack.python.terrain_analysis import run_terrain_analysis, compute_folded_aspect
from rosgen.python.stream_delineation import run_delineation
from rosgen.python.valley_analysis import run_valley_analysis
from rosgen.python.rosgen_parameters import assemble_rosgen_parameters
from rosgen.python.rosgen_classify import classify_all_reaches


# ---------------------------------------------------------------------------
# Pipeline stages
# ---------------------------------------------------------------------------

def stage_terrain(dem: str, out: Path, skip: bool = False) -> dict:
    """Stage 1: Terrain analysis (LEC predictors)."""
    terrain_dir = str(out / "terrain")

    if skip and (out / "terrain" / "slope.tif").exists():
        print("\n[Stage 1] Terrain rasters exist — skipping (--skip-terrain)")
        return {
            "slope": str(out / "terrain" / "slope.tif"),
            "aspect_folded": str(out / "terrain" / "aspect_folded.tif"),
            "tsi": str(out / "terrain" / "terrain_shape_index.tif"),
            "tpi": str(out / "terrain" / "topographic_position_index.tif"),
            "profile_curvature": str(out / "terrain" / "profile_curvature.tif"),
            "plan_curvature": str(out / "terrain" / "plan_curvature.tif"),
            "hillshade": str(out / "terrain" / "hillshade.tif"),
            "elevation": dem,
        }

    print("\n" + "="*60)
    print("[Stage 1] Terrain Analysis")
    print("="*60)
    terrain = run_terrain_analysis(dem, terrain_dir)

    folded_path = str(out / "terrain" / "aspect_folded.tif")
    compute_folded_aspect(terrain["aspect"], folded_path)
    terrain["aspect_folded"] = folded_path

    return terrain


def stage_streams(dem: str, out: Path, threshold: int = 500) -> dict:
    """Stage 2: Stream network delineation."""
    print("\n" + "="*60)
    print("[Stage 2] Stream Delineation")
    print("="*60)

    streams_dir = str(out / "streams")
    outputs = run_delineation(dem, streams_dir, threshold=threshold, min_order=1)
    return outputs


def stage_cross_sections(
    dem: str, stream_geojson: str, out: Path,
    spacing: float = 50.0, half_width: float = 150.0,
    bankfull_height: float = None,
) -> str:
    """Stage 3: Valley cross-section extraction."""
    print("\n" + "="*60)
    print("[Stage 3] Valley Cross-Section Analysis")
    print("="*60)

    xs_path = run_valley_analysis(
        dem, stream_geojson, str(out / "rosgen"),
        spacing=spacing, half_width=half_width,
        bankfull_height=bankfull_height,
    )
    return xs_path


def stage_rosgen_parameters(
    xs_geojson: str, stream_geojson: str, out: Path, field_data: str = None
) -> str:
    """Stage 4: Rosgen parameter assembly."""
    print("\n" + "="*60)
    print("[Stage 4] Rosgen Parameter Assembly")
    print("="*60)

    params_path = assemble_rosgen_parameters(
        xs_geojson, stream_geojson, str(out / "rosgen"), field_data
    )
    return params_path


def stage_rosgen_classify(params_geojson: str, out: Path) -> str:
    """Stage 5: Rosgen Level I + II classification."""
    print("\n" + "="*60)
    print("[Stage 5] Rosgen Classification")
    print("="*60)

    classified_path = classify_all_reaches(params_geojson, str(out / "rosgen"))
    return classified_path


def stage_publish(classified_geojson: str, hillshade: str = None):
    """Stage 6: Copy outputs to Leaflet map data folder."""
    print("\n" + "="*60)
    print("[Stage 6] Publishing to Leaflet Map")
    print("="*60)

    map_data = Path("map-system/stack/leaflet/data")
    map_data.mkdir(parents=True, exist_ok=True)

    # Rosgen GeoJSON
    dest = map_data / "rosgen_classified.geojson"
    shutil.copy(classified_geojson, dest)
    print(f"  Rosgen GeoJSON → {dest}")

    print(f"\nOpen the map:")
    print(f"  cd map-system/stack/leaflet && python -m http.server 8000")
    print(f"  Then open http://localhost:8000 in a browser")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Run full LEC + Rosgen classification pipeline"
    )
    parser.add_argument(
        "--dem", required=True,
        help="Primary DEM path (1m preferred for Rosgen cross-sections)"
    )
    parser.add_argument(
        "--dem-10m", default=None,
        help="10m DEM for terrain analysis (if separate from 1m DEM)"
    )
    parser.add_argument(
        "--output", default="data/processed",
        help="Root output directory (default: data/processed)"
    )
    parser.add_argument(
        "--stream-threshold", type=int, default=500,
        help="Flow accumulation threshold for stream extraction (default: 500)"
    )
    parser.add_argument(
        "--xs-spacing", type=float, default=50.0,
        help="Cross-section spacing in meters (default: 50)"
    )
    parser.add_argument(
        "--xs-width", type=float, default=150.0,
        help="Cross-section half-width in meters (default: 150)"
    )
    parser.add_argument(
        "--bankfull-height", type=float, default=None,
        help="Known bankfull height above thalweg in meters (auto-detect if omitted)"
    )
    parser.add_argument(
        "--field-data", default=None,
        help="CSV with field measurements to override LiDAR values"
    )
    parser.add_argument(
        "--skip-terrain", action="store_true",
        help="Skip terrain analysis if rasters already exist"
    )
    parser.add_argument(
        "--start-from", type=int, default=1, choices=[1, 2, 3, 4, 5],
        help="Start from a specific stage (1=terrain, 2=streams, 3=xs, 4=params, 5=classify)"
    )

    args = parser.parse_args()
    out = Path(args.output)
    dem = args.dem
    dem_terrain = args.dem_10m or dem

    print("\n" + "="*60)
    print("  LEC + Rosgen Pipeline — Piedmont SC")
    print("="*60)
    print(f"  DEM (1m):      {dem}")
    print(f"  DEM (terrain): {dem_terrain}")
    print(f"  Output root:   {out}")

    # Stage 1: Terrain
    if args.start_from <= 1:
        terrain = stage_terrain(dem_terrain, out, skip=args.skip_terrain)

    # Stage 2: Stream delineation
    if args.start_from <= 2:
        stream_outputs = stage_streams(dem, out, threshold=args.stream_threshold)
        stream_geojson = stream_outputs["stream_network_geojson"]
    else:
        stream_geojson = str(out / "streams" / "streams_with_slope.geojson")

    # Stage 3: Cross-sections
    if args.start_from <= 3:
        xs_geojson = stage_cross_sections(
            dem, stream_geojson, out,
            spacing=args.xs_spacing,
            half_width=args.xs_width,
            bankfull_height=args.bankfull_height,
        )
    else:
        xs_geojson = str(out / "rosgen" / "cross_sections_measured.geojson")

    # Stage 4: Parameters
    if args.start_from <= 4:
        params_geojson = stage_rosgen_parameters(
            xs_geojson, stream_geojson, out, args.field_data
        )
    else:
        params_geojson = str(out / "rosgen" / "rosgen_parameters.geojson")

    # Stage 5: Classify
    classified_geojson = stage_rosgen_classify(params_geojson, out)

    # Stage 6: Publish
    hillshade = str(out / "terrain" / "hillshade.tif") if args.start_from <= 1 else None
    stage_publish(classified_geojson, hillshade)

    print("\n" + "="*60)
    print("  Pipeline complete.")
    print("="*60)
    print("""
Next steps:
  1. Load outputs in QGIS for visual QA
  2. Review rosgen_classified_summary.csv — check low-confidence reaches
  3. Field-verify F and G type reaches (incised/degraded)
  4. Update data/field/plots/field_measurements.csv with field data
  5. Re-run from Stage 4 with --start-from 4 --field-data ... to update classification
  6. Run LEC discriminant analysis: see map-system/workflows/lec-classification.md
""")


if __name__ == "__main__":
    main()
