"""
Rosgen Classification Parameters — Per-Reach Computation
Hunnicutt Creek Watershed — Piedmont SC

Aggregates cross-section measurements to reach-level Rosgen parameters:
  - Entrenchment Ratio (ER)
  - Width/Depth Ratio (W/D)
  - Sinuosity (K)
  - Channel Slope (S)
  - Representative bankfull dimensions

Then computes preliminary Rosgen Level I (valley type) and Level II (stream type)
classification inputs. Final classification is handled by rosgen_classify.py.

Usage:
    python rosgen_parameters.py \
        --cross-sections path/to/cross_sections_measured.geojson \
        --streams path/to/streams_with_slope.geojson \
        --output path/to/output/

Optional field data override:
    --field-data path/to/field_measurements.csv
    (CSV with columns: reach_id, bankfull_width_m, bankfull_depth_m,
     flood_prone_width_m, d50_mm, bankfull_height_m)
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import mapping


# ---------------------------------------------------------------------------
# Sinuosity computation
# ---------------------------------------------------------------------------

def compute_sinuosity(streams_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Compute sinuosity (K) for each reach.

    Sinuosity = channel length / straight-line (valley) length
    K < 1.2 → straight
    K 1.2–1.5 → sinuous
    K > 1.5 → meandering

    Note: True sinuosity requires the valley centerline. Here we use the
    chord distance between reach endpoints as the valley length proxy.
    For best accuracy, digitize valley centerlines in QGIS.
    """
    sinuosities = []
    for _, row in streams_gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            sinuosities.append(np.nan)
            continue

        channel_length = geom.length
        start = geom.coords[0]
        end = geom.coords[-1]
        chord_length = (
            (end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2
        ) ** 0.5

        if chord_length < 1:
            sinuosities.append(np.nan)
        else:
            sinuosities.append(round(channel_length / chord_length, 3))

    streams_gdf = streams_gdf.copy()
    streams_gdf["sinuosity"] = sinuosities
    return streams_gdf


# ---------------------------------------------------------------------------
# Aggregate cross-section measurements to reach level
# ---------------------------------------------------------------------------

def aggregate_to_reach(
    xs_geojson: str,
    streams_gdf: gpd.GeoDataFrame,
    field_data: pd.DataFrame = None,
) -> gpd.GeoDataFrame:
    """
    Aggregate cross-section measurements to reach-level representative values.

    Uses median across cross-sections (more robust than mean for morphology).
    Field data overrides LiDAR measurements where available.

    Returns GeoDataFrame with one row per reach, all Rosgen parameters attached.
    """
    xs_gdf = gpd.read_file(xs_geojson)

    # Median morphology per reach
    reach_morph = (
        xs_gdf.groupby("reach_id")[[
            "bankfull_width_m",
            "mean_bankfull_depth_m",
            "width_depth_ratio",
            "entrenchment_ratio",
            "flood_prone_width_m",
            "xs_area_m2",
        ]]
        .median()
        .round(3)
    )

    # Join to stream reaches
    reaches = streams_gdf.merge(reach_morph, on="reach_id", how="left")

    # Compute sinuosity
    reaches = compute_sinuosity(reaches)

    # Apply field data overrides
    if field_data is not None:
        for _, frow in field_data.iterrows():
            rid = frow.get("reach_id")
            if rid is None:
                continue
            mask = reaches["reach_id"] == rid
            if frow.get("bankfull_width_m") is not None:
                reaches.loc[mask, "bankfull_width_m"] = frow["bankfull_width_m"]
            if frow.get("bankfull_depth_m") is not None:
                reaches.loc[mask, "mean_bankfull_depth_m"] = frow["bankfull_depth_m"]
                reaches.loc[mask, "width_depth_ratio"] = (
                    frow["bankfull_width_m"] / frow["bankfull_depth_m"]
                    if frow.get("bankfull_width_m") else reaches.loc[mask, "width_depth_ratio"]
                )
            if frow.get("flood_prone_width_m") is not None:
                reaches.loc[mask, "flood_prone_width_m"] = frow["flood_prone_width_m"]
                reaches.loc[mask, "entrenchment_ratio"] = (
                    frow["flood_prone_width_m"] / frow["bankfull_width_m"]
                    if frow.get("bankfull_width_m") else reaches.loc[mask, "entrenchment_ratio"]
                )
            if frow.get("d50_mm") is not None:
                reaches.loc[mask, "d50_mm"] = frow["d50_mm"]
            if frow.get("sinuosity") is not None:
                reaches.loc[mask, "sinuosity"] = frow["sinuosity"]

    return reaches


# ---------------------------------------------------------------------------
# Entrenchment classification helpers
# ---------------------------------------------------------------------------

def classify_entrenchment(er: float) -> str:
    """
    Classify entrenchment ratio into Rosgen categories.
    """
    if np.isnan(er):
        return "unknown"
    if er > 2.2:
        return "slightly_entrenched"
    if er >= 1.4:
        return "moderately_entrenched"
    return "entrenched"


def classify_wd_ratio(wd: float) -> str:
    """Classify W/D ratio."""
    if np.isnan(wd):
        return "unknown"
    if wd > 40:
        return "very_wide_shallow"
    if wd > 12:
        return "wide"
    return "narrow_deep"


def classify_sinuosity(k: float) -> str:
    if np.isnan(k):
        return "unknown"
    if k > 1.5:
        return "meandering"
    if k >= 1.2:
        return "sinuous"
    return "straight"


def classify_slope(s_pct: float) -> str:
    """Classify slope category (percent)."""
    if np.isnan(s_pct):
        return "unknown"
    if s_pct > 10.0:
        return "very_steep"
    if s_pct > 4.0:
        return "steep"
    if s_pct > 2.0:
        return "moderate"
    if s_pct > 0.5:
        return "low"
    return "very_low"


# ---------------------------------------------------------------------------
# Main parameter assembly
# ---------------------------------------------------------------------------

def assemble_rosgen_parameters(
    xs_geojson: str,
    streams_geojson: str,
    output_dir: str,
    field_data_csv: str = None,
) -> str:
    """
    Assemble all Rosgen parameters into a reach-level dataset ready for classification.

    Returns path to output GeoJSON.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("\n=== Assembling Rosgen Parameters ===")

    streams = gpd.read_file(streams_geojson)
    field_data = pd.read_csv(field_data_csv) if field_data_csv else None

    reaches = aggregate_to_reach(xs_geojson, streams, field_data)

    # Add classification labels for each parameter
    reaches["entrenchment_class"] = reaches["entrenchment_ratio"].apply(classify_entrenchment)
    reaches["wd_class"] = reaches["width_depth_ratio"].apply(classify_wd_ratio)
    reaches["sinuosity_class"] = reaches["sinuosity"].apply(classify_sinuosity)
    reaches["slope_class"] = reaches["slope_pct"].apply(classify_slope)

    out_path = str(out / "rosgen_parameters.geojson")
    reaches.to_file(out_path, driver="GeoJSON")

    # Print summary table
    print("\nReach Parameter Summary:")
    print(f"{'Reach':>6} {'Order':>5} {'ER':>6} {'W/D':>6} {'K':>6} {'Slope%':>7} "
          f"{'Entrench':>18} {'W/D Class':>16} {'Sinuosity':>12}")
    print("-" * 90)
    for _, row in reaches.iterrows():
        print(
            f"{row['reach_id']:>6} "
            f"{row.get('strahler_order', '?'):>5} "
            f"{_fmt(row.get('entrenchment_ratio')):>6} "
            f"{_fmt(row.get('width_depth_ratio')):>6} "
            f"{_fmt(row.get('sinuosity')):>6} "
            f"{_fmt(row.get('slope_pct')):>7} "
            f"{str(row.get('entrenchment_class', '?')):>18} "
            f"{str(row.get('wd_class', '?')):>16} "
            f"{str(row.get('sinuosity_class', '?')):>12}"
        )

    print(f"\nRosgen parameters → {out_path}")
    return out_path


def _fmt(v) -> str:
    try:
        return f"{float(v):.2f}" if not np.isnan(float(v)) else "  —"
    except (TypeError, ValueError):
        return "  —"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble Rosgen reach parameters")
    parser.add_argument("--cross-sections", required=True,
                        help="cross_sections_measured.geojson")
    parser.add_argument("--streams", required=True,
                        help="streams_with_slope.geojson")
    parser.add_argument("--output", required=True)
    parser.add_argument("--field-data", default=None,
                        help="Optional CSV with field measurements to override LiDAR values")
    args = parser.parse_args()

    assemble_rosgen_parameters(
        args.cross_sections, args.streams, args.output, args.field_data
    )
