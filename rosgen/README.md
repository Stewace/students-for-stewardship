# Rosgen Stream & Valley Classification

## What This Is

David Rosgen's natural channel classification system assigns streams a **valley type** (Level I)
and a **channel type** (Level II) based on measurable morphological parameters.

For this project, Rosgen analysis:
1. Classifies each reach of Hunnicutt Creek and tributaries
2. Directly informs the **bottomland / riparian LEC class** assignments
3. Enables restoration planning and hydrogeomorphic condition assessment

---

## Integration with LEC

| Rosgen Type | Dominant LEC Class | Notes |
|-------------|-------------------|-------|
| C, E (low gradient, well-developed floodplain) | Bottomland / Riparian | Most productive; high clay depth |
| B (moderate gradient, rapids) | Mesic Slope | Transitional, confined valley |
| A (steep cascade) | Xeric Ridge / Upper Slope | Headwater, thin soils |
| F, G (entrenched) | Dry-Mesic Slope | Degraded; often human-altered |
| D, DA (braided) | Bottomland (disturbed) | Instability indicator |

---

## Folder Structure

```
rosgen/
├── README.md                       ← You are here
├── research/
│   └── rosgen-classification.md    ← Keys, parameters, reference tables
├── python/
│   ├── stream_delineation.py       ← DEM → stream network (WhiteboxTools)
│   ├── valley_analysis.py          ← Cross-sections, valley width, flood-prone width
│   ├── rosgen_parameters.py        ← W/D ratio, entrenchment ratio, sinuosity, slope
│   └── rosgen_classify.py          ← Level I + Level II classification logic
└── workflows/
    └── rosgen-workflow.md          ← Step-by-step guide for Claude sessions
```

---

## Key Parameters

| Parameter | Abbreviation | How Measured |
|-----------|-------------|-------------|
| Bankfull width | Wbkf | Field survey or LiDAR cross-section |
| Bankfull depth | Dbkf | Field survey (mean depth) |
| Flood-prone width | Wpf | LiDAR cross-section at 2x bankfull height |
| Entrenchment ratio | ER = Wpf / Wbkf | Calculated |
| Width/depth ratio | W/D = Wbkf / Dbkf | Calculated |
| Sinuosity | K = channel length / valley length | GIS measurement |
| Channel slope | S | Rise/run from DEM along thalweg |
| Bed material D50 | D50 | Field pebble count |

---

## Data Requirements

- 1m LiDAR DEM (for cross-sections and bankfull identification)
- Field measurements at representative cross-sections (optional but preferred)
- Stream centerline (extracted from DEM or digitized)
- Valley floor polygon (digitized or extracted from flat-area analysis)
