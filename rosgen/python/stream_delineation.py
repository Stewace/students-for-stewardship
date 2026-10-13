"""
Stream Network Delineation from DEM
Hunnicutt Creek Watershed — Piedmont SC

Extracts stream network, orders reaches (Strahler), delineates sub-watersheds,
and exports stream centerlines as GeoJSON for Rosgen analysis.

Usage:
    python stream_delineation.py --dem path/to/dem_1m.tif --output path/to/output/ \
        [--threshold 2000] [--min-order 2]

The threshold parameter is the flow accumulation cell count above which a cell
is considered part of the stream network. Lower = more streams extracted.
For 1m DEM: ~2000 cells = ~0.2 ha contributing area (good for Piedmont headwaters)
For 10m DEM: ~100 cells = ~10 ha (use for regional network)
"""

import argparse
import json
import os
from pathlib import Path

import whitebox
import rasterio
import numpy as np
import geopandas as gpd
from shapely.geometry import LineString, mapping

wbt = whitebox.WhiteboxTools()
wbt.verbose = False


# ---------------------------------------------------------------------------
# Step 1: Hydrological preprocessing
# ---------------------------------------------------------------------------

def preprocess_dem(dem_path: str, work_dir: Path) -> str:
    """
    Fill depressions and breach single-cell pits to ensure continuous flow routing.
    Returns path to conditioned DEM.
    """
    print("Conditioning DEM for hydrological analysis...")

    # Breach depressions first (preserves more topographic detail than filling)
    breached = str(work_dir / "dem_breached.tif")
    wbt.breach_depressions_least_cost(
        dem_path,
        breached,
        dist=5,
        max_cost=None,
        min_dist=True,
        flat_increment=None,
        fill=True,
    )

    # Fill any remaining sinks
    filled = str(work_dir / "dem_filled.tif")
    wbt.fill_depressions_wang_and_liu(breached, filled)

    # Clean up intermediate
    if os.path.exists(breached):
        os.remove(breached)

    print(f"  Conditioned DEM → {filled}")
    return filled


# ---------------------------------------------------------------------------
# Step 2: Flow direction and accumulation
# ---------------------------------------------------------------------------

def compute_flow_routing(filled_dem: str, work_dir: Path) -> tuple[str, str]:
    """
    Compute D8 flow direction and flow accumulation rasters.
    Returns (flow_direction_path, flow_accumulation_path).
    """
    print("Computing flow direction (D8)...")
    flow_dir = str(work_dir / "flow_direction_d8.tif")
    wbt.d8_pointer(filled_dem, flow_dir)

    print("Computing flow accumulation...")
    flow_acc = str(work_dir / "flow_accumulation.tif")
    wbt.d8_flow_accumulation(filled_dem, flow_acc, out_type="cells", log=False)

    print(f"  Flow direction → {flow_dir}")
    print(f"  Flow accumulation → {flow_acc}")
    return flow_dir, flow_acc


# ---------------------------------------------------------------------------
# Step 3: Stream extraction and ordering
# ---------------------------------------------------------------------------

def extract_streams(
    flow_acc: str, flow_dir: str, work_dir: Path, threshold: int = 2000
) -> tuple[str, str]:
    """
    Extract stream network above a flow accumulation threshold.
    Apply Strahler stream ordering.

    Parameters
    ----------
    threshold : int
        Minimum contributing area in cells.
        1m DEM: 2000 cells ≈ 0.2 ha
        10m DEM: 100 cells ≈ 10 ha

    Returns
    -------
    (streams_raster, stream_order_raster)
    """
    print(f"Extracting streams (threshold = {threshold} cells)...")

    streams = str(work_dir / "streams.tif")
    wbt.extract_streams(flow_acc, streams, threshold=threshold)

    print("Applying Strahler stream ordering...")
    stream_order = str(work_dir / "stream_order_strahler.tif")
    wbt.strahler_stream_order(flow_dir, streams, stream_order)

    print(f"  Stream raster → {streams}")
    print(f"  Stream order → {stream_order}")
    return streams, stream_order


# ---------------------------------------------------------------------------
# Step 4: Vectorize streams to GeoJSON
# ---------------------------------------------------------------------------

def vectorize_streams(
    streams_raster: str,
    stream_order_raster: str,
    flow_dir: str,
    work_dir: Path,
    min_order: int = 1,
) -> str:
    """
    Convert stream raster to vector lines, attach stream order attribute,
    and split into individual reaches.

    Returns path to GeoJSON output.
    """
    print("Vectorizing stream network...")

    # WhiteboxTools raster streams to vector
    stream_vector = str(work_dir / "streams_raw.shp")
    wbt.raster_streams_to_vector(streams_raster, flow_dir, stream_vector)

    # Read vector + attach stream order values
    streams_gdf = gpd.read_file(stream_vector)

    # Sample stream order at start of each line
    with rasterio.open(stream_order_raster) as src:
        orders = []
        for geom in streams_gdf.geometry:
            if geom is None:
                orders.append(0)
                continue
            # Sample at midpoint of line
            pt = geom.interpolate(0.5, normalized=True)
            val = list(src.sample([(pt.x, pt.y)]))[0][0]
            orders.append(int(val) if not np.isnan(val) else 0)

    streams_gdf["strahler_order"] = orders
    streams_gdf["reach_id"] = range(len(streams_gdf))

    # Filter by minimum order
    if min_order > 1:
        streams_gdf = streams_gdf[streams_gdf["strahler_order"] >= min_order]
        print(f"  Filtered to order ≥ {min_order}: {len(streams_gdf)} reaches")

    # Export to GeoJSON
    out_path = str(work_dir / "streams_network.geojson")
    streams_gdf.to_file(out_path, driver="GeoJSON")
    print(f"  Stream network → {out_path} ({len(streams_gdf)} reaches)")

    # Clean up shapefile intermediates
    for ext in [".shp", ".dbf", ".shx", ".prj"]:
        f = stream_vector.replace(".shp", ext)
        if os.path.exists(f):
            os.remove(f)

    return out_path


