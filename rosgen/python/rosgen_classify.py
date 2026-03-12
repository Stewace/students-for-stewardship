"""
Rosgen Level I + Level II Stream Classification
Hunnicutt Creek Watershed — Piedmont SC

Applies the Rosgen classification key to each reach based on:
  - Entrenchment Ratio (ER)
  - Width/Depth Ratio (W/D)
  - Sinuosity (K)
  - Channel Slope (S%)
  - Bed Material D50 (mm) — optional

Outputs:
  - GeoJSON with Level I valley type + Level II channel type per reach
  - CSV summary for tabular analysis
  - LEC integration table (Rosgen type → predicted LEC class)

Usage:
    python rosgen_classify.py \
        --parameters path/to/rosgen_parameters.geojson \
        --output path/to/output/
"""

import argparse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import geopandas as gpd


# ---------------------------------------------------------------------------
# Rosgen Level I: Valley Type
# ---------------------------------------------------------------------------

VALLEY_TYPE_DESCRIPTIONS = {
    "I":   "Steep, V-notch, narrow confined — headwaters",
    "II":  "Moderately steep, confined colluvial",
    "III": "Moderately confined, colluvial/alluvial",
    "IV":  "Wide, alluvial fan or piedmont",
    "V":   "Wide, meandering, well-developed floodplain",
    "VI":  "Wide floodplain, very low gradient",
    "VII": "Braided, wide active channel",
    "VIII":"Tidal influenced",
}


def classify_level1_valley(slope_pct: float, er: float) -> str:
    """
    Assign Rosgen Level I valley type based on slope and entrenchment.
    Simplified key for Piedmont SC context.

    Returns valley type string (I, II, III, IV, V, VI)
    or 'unknown' if insufficient data.
    """
    if np.isnan(slope_pct) or np.isnan(er):
        return "unknown"

    # Very steep — always Type I or II regardless of entrenchment
    if slope_pct > 10.0:
        return "I"
    if slope_pct > 4.0:
        return "II"
    # Moderate gradient
    if slope_pct > 2.0:
        if er < 1.4:
            return "III"      # Confined, moderately steep
        return "IV"           # Open alluvial
    # Low gradient — depends on floodplain development
    if slope_pct > 0.5:
        if er > 2.2:
            return "V"        # Well-developed floodplain
        return "IV"
    # Very low gradient
    if er > 2.2:
        return "VI"
    return "V"


# ---------------------------------------------------------------------------
# Rosgen Level II: Stream Channel Type
# ---------------------------------------------------------------------------

STREAM_TYPE_DESCRIPTIONS = {
    "Aa+": "Extremely steep cascade; torrent; bedrock/boulder",
    "A":   "Steep cascade; bedrock/boulder dominant",
    "B":   "Moderate gradient; rapids; moderately entrenched",
    "C":   "Meandering; well-developed floodplain; riffle-pool",
    "D":   "Braided; wide, unstable active channel",
    "DA":  "Anabranching/anastomosing; very low gradient",
    "E":   "Very low gradient meandering; highly sinuous; narrow/deep",
    "F":   "Entrenched meanders; degraded; incised",
    "G":   "Incised step-pool; entrenched; moderate gradient",
}

# Ecological significance notes for Piedmont SC
STREAM_TYPE_ECOLOGY = {
    "Aa+": "Headwater cascade; high oxygen; cold water refugia",
    "A":   "Headwater; coarse substrate; salamander habitat",
    "B":   "Transitional; moderate aquatic diversity",
    "C":   "High ecological value; floodplain connection; wood turtle, hellbender habitat",
    "D":   "Unstable; low ecological value unless recovering",
    "DA":  "High ecological value; rare in Piedmont; exceptional wetland connectivity",
    "E":   "Highest ecological value; rare; meadow stream; brook trout, hellbender",
    "F":   "Degraded; restoration priority; poor floodplain connection",
    "G":   "Incised; recovery potential; restoration priority",
}


@dataclass
class RosgenType:
    level1: str                      # Valley type (I–VIII)
    level2: str                      # Channel type (A, B, C, D, DA, E, F, G, Aa+)
    confidence: str                  # high / medium / low
    lec_class_primary: str           # Primary predicted LEC class
    lec_class_notes: str             # Notes on LEC integration
    restoration_priority: str        # high / moderate / low / none
    flags: list = field(default_factory=list)  # Warning messages


