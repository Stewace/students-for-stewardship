# Map System — Landscape Ecosystem Classification (LEC)

## Chosen Stack (No Esri Required)

| Layer | Tool | Why |
|-------|------|-----|
| Terrain analysis | **WhiteboxTools** + Python | Best free tool for TSI, Landform Index, slope, aspect, curvature |
| Desktop GIS | **QGIS 3.28+ LTR** | LiDAR loading, DEM generation, visual QA |
| Data wrangling | **Python** (rasterio, geopandas, numpy) | Scriptable, reproducible, version-controllable |
| Classification | **scikit-learn** (LinearDiscriminantAnalysis) | Mirrors Jones/Hutto discriminant analysis methodology |
| Web maps | **Leaflet.js** | Lightweight, raster-tile-optimized, works on any host |
| LiDAR pre-processing | **PDAL** or QGIS native | LAZ/LAS → DEM conversion |

This is a fully free, open-source, publishable-quality stack.

---

## Folder Guide

```
map-system/
├── README.md                  ← You are here — overview and decisions
├── research/
│   ├── stack-comparison.md    ← Why this stack vs. alternatives
│   ├── terrain-indices.md     ← TSI, Landform Index, slope formulas
│   └── lec-methodology.md     ← Jones/Hutto LEC framework reference
├── stack/
│   ├── setup.md               ← Install instructions for the whole stack
│   ├── python/
│   │   ├── requirements.txt   ← All Python dependencies
│   │   └── terrain_analysis.py← WhiteboxTools terrain pipeline script
│   └── leaflet/
│       └── index.html         ← Starter interactive web map
└── workflows/
    ├── README.md              ← Claude workflow instructions
    ├── data-pipeline.md       ← Raw LiDAR → classified raster steps
    └── lec-classification.md  ← Discriminant analysis workflow
```

---

## Project Context

We are digitizing the **Landscape Ecosystem Classification (LEC)** framework from:

- **Jones & Lloyd (1993)** — original LEC theory (Defining Sustainable Forestry, Island Press)
- **Hutto, Shelburne & Jones (1999)** — discriminant analysis applied to Blue Ridge/Piedmont (Forest Ecology and Management 114:385–393)
- **McNab (1989, 1993)** — Terrain Shape Index and Landform Index formulas

The goal is to build a **GIS-based Piedmont landform classifier** using:
1. LiDAR-derived DEMs
2. Soil data (clay depth, clay %, drainage class)
3. Terrain indices (TSI, LI, slope, aspect)
4. Stepwise discriminant analysis to predict ecosystem type

Study area: **Hunnicutt Creek watershed** and surrounding Piedmont of South Carolina.
