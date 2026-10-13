"""
Valley Cross-Section Analysis for Rosgen Classification
Hunnicutt Creek Watershed — Piedmont SC

Extracts perpendicular cross-sections along stream reaches from a 1m LiDAR DEM,
then measures:
  - Bankfull width (Wbkf)
  - Bankfull depth (Dbkf)
  - Flood-prone width (at 2× bankfull height above thalweg)
  - Valley width
  - Entrenchment ratio (ER = flood-prone width / bankfull width)

Best results with 1m LiDAR DEM. Will work with 10m DEM but cross-sections are coarser.

Usage:
    python valley_analysis.py --dem path/to/dem_1m.tif \
        --streams path/to/streams_with_slope.geojson \
        --output path/to/output/ \
        [--spacing 50] [--width 200]
"""

import argparse
import math
from pathlib import Path

import numpy as np
import geopandas as gpd
import pandas as pd
import rasterio
from shapely.geometry import LineString, Point, mapping
from shapely.affinity import rotate


# ---------------------------------------------------------------------------
# Cross-section geometry
# ---------------------------------------------------------------------------

def generate_cross_sections(
    stream_geojson: str,
    spacing: float = 50.0,
    half_width: float = 100.0,
) -> gpd.GeoDataFrame:
    """
    Generate perpendicular cross-section lines at regular intervals along each reach.

    Parameters
    ----------
    stream_geojson : str
        Path to stream network GeoJSON (from stream_delineation.py)
    spacing : float
        Distance between cross-sections along the stream (meters)
    half_width : float
        Half-length of each cross-section (total width = 2 × half_width)
        Should extend well beyond expected flood-prone width

    Returns
    -------
    GeoDataFrame with cross-section lines and reach metadata
    """
    streams = gpd.read_file(stream_geojson)
    sections = []

    for _, reach in streams.iterrows():
        geom = reach.geometry
        if geom is None or geom.is_empty:
            continue

        reach_length = geom.length
        # Place cross-sections at regular intervals, plus one at midpoint
        distances = list(np.arange(spacing, reach_length - spacing / 2, spacing))
        if not distances:
            distances = [reach_length / 2]  # at least one per reach

        for dist in distances:
            # Point along stream at this distance
            pt = geom.interpolate(dist)

            # Get azimuth of stream at this point
            pt_before = geom.interpolate(max(0, dist - 1))
            pt_after = geom.interpolate(min(reach_length, dist + 1))
            stream_az = math.atan2(
                pt_after.x - pt_before.x,
                pt_after.y - pt_before.y
            )

            # Perpendicular azimuth
            perp_az = stream_az + math.pi / 2

            # Cross-section endpoints
            x1 = pt.x + half_width * math.sin(perp_az)
            y1 = pt.y + half_width * math.cos(perp_az)
            x2 = pt.x - half_width * math.sin(perp_az)
            y2 = pt.y - half_width * math.cos(perp_az)

            line = LineString([(x1, y1), (x2, y2)])

            sections.append({
                "reach_id": reach.get("reach_id", 0),
                "strahler_order": reach.get("strahler_order", 1),
                "slope_pct": reach.get("slope_pct", np.nan),
                "dist_along_reach": dist,
                "geometry": line,
            })

    gdf = gpd.GeoDataFrame(sections, crs=streams.crs)
    gdf["xs_id"] = range(len(gdf))
    print(f"Generated {len(gdf)} cross-sections across {len(streams)} reaches")
    return gdf


# ---------------------------------------------------------------------------
# Elevation profile extraction
# ---------------------------------------------------------------------------