def classify_level2_channel(
    er: float,
    wd: float,
    sinuosity: float,
    slope_pct: float,
    d50_mm: float = np.nan,
) -> tuple[str, str, list]:
    """
    Classify Level II stream channel type using Rosgen's decision key.

    Returns (stream_type, confidence, flags)
    """
    flags = []

    # Handle missing data
    if np.isnan(er):
        flags.append("ER missing — using LiDAR estimate may be unreliable")
        er = 1.5  # assume moderate if unknown
    if np.isnan(wd):
        flags.append("W/D missing")
        wd = 20.0  # assume intermediate
    if np.isnan(sinuosity):
        flags.append("Sinuosity unmeasured — digitize valley centerline for accuracy")
        sinuosity = 1.3  # assume sinuous
    if np.isnan(slope_pct):
        flags.append("Slope not computed")
        slope_pct = 1.0

    # Track how many parameters were estimated
    n_estimated = len(flags)
    confidence = "high" if n_estimated == 0 else ("medium" if n_estimated <= 2 else "low")

    # --- Classification logic (Rosgen 1994, 1996) ---

    # Aa+ and A: very steep, entrenched, narrow/deep, straight
    if slope_pct > 10.0:
        return ("Aa+", confidence, flags) if slope_pct > 20 else ("A", confidence, flags)

    if slope_pct > 4.0:
        if er < 1.4 and wd < 12 and sinuosity < 1.2:
            return "A", confidence, flags
        if er < 1.4 and sinuosity < 1.5:
            return "B", confidence, flags

    # B: moderate gradient, moderately entrenched, intermediate W/D, sinuous
    if 2.0 < slope_pct <= 4.0:
        if er < 1.4 and sinuosity < 1.5:
            return "B", confidence, flags

    # G: incised step-pool, moderate gradient
    if 2.0 <= slope_pct <= 4.0 and er < 1.4 and sinuosity > 1.5 and wd < 12:
        return "G", confidence, flags

    # F: entrenched meanders, low gradient — degraded
    if er < 1.4 and wd > 12 and sinuosity > 1.5 and slope_pct < 2.0:
        flags.append("Reach appears incised/degraded — restoration assessment recommended")
        return "F", confidence, flags

    # C: classic Piedmont meandering reach
    if er > 2.2 and wd > 12 and sinuosity > 1.5 and slope_pct < 2.0:
        return "C", confidence, flags

    # E: very sinuous, low gradient, narrow/deep, not entrenched — meadow stream
    if er > 2.2 and wd < 12 and sinuosity > 1.5 and slope_pct < 2.0:
        return "E", confidence, flags

    # D: braided, wide, unstable
    if er > 2.2 and wd > 40 and sinuosity < 1.5:
        flags.append("Braided reach — check for active bank instability")
        return "D", confidence, flags

    # DA: anabranching
    if er > 2.2 and wd > 40 and slope_pct < 0.5:
        return "DA", confidence, flags

    # B: catch-all moderate gradient
    if 1.0 < slope_pct <= 4.0:
        return "B", confidence, flags

    # C: catch-all low gradient with floodplain
    if er > 1.4 and sinuosity > 1.2:
        return "C", confidence, flags

    # G: incised fallback
    if er < 1.4:
        flags.append("Entrenched reach — verify with field survey")
        return "G", confidence, flags

    return "C", "low", flags + ["Could not confidently classify — defaulted to C"]


# ---------------------------------------------------------------------------
# LEC integration
# ---------------------------------------------------------------------------

LEC_FROM_ROSGEN = {
    "Aa+": ("Xeric Ridge / Upper Slope",
             "Headwater cascade; LEC class driven by upland slopes, not channel"),
    "A":   ("Mesic Slope",
             "Headwater reach; thin soils; transitional to upland LEC"),
    "B":   ("Mesic Slope",
             "Moderate gradient; valley LEC similar to adjacent slopes"),
    "C":   ("Bottomland / Riparian",
             "Well-developed floodplain; deep alluvial soils; primary bottomland LEC"),
    "D":   ("Bottomland (disturbed)",
             "Unstable; exclude from LEC training data or flag as disturbed class"),
    "DA":  ("Bottomland / Riparian",
             "High connectivity; exceptional LEC value; map floodplain carefully"),
    "E":   ("Bottomland / Riparian",
             "Highest LEC value; narrow but very high quality riparian strip"),
    "F":   ("Dry-Mesic Slope",
             "Incised; poor floodplain connection; LEC similar to slopes above"),
    "G":   ("Dry-Mesic Slope",
             "Incised step-pool; restoration target; LEC transitional"),
}

RESTORATION_PRIORITY = {
    "Aa+": "none",
    "A":   "low",
    "B":   "low",
    "C":   "none",
    "D":   "high",
    "DA":  "none",
    "E":   "none",
    "F":   "high",
    "G":   "moderate",
}


