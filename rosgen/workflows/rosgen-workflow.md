# Rosgen Classification Workflow

## Prerequisites
- 1m LiDAR DEM (preferred) or 10m DEM in `data/processed/dem/dem_utm.tif`
- Python environment active (`source lec-env/bin/activate`)
- Stream delineation not yet run → start at Step 1
- Stream delineation already done → start at Step 2

---

## Step 1: Delineate Stream Network

```bash
python rosgen/python/stream_delineation.py \
  --dem data/processed/dem/dem_1m_utm.tif \
  --output data/processed/streams/ \
  --threshold 500 \
  --min-order 1
```

**Threshold guidance:**
| DEM Resolution | Threshold | Min Contributing Area |
|----------------|-----------|----------------------|
| 1m | 500 | ~0.05 ha — captures small headwaters |
| 1m | 2000 | ~0.2 ha — main channel network |
| 10m | 50 | ~5 ha — regional network |
| 10m | 100 | ~10 ha — 2nd order and above |

**Outputs in `data/processed/streams/`:**
- `stream_delineation_work/streams_network.geojson` — raw network
- `streams_with_slope.geojson` — network with slope per reach ← **use this**
- `stream_delineation_work/stream_order_strahler.tif`
- `stream_delineation_work/sub_watersheds.tif`

**QA in QGIS:** Load `streams_with_slope.geojson` and compare to aerial/topo.
If too many or too few streams extracted, adjust `--threshold`.

---

## Step 2: Extract Valley Cross-Sections

```bash
python rosgen/python/valley_analysis.py \
  --dem data/processed/dem/dem_1m_utm.tif \
  --streams data/processed/streams/streams_with_slope.geojson \
  --output data/processed/rosgen/ \
  --spacing 50 \
  --width 150
```

**Spacing guidance:**
- 50m → dense; good for short reaches and detailed analysis
- 100m → standard for regional classification
- Higher order streams → use larger spacing (100–200m)

**If you have field bankfull height measurements:**
```bash
  --bankfull-height 0.75
```
(Replaces auto-detection with a known value — much more accurate)

**Outputs in `data/processed/rosgen/`:**
- `cross_sections_measured.geojson` — individual cross-section lines with measurements
- `reach_morphology_summary.csv` — median values per reach

**QA in QGIS:**
1. Load cross-sections over hillshade
2. Spot-check a few in known valleys — bankfull_width_m should look right
3. Check entrenchment_ratio — incised urban streams → ER < 1.4, floodplain streams → ER > 2.2

---

## Step 3: Compute Rosgen Parameters

```bash
python rosgen/python/rosgen_parameters.py \
  --cross-sections data/processed/rosgen/cross_sections_measured.geojson \
  --streams data/processed/streams/streams_with_slope.geojson \
  --output data/processed/rosgen/
```

**If you have field data to override LiDAR values:**
1. Create `data/field/plots/field_measurements.csv` with columns:
   `reach_id, bankfull_width_m, bankfull_depth_m, flood_prone_width_m, d50_mm, sinuosity`
2. Add `--field-data data/field/plots/field_measurements.csv`

Field data always takes precedence over LiDAR measurements.

**Output:** `data/processed/rosgen/rosgen_parameters.geojson`

---

## Step 4: Classify Reaches

```bash
python rosgen/python/rosgen_classify.py \
  --parameters data/processed/rosgen/rosgen_parameters.geojson \
  --output data/processed/rosgen/
```

**Outputs:**
- `rosgen_classified.geojson` → copy to `map-system/stack/leaflet/data/`
- `rosgen_classified_summary.csv` → tabular summary for analysis

**Review classification flags in CSV** — reaches with low confidence should be
field-checked before using in LEC training data.

---

## Step 5: Update Leaflet Map

```bash
# Copy final GeoJSON to map data folder
mkdir -p map-system/stack/leaflet/data/
cp data/processed/rosgen/rosgen_classified.geojson map-system/stack/leaflet/data/

# Serve locally to test
cd map-system/stack/leaflet/
python -m http.server 8000
# Open http://localhost:8000
```

Stream reaches will appear color-coded by Rosgen type. Click any reach to see
the full classification, LEC prediction, and restoration priority.

---

## Step 6: Integrate Rosgen → LEC Training Data

After reviewing classification:

1. Open `rosgen_classified_summary.csv`
2. Identify F and G type reaches → exclude these from bottomland LEC training polygons
   (these reaches are incised; their floodplain LEC connection is broken)
3. C and E type reaches → use their flood-prone width buffers as bottomland LEC polygons
4. Use the `lec_class_predicted` column as a starting point for LEC class assignments

**Buffer bottomland LEC from Rosgen data:**
```python
import geopandas as gpd

streams = gpd.read_file("data/processed/rosgen/rosgen_classified.geojson")

# Buffer C and E reaches by their flood-prone width / 2
floodplain = streams[streams["rosgen_type"].isin(["C", "E", "DA"])].copy()
floodplain["buffer_m"] = floodplain["flood_prone_width_m"].fillna(30) / 2
floodplain["geometry"] = floodplain.apply(
    lambda r: r.geometry.buffer(r.buffer_m), axis=1
)

floodplain.to_file(
    "data/processed/lec_training/bottomland_from_rosgen.gpkg", driver="GPKG"
)
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Cross-sections show flat profiles | DEM resolution too coarse; use 1m LiDAR DEM |
| All reaches classified as C | Sinuosity likely defaulted — digitize valley centerlines in QGIS |
| ER values all ~1.0 | Flood-prone width not detected — stream may be in narrow valley; check `--width` parameter |
| Bankfull width looks wrong | Supply `--bankfull-height` from field measurement |
| Stream network misses small tributaries | Lower `--threshold` value |
| Stream network has too many spurious lines | Raise `--threshold` or use `--min-order 2` |
