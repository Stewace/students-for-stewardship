# Stack Setup Instructions

## 1. Install QGIS

Download QGIS 3.28 LTS from https://qgis.org/en/site/forusers/download.html

After install, add these plugins via Plugins → Manage:
- **WhiteboxTools for Processing** — connects WhiteboxTools to QGIS Processing Toolbox
- **PDAL Wrench** — LiDAR point cloud operations

---

## 2. Install Python Environment

```bash
# Create a virtual environment
python -m venv lec-env
source lec-env/bin/activate   # Mac/Linux
# OR
lec-env\Scripts\activate       # Windows

# Install dependencies
pip install -r requirements.txt
```

---

## 3. Install WhiteboxTools Binary

```bash
# Via pip (installs Python wrapper + downloads binary automatically)
pip install whitebox

# Test it
python -c "import whitebox; wbt = whitebox.WhiteboxTools(); print(wbt.version())"
```

---

## 4. Verify GDAL

```bash
# Check GDAL is available (usually installed with rasterio)
python -c "import rasterio; print(rasterio.__version__)"
gdalinfo --version
```

---

## 5. Data Downloads

### LiDAR / DEM
1. Go to https://portal.opentopography.org/
2. Search for "South Carolina Piedmont" or draw a box around Hunnicutt Creek
3. Download 1m DEM or LAZ point cloud
4. Save to `../data/raw/lidar/`

### Soils
1. Go to https://websoilsurvey.sc.egov.usda.gov/
2. Draw area of interest
3. Download SSURGO data (includes shapefile + tabular data)
4. Save to `../data/raw/soils/`

### Watershed Boundary
1. Go to https://streamstats.usgs.gov/
2. Delineate Hunnicutt Creek watershed
3. Download boundary shapefile
4. Save to `../data/raw/watershed/`

---

## 6. Folder Structure for Data

```
data/
├── raw/
│   ├── lidar/          ← LAZ or LAS files from OpenTopography
│   ├── dem/            ← GeoTIFF DEMs from USGS 3DEP
│   ├── soils/          ← SSURGO shapefiles + tabular data
│   └── watershed/      ← HUC boundaries, stream network
├── processed/
│   ├── terrain/        ← WhiteboxTools output rasters (slope, TSI, etc.)
│   ├── soils/          ← Rasterized soil attributes
│   └── classified/     ← Final LEC classification rasters
└── field/
    ├── plots/          ← Field plot locations and measurements
    └── training/       ← Training polygons for LEC classes
```