# ---------------------------------------------------------------------------
# Step 5: Sub-watershed delineation per reach
# ---------------------------------------------------------------------------

def delineate_sub_watersheds(
    flow_dir: str, streams_raster: str, work_dir: Path
) -> str:
    """
    Delineate sub-watershed for each stream reach using watershed function.
    Returns path to sub-watershed raster.
    """
    print("Delineating sub-watersheds...")

    subwatersheds = str(work_dir / "sub_watersheds.tif")
    wbt.watershed(flow_dir, streams_raster, subwatersheds)

    print(f"  Sub-watersheds → {subwatersheds}")
    return subwatersheds


# ---------------------------------------------------------------------------
# Step 6: Compute reach slopes from DEM
# ---------------------------------------------------------------------------

def compute_reach_slopes(
    stream_geojson: str, dem_path: str, work_dir: Path
) -> str:
    """
    For each stream reach, compute average slope (rise/run along thalweg).
    Adds 'slope_pct' and 'slope_deg' attributes to stream GeoJSON.

    Returns path to updated GeoJSON.
    """
    print("Computing reach slopes...")
    import math

    streams_gdf = gpd.read_file(stream_geojson)

    with rasterio.open(dem_path) as src:
        slopes_pct = []
        slopes_deg = []

        for _, row in streams_gdf.iterrows():
            geom = row.geometry
            if geom is None or geom.is_empty:
                slopes_pct.append(np.nan)
                slopes_deg.append(np.nan)
                continue

            # Sample elevation at start and end of reach
            start = geom.coords[0]
            end = geom.coords[-1]
            elev_start = list(src.sample([start]))[0][0]
            elev_end = list(src.sample([end]))[0][0]

            elev_diff = abs(float(elev_start) - float(elev_end))
            length = geom.length  # in CRS units (meters if projected)

            slope_pct = (elev_diff / length) * 100 if length > 0 else 0
            slope_deg = math.degrees(math.atan(elev_diff / length)) if length > 0 else 0

            slopes_pct.append(round(slope_pct, 4))
            slopes_deg.append(round(slope_deg, 4))

    streams_gdf["slope_pct"] = slopes_pct
    streams_gdf["slope_deg"] = slopes_deg

    out_path = str(work_dir / "streams_with_slope.geojson")
    streams_gdf.to_file(out_path, driver="GeoJSON")
    print(f"  Reaches with slope → {out_path}")
    return out_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_delineation(
    dem_path: str,
    output_dir: str,
    threshold: int = 2000,
    min_order: int = 1,
) -> dict:
    """
    Run complete stream delineation pipeline.

    Returns
    -------
    dict with paths to all key outputs
    """
    out = Path(output_dir)
    work = out / "stream_delineation_work"
    work.mkdir(parents=True, exist_ok=True)

    dem = str(Path(dem_path).resolve())
    print(f"\n=== Stream Delineation Pipeline ===")
    print(f"DEM: {dem}")
    print(f"Threshold: {threshold} cells\n")

    filled = preprocess_dem(dem, work)
    flow_dir, flow_acc = compute_flow_routing(filled, work)
    streams, stream_order = extract_streams(flow_acc, flow_dir, work, threshold)
    stream_geojson = vectorize_streams(streams, stream_order, flow_dir, work, min_order)
    sub_watersheds = delineate_sub_watersheds(flow_dir, streams, work)
    streams_with_slope = compute_reach_slopes(stream_geojson, dem, out)

    outputs = {
        "dem_filled": filled,
        "flow_direction": flow_dir,
        "flow_accumulation": flow_acc,
        "streams_raster": streams,
        "stream_order_raster": stream_order,
        "stream_network_geojson": streams_with_slope,
        "sub_watersheds": sub_watersheds,
    }

    print("\n=== Delineation complete ===")
    for k, v in outputs.items():
        print(f"  {k:30s} → {v}")

    return outputs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delineate stream network from DEM")
    parser.add_argument("--dem", required=True, help="Path to input DEM GeoTIFF")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--threshold",
        type=int,
        default=2000,
        help="Flow accumulation threshold (cells). Default=2000 for 1m DEM",
    )
    parser.add_argument(
        "--min-order",
        type=int,
        default=1,
        help="Minimum Strahler order to include. Default=1 (all streams)",
    )
    args = parser.parse_args()

    run_delineation(args.dem, args.output, args.threshold, args.min_order)
