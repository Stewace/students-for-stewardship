# Landscape Ecosystem Classification (LEC) Methodology

## Overview

The LEC framework classifies land areas into ecologically meaningful units based on the physical environment — primarily topography, soils, and hydrology. Each unit predicts a characteristic plant community and site productivity.

**Original framework:** Jones & Lloyd (1993), applied to southeastern US forests.
**Piedmont/Blue Ridge application:** Hutto, Shelburne & Jones (1999).

---

## Key Publications to Obtain

1. **Jones, S.M. and Lloyd, F.T. (1993)**
   "Landscape ecosystem classification: the first step toward ecosystem management in the southeastern United States"
   In: *Defining Sustainable Forestry*, Island Press, Washington DC, pp. 181–201.
   → *Contact: Victor B. Shelburne, Dept. of Forestry & Environmental Conservation, Clemson University*

2. **Hutto, C.J., Shelburne, V.B., and Jones, S.M. (1999)**
   "Preliminary ecological land classification of the Chauga Ridges region of South Carolina"
   *Forest Ecology and Management* 114:385–393.
   → *Available via ResearchGate or Forest Ecology and Management journal archive*

3. **McNab, W.H. (1989)**
   "Terrain shape index: quantifying effect of minor landforms on tree height"
   *Forest Science* 35(1):91–104.
   → *Available via USDA Forest Service publications archive*

4. **McNab, W.H. (1993)**
   "A topographic index to quantify the effect of mesoscale landform on site productivity"
   *Canadian Journal of Forest Research* 23:1100–1107.
   → *Available via NRC Research Press*

5. **Gattis, J.T. (1992)**
   "Landscape ecosystem classification of the Highlands Ranger District, Nantahala National Forest in North Carolina"
   MSc Thesis, Clemson University.
   → *Contact Clemson libraries (open.clemson.edu)*

6. **Cole, B.G. (1995)**
   "Landscape Ecosystem Classification of Forested Wetlands in the Upper Edisto Basin of South Carolina"
   MSc Thesis, Clemson University.
   → *Available at open.clemson.edu*

---

## Statistical Approach

### Stepwise Discriminant Analysis (SDA)

Used to identify which environmental variables best separate the LEC classes.

**Steps:**
1. Establish training polygons for each known LEC class (field data)
2. Extract terrain + soil variable values at training locations
3. Run stepwise SDA to identify most powerful predictors
4. Build discriminant functions for each class
5. Apply functions to entire study area raster stack
6. Assign each pixel to most probable LEC class

**scikit-learn implementation:**
```python
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
lda = LinearDiscriminantAnalysis()
lda.fit(X_train, y_train)
predictions = lda.predict(X_raster_stack)
```

### Detrended Canonical Correspondence Analysis (DCCA)

Ordination method to visualize relationships between vegetation composition and environmental gradients.

Used to validate that LEC classes correspond to distinct plant communities.

**Python tool:** `scikit-bio` or R `vegan` package

---

## Modern Digitization Plan

This project digitizes the LEC framework into a fully GIS-based, reproducible pipeline:

```
Phase 1: Data Assembly
  - USGS 3DEP LiDAR → DEM (10m or 1m resolution)
  - SSURGO soils data → soil attribute rasters
  - Field validation plots at Hunnicutt Creek

Phase 2: Terrain Analysis
  - WhiteboxTools: slope, aspect, TSI, LI, curvature
  - Export raster stack (GeoTIFF, one band per variable)

Phase 3: Classification
  - Training data from field plots + historical LEC maps
  - scikit-learn LDA → discriminant functions
  - Predict LEC class for every pixel in study area

Phase 4: Validation
  - Compare predictions to field-verified ecosystem types
  - Calculate accuracy metrics (kappa, overall accuracy)

Phase 5: Web Visualization
  - Publish classified map + terrain layers via Leaflet.js
  - Allow users to click any point → view predicted LEC class
```

---

## Contact for Original Data

| Person | Institution | Role |
|--------|------------|------|
| Victor B. Shelburne | Clemson Forestry & Env. Conservation | Co-author, Hutto et al. 1999 |
| Steve Jones | (formerly Clemson / USDA FS) | Framework originator |
| W.H. McNab | USDA Forest Service (Southern Research Station) | TSI/LI formula developer |
