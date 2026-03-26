# Data Pipeline — LiDAR/DEM → Terrain Rasters

## Overview

```
Raw data (LiDAR LAZ or DEM GeoTIFF)
    ↓ QGIS or PDAL
DEM GeoTIFF (10m or 1m, projected)
    ↓ terrain_analysis.py
Terrain rasters (slope, aspect, TSI, TPI, curvature)
    ↓ manual step
Soil attribute rasters (clay depth, clay %, drainage)
    ↓ lec-classification.py (next workflow)
LEC classified raster
```

---

## Step 1: Get LiDAR or DEM Data

### Option A: Download DEM directly (easier)
1. Go to https://apps.nationalmap.gov/downloader/
2. Select "Elevation Products (3DEP)" → "1 Arc-second DEM"
3. Draw box around study area
4. Download GeoTIFF
5. Save to `data/raw/dem/`

### Option B: Download LiDAR point cloud (higher resolution)
1. Go to https://portal.opentopography.org/
2. Select "Point Cloud Data"
3. Draw area of interest over Piedmont SC
4. Download LAZ format
5. Save to `data/raw/lidar/`

---

## Step 2: Convert LiDAR to DEM (skip if you got a DEM directly)

### In QGIS:
1. Drag LAZ file into QGIS
2. Processing → Toolbox → search "LAS to DEM"
3. Set cell size = 1m (or 10m for regional analysis)
4. Output: `data/raw/dem/dem_1m.tif`

### In command line (PDAL):
```bash
pdal pipeline lidar_to_dem.json
```

Where `lidar_to_dem.json` contains:
```json
{
  "pipeline": [
    "data/raw/lidar/input.laz",
    {
      "type": "filters.ground",
      "max_window_size": 33,
      "max_distance": 2.5
    },
    {
      "filename": "data/raw/dem/dem_1m.tif",
      "gdaldriver": "GTiff",
      "output_type": "mean",
      "resolution": 1.0,
      "type": "writers.gdal"
    }
  ]
}
```

---

## Step 3: Reproject and Resample DEM

Make sure the DEM is in **UTM Zone 17N (EPSG:26917)** and at **10m resolution**:

```bash
# Reproject + resample to 10m UTM
gdalwarp -t_srs EPSG:26917 -tr 10 10 -r bilinear \
  data/raw/dem/dem_raw.tif data/processed/dem/dem_10m_utm.tif
```

---

## Step 4: Run Terrain Analysis

```bash
cd map-system/stack/python
source ../../lec-env/bin/activate

python terrain_analysis.py \
  --dem ../../../data/processed/dem/dem_10m_utm.tif \
  --output ../../../data/processed/terrain/
```

**Expected outputs in `data/processed/terrain/`:**
- `slope.tif` — slope in degrees
- `aspect.tif` — aspect in degrees (0 = north)
- `aspect_folded.tif` — heat load index (0 = SW hot, 180 = NE cool)
- `terrain_shape_index.tif` — TSI (+ = concave, - = convex)
- `topographic_position_index.tif` — TPI / Landform Index
- `profile_curvature.tif`
- `plan_curvature.tif`
- `hillshade.tif` — visualization only

---

## Step 5: Get and Rasterize Soil Data

### Download SSURGO soils
1. Go to https://websoilsurvey.sc.egov.usda.gov/
2. Define area of interest matching your DEM extent
3. Download SSURGO data (ZIP with shapefile + tabular data)
4. Extract to `data/raw/soils/`

### Rasterize key attributes
The SSURGO download includes `mapunit` shapefile + tabular data in `tabular/` folder.

Key fields to extract:
- `claytotal_r` — clay % in B horizon
- `depth_to_restrictive` or `hzdept_r/hzdepb_r` — horizon depths
- `drainagecl` — drainage class (encoded as integer: 1=very poorly drained → 7=excessively drained)

Use QGIS or geopandas to join tabular data to shapefile, then rasterize.

---

## Step 6: Quality Check in QGIS

1. Load all terrain rasters into QGIS
2. Verify:
   - No-data edges look clean (not bleeding into valid area)
   - TSI values make sense (ridges = negative, valleys = positive)
   - Slope range reasonable for Piedmont (0–40°)
3. Compare hillshade with known topographic features

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| WhiteboxTools "file not found" | Check that DEM path has no spaces; use absolute paths |
| Nodata bleeding at edges | Use `gdalwarp -cutline` to clip to watershed boundary first |
| CRS mismatch errors | Check all inputs are in same CRS with `gdalinfo file.tif` |
| Memory error on large DEM | Tile the DEM first with `gdal_retile.py`, process tiles |
