# Data Directory

This folder holds all spatial data for the LEC project.
**Do not commit large raster files to git** — add them to `.gitignore` and store locally or on a shared drive.

## Folder Structure

```
data/
├── raw/
│   ├── lidar/       ← Original LAZ/LAS point clouds (OpenTopography)
│   ├── dem/         ← Raw DEMs from USGS 3DEP (before reprojection)
│   ├── soils/       ← SSURGO download (shapefiles + tabular/)
│   └── watershed/   ← HUC boundary, stream network shapefiles
├── processed/
│   ├── dem/         ← Reprojected 10m DEM (EPSG:26917)
│   ├── terrain/     ← WhiteboxTools output rasters
│   ├── soils/       ← Rasterized soil attributes
│   └── classified/  ← Final LEC classification raster + LDA model
└── field/
    ├── plots/       ← Field plot GPS points + measurements
    └── training/    ← Training polygons/points for LDA
```

## CRS Standard

All processed data: **EPSG:26917** (UTM Zone 17N, NAD83)

## Resolution Standard

- Regional analysis: **10m** (matches USGS 3DEP 1/3 arc-second)
- Detailed site analysis: **1m** (from LiDAR)

## .gitignore for data

Add this to root `.gitignore` to avoid committing large files:
```
data/raw/
data/processed/terrain/
data/processed/dem/
data/processed/classified/*.tif
```
