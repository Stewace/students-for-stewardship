# Field Data

## Files in this folder

### `plots/field_measurements.csv`

Field survey data at cross-section locations. This file overrides LiDAR-based
measurements in the Rosgen pipeline when provided.

**Required columns** (any can be omitted — LiDAR values used as fallback):

| Column | Units | Description |
|--------|-------|-------------|
| `reach_id` | integer | Must match reach_id in stream network GeoJSON |
| `bankfull_width_m` | meters | Bankfull width measured perpendicular to flow |
| `bankfull_depth_m` | meters | Mean bankfull depth = XS area ÷ width |
| `flood_prone_width_m` | meters | Width at 2× bankfull height above thalweg |
| `d50_mm` | mm | Median grain size (Wolman pebble count) |
| `sinuosity` | dimensionless | Measured from thalweg map or GPS track |
| `bankfull_height_m` | meters | Bankfull height above thalweg (for LiDAR override) |

**Example:**
```csv
reach_id,bankfull_width_m,bankfull_depth_m,flood_prone_width_m,d50_mm,sinuosity
12,4.5,0.45,22.0,32,1.6
13,6.2,0.52,18.5,18,1.4
17,3.1,0.38,4.2,64,1.1
```

### `training/`

Training polygons for LEC discriminant analysis. See `map-system/workflows/lec-classification.md`.

## Field Methods

### Bankfull Width and Depth (Rosgen Level II survey)

1. Establish a cross-section baseline perpendicular to flow
2. Identify bankfull stage using:
   - Top of point bar
   - Change in vegetation (grass/annual plants → woody shrubs)
   - Undercut bank top
   - Break in soil profile
3. Measure width from left bank to right bank at bankfull
4. Measure water surface elevations at 0.5m intervals across channel
5. Calculate mean depth = sum(depths × widths) ÷ total width

### Flood-Prone Width

At same cross-section:
1. Calculate bankfull height above thalweg (H = bankfull elev − thalweg elev)
2. Find elevation at 2H above thalweg
3. Measure valley width at that elevation (extend tape up valley walls)

### Pebble Count (Wolman 1954 — D50)

1. Walk channel in grid pattern (100 paces)
2. At each pace, pick up pebble under right foot — do not look
3. Measure intermediate axis (b-axis) with calipers
4. Repeat 100 times → plot frequency distribution
5. D50 = 50th percentile grain size in mm

### GPS Track for Sinuosity

1. Walk thalweg with GPS (1m accuracy minimum)
2. Export track as GPX → convert to GeoJSON
3. Sinuosity = track length ÷ straight-line distance endpoint to endpoint
4. Record in field_measurements.csv