def classify_reach(
    er: float,
    wd: float,
    sinuosity: float,
    slope_pct: float,
    d50_mm: float = np.nan,
) -> RosgenType:
    """
    Full Rosgen classification for a single reach.
    """
    l1 = classify_level1_valley(slope_pct, er)
    l2, confidence, flags = classify_level2_channel(er, wd, sinuosity, slope_pct, d50_mm)

    lec_primary, lec_notes = LEC_FROM_ROSGEN.get(l2, ("unknown", ""))
    restoration = RESTORATION_PRIORITY.get(l2, "unknown")

    return RosgenType(
        level1=l1,
        level2=l2,
        confidence=confidence,
        lec_class_primary=lec_primary,
        lec_class_notes=lec_notes,
        restoration_priority=restoration,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# Classify all reaches
# ---------------------------------------------------------------------------

def classify_all_reaches(params_geojson: str, output_dir: str) -> str:
    """
    Run Rosgen classification for every reach in the parameters GeoJSON.
    Adds classification columns and exports results.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("\n=== Rosgen Level I + II Classification ===\n")
    gdf = gpd.read_file(params_geojson)

    level1_list = []
    level2_list = []
    confidence_list = []
    lec_primary_list = []
    lec_notes_list = []
    restoration_list = []
    flags_list = []

    for _, row in gdf.iterrows():
        result = classify_reach(
            er=row.get("entrenchment_ratio", np.nan),
            wd=row.get("width_depth_ratio", np.nan),
            sinuosity=row.get("sinuosity", np.nan),
            slope_pct=row.get("slope_pct", np.nan),
            d50_mm=row.get("d50_mm", np.nan),
        )
        level1_list.append(result.level1)
        level2_list.append(result.level2)
        confidence_list.append(result.confidence)
        lec_primary_list.append(result.lec_class_primary)
        lec_notes_list.append(result.lec_class_notes)
        restoration_list.append(result.restoration_priority)
        flags_list.append("; ".join(result.flags) if result.flags else "")

    gdf["rosgen_valley"] = level1_list
    gdf["rosgen_type"] = level2_list
    gdf["classification_confidence"] = confidence_list
    gdf["lec_class_predicted"] = lec_primary_list
    gdf["lec_integration_notes"] = lec_notes_list
    gdf["restoration_priority"] = restoration_list
    gdf["classification_flags"] = flags_list

    # GeoJSON output (for Leaflet map)
    geojson_path = str(out / "rosgen_classified.geojson")
    gdf.to_file(geojson_path, driver="GeoJSON")

    # CSV summary (for tabular analysis)
    csv_path = str(out / "rosgen_classified_summary.csv")
    summary_cols = [
        "reach_id", "strahler_order", "slope_pct", "sinuosity",
        "entrenchment_ratio", "width_depth_ratio",
        "rosgen_valley", "rosgen_type", "classification_confidence",
        "lec_class_predicted", "restoration_priority", "classification_flags"
    ]
    available = [c for c in summary_cols if c in gdf.columns]
    gdf[available].to_csv(csv_path, index=False)

    # Print summary
    print(f"{'Reach':>6} {'Order':>5} {'L-I':>4} {'L-II':>5} {'Confidence':>10} "
          f"{'Slope%':>7} {'ER':>6} {'W/D':>6} {'K':>6} {'Restoration':>12}")
    print("-" * 80)
    for _, row in gdf.iterrows():
        print(
            f"{row['reach_id']:>6} "
            f"{str(row.get('strahler_order', '?')):>5} "
            f"{row['rosgen_valley']:>4} "
            f"{row['rosgen_type']:>5} "
            f"{row['classification_confidence']:>10} "
            f"{_fmt(row.get('slope_pct')):>7} "
            f"{_fmt(row.get('entrenchment_ratio')):>6} "
            f"{_fmt(row.get('width_depth_ratio')):>6} "
            f"{_fmt(row.get('sinuosity')):>6} "
            f"{row['restoration_priority']:>12}"
        )

    # Type frequency summary
    print("\n--- Type Distribution ---")
    for t, count in gdf["rosgen_type"].value_counts().items():
        desc = STREAM_TYPE_DESCRIPTIONS.get(t, "")
        print(f"  {t:4s} × {count:2d} — {desc}")

    print(f"\nClassification GeoJSON → {geojson_path}")
    print(f"Summary CSV → {csv_path}")
    return geojson_path


def _fmt(v) -> str:
    try:
        return f"{float(v):.2f}" if not np.isnan(float(v)) else "  —"
    except (TypeError, ValueError):
        return "  —"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rosgen Level I + II classification")
    parser.add_argument("--parameters", required=True,
                        help="rosgen_parameters.geojson from rosgen_parameters.py")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    classify_all_reaches(args.parameters, args.output)
