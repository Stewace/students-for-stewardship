# Terrain Indices for LEC Classification

## Terrain Shape Index (TSI) — McNab 1989, 1993

TSI measures whether a point on the landscape is locally convex (ridge-like) or concave (hollow-like).

**Formula:**
```
TSI = mean elevation of 8 surrounding cells − center cell elevation
```
- **Positive TSI** → center is lower than surroundings → concave (hollow, valley)
- **Negative TSI** → center is higher than surroundings → convex (ridge, knob)
- **TSI ≈ 0** → planar slope

**WhiteboxTools tool:** `terrain_shape_index`

**References:**
- McNab, W.H. 1989. Terrain shape index: quantifying effect of minor landforms on tree height. Forest Science 35(1):91–104.
- McNab, W.H. 1993. A topographic index to quantify the effect of mesoscale landform on site productivity. Canadian Journal of Forest Research 23:1100–1107.

---

## Landform Index (LI) — McNab 1993

LI integrates slope gradient with terrain shape to produce a composite landform descriptor.

**Formula:**
```
LI = TSI / (slope_gradient + 1)
```
Higher LI values → more sheltered/concave positions
Lower LI values → more exposed/convex ridges

**WhiteboxTools tool:** `landform_index` (also called `topographic_position_index` in some implementations)

---

## Slope and Aspect

**Slope** — rate of elevation change per unit distance (degrees or percent)
**Aspect** — direction the slope faces (0–360°, north = 0/360°)

These are standard DEM derivatives. In WhiteboxTools:
- `slope` — calculates slope in degrees or percent
- `aspect` — calculates aspect in degrees

**Ecological interpretation for Piedmont:**
- North/NE aspects: cooler, moister → mesic forest types
- South/SW aspects: hotter, drier → xeric forest types

---

## Profile and Plan Curvature

**Profile curvature** — curvature in the direction of slope (affects flow acceleration)
**Plan curvature** — curvature perpendicular to slope (affects flow convergence)

WhiteboxTools tools: `profile_curvature`, `plan_curvature`, `total_curvature`

---

## Variable Stack for Discriminant Analysis

Based on Hutto, Shelburne & Jones (1999), the key predictors are:

| Variable | Source | Tool |
|----------|--------|------|
| Slope position (TSI / LI) | DEM | WhiteboxTools |
| Slope gradient (degrees) | DEM | WhiteboxTools |
| Aspect (transformed) | DEM | WhiteboxTools |
| Clay horizon depth (cm) | Soil survey | Web Soil Survey / field |
| Clay % in B horizon | Soil survey | Web Soil Survey / field |
| Drainage class | Soil survey | Web Soil Survey |
| Elevation | DEM | USGS 3DEP / LiDAR |

**Aspect transformation** (for linear models — converts circular to linear):
```python
# Folded aspect — 0 = south-facing, 1 = north-facing
folded_aspect = abs(180 - abs(aspect - 225))
```

---

## Ecosystem Types (Piedmont LEC)

From Jones & Lloyd (1993) / Hutto et al. (1999), typical Piedmont LEC classes:

1. **Xeric ridges/upper slopes** — shallow soils, convex, S/SW aspects
2. **Mesic slopes** — moderate soils, intermediate position
3. **Cove/hollow positions** — deep soils, concave, N-facing, high TSI
4. **Bottomland/riparian** — alluvial soils, flat, high drainage class
5. **Upland flats** — relatively level, variable soils

The discriminant functions assign each landscape unit a class probability and a most-likely class.
