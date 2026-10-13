# LEC Classification Workflow — Discriminant Analysis

## Prerequisites

- All terrain rasters completed (see `data-pipeline.md`)
- Soil attribute rasters completed
- Field plot data collected OR training polygons digitized in QGIS

---

## Step 1: Prepare Training Data

Training data tells the model which areas belong to which LEC class.

### Option A: Use field plots
- CSV with columns: `plot_id`, `latitude`, `longitude`, `lec_class`
- Extract terrain + soil values at each point using rasterio
- `lec_class` values: 1=xeric_ridge, 2=dry_mesic, 3=mesic, 4=cove, 5=bottomland, 6=upland_flat

### Option B: Digitize training polygons in QGIS
1. Load hillshade + slope + topographic map
2. Create new polygon layer with field `lec_class` (integer)
3. Digitize representative areas for each LEC class
4. Export as `data/field/training/training_polygons.gpkg`

---

## Step 2: Extract Predictor Values at Training Locations

```python
import numpy as np
import pandas as pd
import rasterio
import geopandas as gpd
from rasterio.sample import sample_gen

# Load training points
training = gpd.read_file("data/field/training/training_points.gpkg")
coords = [(row.geometry.x, row.geometry.y) for _, row in training.iterrows()]

# Define predictor rasters
predictors = {
    "slope":            "data/processed/terrain/slope.tif",
    "aspect_folded":    "data/processed/terrain/aspect_folded.tif",
    "tsi":              "data/processed/terrain/terrain_shape_index.tif",
    "tpi":              "data/processed/terrain/topographic_position_index.tif",
    "profile_curv":     "data/processed/terrain/profile_curvature.tif",
    "elevation":        "data/processed/dem/dem_10m_utm.tif",
    "clay_depth":       "data/processed/soils/clay_depth.tif",
    "clay_pct_b":       "data/processed/soils/clay_pct_b.tif",
    "drainage_class":   "data/processed/soils/drainage_class.tif",
}

# Extract values
rows = []
for name, path in predictors.items():
    with rasterio.open(path) as src:
        values = [v[0] for v in src.sample(coords)]
    training[name] = values

training.to_csv("data/field/training/training_extracted.csv", index=False)
print("Training data extracted.")
```

---

## Step 3: Run Linear Discriminant Analysis

```python
import pandas as pd
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import LabelEncoder
import joblib

# Load training data
df = pd.read_csv("data/field/training/training_extracted.csv")
df = df.dropna()  # drop rows with nodata values

feature_cols = ["slope", "aspect_folded", "tsi", "tpi",
                "profile_curv", "elevation", "clay_depth",
                "clay_pct_b", "drainage_class"]

X = df[feature_cols].values
y = df["lec_class"].values

# Fit LDA
lda = LinearDiscriminantAnalysis()
lda.fit(X, y)

# Cross-validation accuracy
scores = cross_val_score(lda, X, y, cv=5)
print(f"Cross-validation accuracy: {scores.mean():.2f} ± {scores.std():.2f}")

# Save model
joblib.dump(lda, "data/processed/classified/lda_model.pkl")
print("Model saved.")
```

---

## Step 4: Classify the Full Study Area

```python
import numpy as np
import rasterio
import joblib

lda = joblib.load("data/processed/classified/lda_model.pkl")

feature_cols = ["slope", "aspect_folded", "tsi", "tpi",
                "profile_curv", "elevation", "clay_depth",
                "clay_pct_b", "drainage_class"]

raster_paths = {
    "slope":          "data/processed/terrain/slope.tif",
    "aspect_folded":  "data/processed/terrain/aspect_folded.tif",
    "tsi":            "data/processed/terrain/terrain_shape_index.tif",
    "tpi":            "data/processed/terrain/topographic_position_index.tif",
    "profile_curv":   "data/processed/terrain/profile_curvature.tif",
    "elevation":      "data/processed/dem/dem_10m_utm.tif",
    "clay_depth":     "data/processed/soils/clay_depth.tif",
    "clay_pct_b":     "data/processed/soils/clay_pct_b.tif",
    "drainage_class": "data/processed/soils/drainage_class.tif",
}

# Read all bands into array
bands = []
profile = None
for col in feature_cols:
    with rasterio.open(raster_paths[col]) as src:
        bands.append(src.read(1).astype(float))
        if profile is None:
            profile = src.profile
            nodata = src.nodata or -9999
            shape = src.shape

stack = np.stack(bands, axis=-1)  # shape: (rows, cols, n_features)
rows, cols, n_feat = stack.shape

# Flatten to 2D, mask nodata
flat = stack.reshape(-1, n_feat)
valid_mask = ~np.any(flat == nodata, axis=1)

# Predict
predictions = np.full(rows * cols, 0, dtype=np.int8)
predictions[valid_mask] = lda.predict(flat[valid_mask])
classified = predictions.reshape(rows, cols)

# Write output
profile.update(dtype="int8", count=1, nodata=0)
with rasterio.open("data/processed/classified/lec_classified.tif", "w", **profile) as dst:
    dst.write(classified, 1)

print("Classification complete: data/processed/classified/lec_classified.tif")
```

---

## Step 5: Validate Results

1. Load `lec_classified.tif` into QGIS
2. Apply color ramp: 1=red, 2=orange, 3=green, 4=blue, 5=teal, 6=gray
3. Visually compare to:
   - Hillshade (do ridges show as xeric? valleys as cove/bottomland?)
   - USGS topo map (do bottomlands match stream valleys?)
4. Compare against field plots not used in training
5. Calculate accuracy: see confusion matrix in cross-validation output

---

## Step 6: Generate Tiles for Leaflet Map

```bash
# Convert classified raster to PNG tiles for Leaflet
gdal2tiles.py \
  --zoom=10-16 \
  --resampling=near \
  --webviewer=none \
  data/processed/classified/lec_classified.tif \
  map-system/stack/leaflet/tiles/lec_classified/

# Also generate hillshade tiles
gdal2tiles.py \
  --zoom=10-16 \
  --resampling=bilinear \
  --webviewer=none \
  data/processed/terrain/hillshade.tif \
  map-system/stack/leaflet/tiles/hillshade/
```

Then open `map-system/stack/leaflet/index.html` in a browser
(serve locally with `python -m http.server 8000`).
