# Workflow Guide — Claude Instructions

This folder contains step-by-step directions for recurring tasks in this project.
Drop any of these files into a conversation with Claude as context to get targeted help.

---

## Files in This Folder

| File | When to use |
|------|------------|
| `data-pipeline.md` | Loading new LiDAR/DEM data → processed terrain rasters |
| `lec-classification.md` | Running discriminant analysis → LEC class raster |

---

## How to Use These with Claude

**Starting a new session:**
> "I'm working on the LEC project. Here's the workflow doc: [paste data-pipeline.md].
> I have a new LAZ file at [path]. Walk me through the pipeline."

**Asking Claude to write code:**
> "Using the stack in map-system/stack/python/terrain_analysis.py as a base,
> write a script that reads soil data from SSURGO and rasterizes the clay depth field."

**Debugging:**
> "Here's the error I'm getting from WhiteboxTools [paste error].
> My DEM is at [path] and I'm running the terrain_analysis.py script."

---

## Project Conventions

- All paths relative to the repo root: `data/`, `map-system/`, etc.
- All rasters in **EPSG:26917** (UTM Zone 17N) — matches Piedmont SC
- All rasters at **10m resolution** unless working with detailed LiDAR (1m)
- Output rasters named descriptively: `slope_10m.tif`, `tsi_10m.tif`, etc.
- Python scripts live in `map-system/stack/python/`
- Web maps live in `map-system/stack/leaflet/`