def extract_elevation_profile(
    cross_section: LineString,
    dem_src: rasterio.DatasetReader,
    n_points: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Sample elevation along a cross-section line.

    Returns
    -------
    (distances, elevations) — arrays of same length
    """
    length = cross_section.length
    distances = np.linspace(0, length, n_points)
    points = [cross_section.interpolate(d) for d in distances]
    coords = [(p.x, p.y) for p in points]

    nodata = dem_src.nodata or -9999
    elevations = np.array([list(dem_src.sample([c]))[0][0] for c in coords], dtype=float)
    elevations[elevations == nodata] = np.nan

    return distances, elevations


# ---------------------------------------------------------------------------
# Morphological measurements from profile
# ---------------------------------------------------------------------------

def measure_cross_section(
    distances: np.ndarray,
    elevations: np.ndarray,
    bankfull_height_above_thalweg: float = None,
) -> dict:
    """
    Extract channel morphology measurements from an elevation profile.

    If bankfull_height_above_thalweg is None, uses automatic detection
    (inflection point method — works on LiDAR; less reliable on coarse DEMs).

    Returns
    -------
    dict with:
        thalweg_elev, bankfull_elev, bankfull_width, bankfull_depth,
        flood_prone_elev, flood_prone_width, entrenchment_ratio,
        width_depth_ratio, cross_section_area
    """
    if np.all(np.isnan(elevations)):
        return _empty_measurements()

    # Thalweg = minimum elevation in cross-section
    thalweg_idx = np.nanargmin(elevations)
    thalweg_elev = elevations[thalweg_idx]

    # --- Bankfull detection ---
    if bankfull_height_above_thalweg is not None:
        # Field-supplied bankfull height (most reliable)
        bankfull_elev = thalweg_elev + bankfull_height_above_thalweg
    else:
        # Auto-detect: look for slope break (inflection) on valley walls
        # This works best with 1m LiDAR data
        bankfull_elev = _detect_bankfull_inflection(
            distances, elevations, thalweg_idx
        )

    # Bankfull width = distance between left and right bankfull crossings
    bankfull_width = _measure_width_at_elevation(
        distances, elevations, bankfull_elev, thalweg_idx
    )

    # Bankfull depth = bankfull_elev - thalweg_elev
    bankfull_depth = bankfull_elev - thalweg_elev

    # Mean bankfull depth = cross-sectional area / bankfull width
    xs_area = _cross_section_area(distances, elevations, bankfull_elev, thalweg_idx)
    mean_bankfull_depth = xs_area / bankfull_width if bankfull_width > 0 else np.nan

    # Width/Depth ratio
    wd_ratio = bankfull_width / mean_bankfull_depth if mean_bankfull_depth > 0 else np.nan

    # Flood-prone width = width at 2× bankfull depth above thalweg
    flood_prone_elev = thalweg_elev + 2 * bankfull_depth
    flood_prone_width = _measure_width_at_elevation(
        distances, elevations, flood_prone_elev, thalweg_idx
    )

    # Entrenchment ratio
    er = flood_prone_width / bankfull_width if bankfull_width > 0 else np.nan

    return {
        "thalweg_elev_m": round(float(thalweg_elev), 3),
        "bankfull_elev_m": round(float(bankfull_elev), 3),
        "bankfull_width_m": round(float(bankfull_width), 3),
        "bankfull_depth_m": round(float(bankfull_depth), 3),
        "mean_bankfull_depth_m": round(float(mean_bankfull_depth), 3),
        "xs_area_m2": round(float(xs_area), 3),
        "width_depth_ratio": round(float(wd_ratio), 2),
        "flood_prone_elev_m": round(float(flood_prone_elev), 3),
        "flood_prone_width_m": round(float(flood_prone_width), 3),
        "entrenchment_ratio": round(float(er), 3),
    }


def _detect_bankfull_inflection(
    distances: np.ndarray,
    elevations: np.ndarray,
    thalweg_idx: int,
    search_height: float = 5.0,
) -> float:
    """
    Auto-detect bankfull elevation using slope change method.
    Looks for the elevation where the valley wall gradient inflects
    from steep (active channel) to gentle (floodplain).

    search_height: max height above thalweg to search (meters)
    """
    thalweg_elev = elevations[thalweg_idx]
    n = len(elevations)

    # Look at left wall (left of thalweg) and right wall (right of thalweg)
    bankfull_candidates = []

    for side_indices in [
        range(thalweg_idx, -1, -1),   # left wall
        range(thalweg_idx, n),          # right wall
    ]:
        prev_grad = None
        for i in side_indices:
            if np.isnan(elevations[i]):
                continue
            if elevations[i] > thalweg_elev + search_height:
                break
            if prev_grad is not None:
                current_grad = elevations[i] - elevations[thalweg_idx]
                if prev_grad > 0.3 and current_grad < 0.1:
                    # Slope break found
                    bankfull_candidates.append(elevations[i])
                    break
            prev_grad = abs(elevations[i] - thalweg_elev) / max(
                abs(distances[i] - distances[thalweg_idx]), 0.001
            )

    if bankfull_candidates:
        return np.mean(bankfull_candidates)

    # Fallback: use 0.5m above thalweg (crude estimate for Piedmont streams)
    return thalweg_elev + 0.5


def _measure_width_at_elevation(
    distances: np.ndarray,
    elevations: np.ndarray,
    target_elev: float,
    thalweg_idx: int,
) -> float:
    """
    Measure channel width at a given elevation by finding where the
    elevation profile crosses target_elev on each side of the thalweg.
    """
    n = len(elevations)

    def find_crossing(indices):
        for i in indices:
            if i + 1 >= n or i < 0:
                break
            e1, e2 = elevations[i], elevations[i + 1 if i < n - 1 else i]
            if np.isnan(e1) or np.isnan(e2):
                continue
            if (e1 <= target_elev <= e2) or (e2 <= target_elev <= e1):
                # Linear interpolation
                frac = (target_elev - e1) / (e2 - e1 + 1e-10)
                return distances[i] + frac * (distances[i + 1] - distances[i])
        # If no crossing found, return edge
        return distances[0] if indices[0] < thalweg_idx else distances[-1]

    left_dist = find_crossing(range(thalweg_idx, -1, -1))
    right_dist = find_crossing(range(thalweg_idx, n - 1))

    return abs(right_dist - left_dist)


def _cross_section_area(
    distances: np.ndarray,
    elevations: np.ndarray,
    bankfull_elev: float,
    thalweg_idx: int,
) -> float:
    """Compute cross-sectional area below bankfull elevation using trapezoid rule."""
    # Find bankfull crossing indices
    n = len(elevations)
    clipped = np.minimum(elevations, bankfull_elev)
    below_bankfull = bankfull_elev - clipped  # depth below bankfull

    # Integrate with trapezoid rule, only between left and right crossings
    area = float(np.trapz(below_bankfull, distances))
    return max(area, 0.0)


def _empty_measurements() -> dict:
    nan = float("nan")
    return {k: nan for k in [
        "thalweg_elev_m", "bankfull_elev_m", "bankfull_width_m",
        "bankfull_depth_m", "mean_bankfull_depth_m", "xs_area_m2",
        "width_depth_ratio", "flood_prone_elev_m", "flood_prone_width_m",
        "entrenchment_ratio",
    ]}


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_valley_analysis(
    dem_path: str,
    stream_geojson: str,
    output_dir: str,
    spacing: float = 50.0,
    half_width: float = 100.0,
    bankfull_height: float = None,
) -> str:
    """
    Run complete valley cross-section analysis.

    Returns path to output GeoJSON with all measurements per cross-section.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Valley Cross-Section Analysis ===")
    print(f"Stream: {stream_geojson}")
    print(f"DEM: {dem_path}")
    print(f"Cross-section spacing: {spacing}m, half-width: {half_width}m\n")

    # Generate cross-section lines
    xs_gdf = generate_cross_sections(stream_geojson, spacing, half_width)

    # Extract measurements from DEM
    results = []
    with rasterio.open(dem_path) as dem_src:
        for idx, row in xs_gdf.iterrows():
            distances, elevations = extract_elevation_profile(row.geometry, dem_src)
            measurements = measure_cross_section(
                distances, elevations, bankfull_height
            )
            measurements["xs_id"] = row["xs_id"]
            measurements["reach_id"] = row["reach_id"]
            measurements["strahler_order"] = row["strahler_order"]
            measurements["slope_pct"] = row["slope_pct"]
            measurements["geometry"] = row.geometry
            results.append(measurements)

    results_gdf = gpd.GeoDataFrame(results, crs=xs_gdf.crs)

    out_path = str(out / "cross_sections_measured.geojson")
    results_gdf.to_file(out_path, driver="GeoJSON")
    print(f"\nCross-section measurements → {out_path}")
    print(f"Total cross-sections: {len(results_gdf)}")

    # Summary statistics per reach
    summary = (
        results_gdf.groupby("reach_id")[[
            "bankfull_width_m", "mean_bankfull_depth_m",
            "width_depth_ratio", "entrenchment_ratio", "slope_pct"
        ]].mean().round(3)
    )
    summary_path = str(out / "reach_morphology_summary.csv")
    summary.to_csv(summary_path)
    print(f"Reach summary → {summary_path}")

    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Valley cross-section analysis")
    parser.add_argument("--dem", required=True)
    parser.add_argument("--streams", required=True, help="streams_with_slope.geojson")
    parser.add_argument("--output", required=True)
    parser.add_argument("--spacing", type=float, default=50.0,
                        help="Cross-section spacing in meters (default: 50)")
    parser.add_argument("--width", type=float, default=100.0,
                        help="Cross-section half-width in meters (default: 100)")
    parser.add_argument("--bankfull-height", type=float, default=None,
                        help="Known bankfull height above thalweg (meters). "
                             "If omitted, auto-detection is used.")
    args = parser.parse_args()

    run_valley_analysis(
        args.dem, args.streams, args.output,
        args.spacing, args.width, args.bankfull_height
    )
