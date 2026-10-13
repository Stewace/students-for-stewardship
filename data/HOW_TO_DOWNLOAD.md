# How to Download LiDAR / DEM Data

The git repo does not store large raster files (they're in .gitignore).
Run these commands once on your local machine to populate data/raw/.

---

## Option 1: USGS 3DEP — South Carolina (Recommended First Step)

### Check what's available first (no download)
```bash
python data/download_lidar.py --state SC --resolution 13 --dry-run
```

### Download 1/3 arc-second DEM (~10m) for all of South Carolina
This is the best starting point for statewide LEC analysis.
Estimated size: ~1–3 GB total for SC.
```bash
python data/download_lidar.py --state SC --resolution 13
```
Output: `data/raw/dem/`

### Download 1-meter DEM for the SC Upstate / Piedmont only
Smaller area, highest resolution — best for Rosgen cross-section analysis.
Estimated size: varies by tile count (each tile ~200–500 MB).
```bash
# SC Upstate Piedmont (Greenville, Pickens, Anderson, Oconee, Spartanburg counties)
python data/download_lidar.py \
  --bbox -83.4,34.4,-81.5,35.2 \
  --resolution 1

# Hunnicutt Creek study area only (smallest download, start here)
python data/download_lidar.py \
  --bbox -82.7,34.7,-82.0,35.0 \
  --resolution 1
```

### Download 1-meter DEM for NC Piedmont (optional)
```bash
python data/download_lidar.py \
  --bbox -82.0,35.0,-80.0,36.5 \
  --resolution 1 \
  --state NC
```

### Download raw LiDAR point clouds (LAZ) — for detailed site work
WARNING: Very large files (several GB per tile). Only use for small areas.
```bash
python data/download_lidar.py \
  --bbox -82.55,34.80,-82.35,34.95 \
  --type lidar
```
Output: `data/raw/lidar/`

---

## Option 2: NEON Airborne LiDAR — Piedmont Validation Sites

NEON provides 1m LiDAR DTMs at ecological observatory sites. Use these
to validate the LEC model against sites with known ecology.

### List available sites
```bash
python data/download_neon.py --list-sites
```

### Download DTM + CHM for nearest Piedmont site
```bash
# Talladega National Forest, AL (closest NEON site to Piedmont SC)
python data/download_neon.py --site TALL --products DTM CHM --year 2022

# Oak Ridge, TN (TVA Piedmont comparison)
python data/download_neon.py --site ORNL --products DTM CHM --year 2022
```
Output: `data/raw/neon/TALL/` or `data/raw/neon/ORNL/`

---

## After Downloading: Reproject and Process

```bash
# 1. Reproject SC DEM tiles to UTM Zone 17N and mosaic
#    (run once for all downloaded tiles)
gdalbuildvrt data/raw/dem/sc_dem_mosaic.vrt data/raw/dem/*.tif
gdalwarp -t_srs EPSG:26917 -tr 10 10 -r bilinear \
  data/raw/dem/sc_dem_mosaic.vrt \
  data/processed/dem/sc_10m_utm.tif

# For 1m tiles
gdalbuildvrt data/raw/dem/upstate_dem_1m.vrt data/raw/dem/*1m*.tif
gdalwarp -t_srs EPSG:26917 -tr 1 1 -r bilinear \
  data/raw/dem/upstate_dem_1m.vrt \
  data/processed/dem/upstate_1m_utm.tif

# 2. Run terrain analysis
python map-system/stack/python/terrain_analysis.py \
  --dem data/processed/dem/sc_10m_utm.tif \
  --output data/processed/terrain/

# 3. Run full LEC + Rosgen pipeline
python run_pipeline.py \
  --dem data/processed/dem/upstate_1m_utm.tif \
  --dem-10m data/processed/dem/sc_10m_utm.tif \
  --output data/processed/
```

---

## Alternative: OpenTopography (Browser Download)

If the API script doesn't work, download manually:

1. Go to https://portal.opentopography.org/
2. Click "Find Data" → draw box over SC Piedmont
3. Select "USGS 1m DEM" or available LiDAR dataset
4. Download GeoTIFF to `data/raw/dem/`

---

## File Size Reference

| Dataset | Resolution | SC Size (approx) | Study Area Only |
|---------|-----------|-----------------|-----------------|
| USGS 3DEP 1/3 arc-sec | ~10m | 1–3 GB | ~50–200 MB |
| USGS 3DEP 1-meter | 1m | 50–200 GB | 1–5 GB |
| NEON DTM (per site) | 1m | N/A | 500 MB–2 GB |
| LiDAR point cloud (LAZ) | variable | 500+ GB | 2–20 GB |

**Recommendation:** Start with 1/3 arc-second for SC statewide,
then download 1-meter only for the Hunnicutt Creek study area.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `urllib.error.URLError` | Check internet connection |
| 404 on download URL | TNM occasionally reorganizes files; try `--dry-run` to see current URLs |
| Very slow download | Add `--max 5` to test with a few tiles first |
| Tiles don't cover study area | Use `--bbox` instead of `--state` for precise control |
| LAZ files too large | Use 1m DEM rasters instead of point clouds for this project |
