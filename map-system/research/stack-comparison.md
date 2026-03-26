# Map Stack Comparison

## The Short Answer

**Use: QGIS + WhiteboxTools + Python + Leaflet.js**

No Esri license required. Everything is free and open-source.

---

## Option Breakdown

### WhiteboxTools (WINNER for terrain morphometry)
- Built in Rust — very fast, 445+ tools
- Has direct implementations of: Terrain Shape Index, Landform Index, slope, aspect, curvature, Topographic Position Index
- Python interface: `whitebox` package on pip
- Runs as a standalone binary — no QGIS required
- MIT license — use in publications freely
- **This is your core terrain engine.**

### QGIS 3.28+ LTR
- Load LiDAR point clouds (LAZ/LAS) directly — no conversion needed
- Generate DEMs from point clouds via built-in tools
- Visual QA of terrain rasters
- Run WhiteboxTools via Processing Toolbox
- Export styled maps for publication
- **Use this as your desktop interface.**

### Python Stack
```
rasterio     — read/write GeoTIFF rasters
geopandas    — vector data (soil polygons, field plots)
numpy        — array math
scikit-learn — discriminant analysis (LDA/QDA)
whitebox     — WhiteboxTools Python wrapper
matplotlib   — charts and plots
pandas       — tabular data (field measurements)
```

### Leaflet.js
- JavaScript library for interactive web maps
- Handles raster tile layers (your terrain products, hillshade, slope maps)
- Handles GeoJSON vectors (soil polygons, watershed boundaries)
- Works on any static host (GitHub Pages, Netlify, local)
- Much simpler than MapLibre when you're working primarily with rasters

### Google Earth Engine (supplemental)
- Great for rapid prototyping with national LiDAR (NEON, GEDI)
- Validate your Piedmont model against NEON datasets
- Cannot replace local processing — use as a cross-check tool only

---

## What NOT to Use

| Tool | Why Skip |
|------|----------|
| ArcGIS / ArcPy | Requires Esri license |
| Mapbox | Requires API key + paid tier at scale |
| OpenLayers | More complex than Leaflet with no added benefit for rasters |
| PostGIS | Overkill until you're serving dynamic queries to many users |

---

## Data Sources (Free)

| Data Type | Source | URL |
|-----------|--------|-----|
| LiDAR point clouds | OpenTopography (NSF) | opentopography.org |
| High-res DEMs | USGS 3DEP | nationalmap.gov |
| Soils | USDA Web Soil Survey | websoilsurvey.sc.egov.usda.gov |
| Vegetation / Land cover | SC DNR GIS data | sc.gov/dnr |
| Streams / Watersheds | USGS StreamStats | streamstats.usgs.gov |
| NEON ecological data | NEON Science | neonscience.org |
