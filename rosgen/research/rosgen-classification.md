# Rosgen Classification Reference

## Source

Rosgen, D.L. (1994). A classification of natural rivers. *Catena* 22:169–199.
Rosgen, D.L. (1996). *Applied River Morphology*. Wildland Hydrology, Pagosa Springs, CO.
Rosgen, D.L. and Silvey, H.L. (1996). *Field Guide for Stream Classification*. Wildland Hydrology.

---

## Level I — Valley Type Classification

Valley type is determined by **valley slope** and **degree of valley confinement / entrenchment**.

| Valley Type | Slope | Description | Typical Landform |
|-------------|-------|-------------|-----------------|
| I | >4% | Very steep, V-notch, narrow confined | Mountain headwaters |
| II | 2–4% | Moderately steep, confined | Upper piedmont streams |
| III | <2% | Moderately confined, colluvial | Mid-slope streams |
| IV | <2% | Wide alluvial, open valley | Alluvial fans, piedmont |
| V | <2% | Wide valley, meandering floodplain | Piedmont / lowland |
| VI | <1% | Wide floodplain, low gradient | Lowland / coastal plain |
| VII | Variable | Braided, wide active channel | Disturbed or glacial |
| VIII | <0.1% | Tidal influenced | Coastal/estuarine |

**Piedmont SC focus:** Valley types II–V are most common in the Hunnicutt Creek drainage.

---

## Level II — Stream Channel Type Classification

### Key Discriminant Parameters

**Step 1: Is the channel entrenched?**
- Entrenchment Ratio (ER) = flood-prone width ÷ bankfull width
  - ER > 2.2 → **Slightly entrenched** (has floodplain access)
  - ER 1.4–2.2 → **Moderately entrenched**
  - ER < 1.4 → **Entrenched** (no floodplain access)

**Step 2: Width/Depth ratio**
- W/D = bankfull width ÷ mean bankfull depth
  - W/D < 12 → narrow/deep
  - W/D 12–40 → intermediate
  - W/D > 40 → wide/shallow

**Step 3: Sinuosity**
- K = channel length ÷ valley length
  - K < 1.2 → straight
  - K 1.2–1.5 → sinuous
  - K > 1.5 → meandering

**Step 4: Slope**
- Measured along thalweg (deepest point of channel)

---

### Stream Type Decision Key

| Type | ER | W/D | Sinuosity | Slope | Description |
|------|----|-----|-----------|-------|-------------|
| **Aa+** | <1.4 | <12 | <1.2 | >10% | Extremely steep cascade, torrent |
| **A** | <1.4 | <12 | <1.2 | 4–10% | Steep cascade, bedrock/boulder |
| **B** | <1.4 | >12 | 1.2–1.5 | 2–4% | Rapids, moderate slope, moderately entrenched |
| **C** | >2.2 | >12 | >1.5 | <2% | Meandering, well-developed floodplain |
| **D** | >2.2 | >40 | <1.5 | <2% | Braided, wide, unstable |
| **DA** | >2.2 | >40 | variable | <0.5% | Anabranching, anastomosing |
| **E** | >2.2 | <12 | >1.5 | <2% | Very low gradient, entrenched meander |
| **F** | <1.4 | >12 | >1.5 | <2% | Entrenched meanders, degraded |
| **G** | <1.4 | <12 | >1.5 | 2–4% | Incised step/pool, unstable |

**Most likely types in Piedmont SC piedmont/Hunnicutt Creek:**
- **C** — well-developed floodplain meanders in lowland reaches
- **B** — moderate gradient reaches in upper basin
- **E** — very low gradient meadow reaches (rare but high ecological value)
- **F or G** — degraded reaches (incised due to agriculture/development)

---

## Level III — Stream Condition (Qualitative)

After L-I and L-II classification, assess:
1. **Riparian condition** — canopy cover, bank vegetation
2. **Bank erosion** — lateral migration rate
3. **In-stream features** — pools, riffles, wood debris
4. **Connectivity** — floodplain inundation frequency

---

## Cross-Section Measurement Protocol

At each assessment reach (minimum 1 cross-section per 20× bankfull widths):

1. Establish a baseline perpendicular to flow
2. Record rod height at bankfull indicators (top of bank, vegetation line, or terrace)
3. Measure flood-prone width at 2× bankfull height above thalweg
4. Calculate mean bankfull depth = cross-sectional area ÷ bankfull width
5. Record pebble count for D50 (Wolman 1954 method — 100 particles)

### Bankfull Indicators (field identification)

In the Piedmont, bankfull stage is typically identified by:
- Top of point bar
- Change in vegetation community (grass → woody)
- Undercut bank top
- Soil horizon change (alluvial vs. upland soil)

---

## Rosgen × LEC Integration Notes

The Rosgen stream type directly predicts:
- **Floodplain width** → determines the bottomland LEC class polygon width
- **Incision depth** → affects soil drainage class and clay depth (LEC predictors)
- **Sinuosity** → predicts riparian vegetation diversity
- **Reach type stability** → indicates whether LEC classes are in equilibrium or transitional

For the Piedmont model:
- Map each stream reach → assign Rosgen type
- Buffer floodplain width around each C/E type reach
- Apply bottomland LEC to buffered area
- Flag F/G reaches as degraded — exclude from LEC training data or add as separate class
