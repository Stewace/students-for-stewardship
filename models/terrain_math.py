"""
Terrain Mathematics for Landscape Ecosystem Classification
Piedmont Ecoregion (EPA Level III, Region 45)

Implements all terrain indices used in the LEC discriminant analysis
with full mathematical documentation, citations, and NumPy/rasterio
implementations.

References:
  McNab, W.H. (1989). Terrain shape index. Forest Science 35(1):91-104.
  McNab, W.H. (1993). Topographic index for site productivity. CJFR 23:1100-1107.
  Beers, T.W. et al. (1966). Aspect transformation in site productivity research.
      J. Forestry 64:691-692.
  McCune, B. and Keon, D. (2002). Equations for potential annual direct incident
      radiation on a slope. J. Vegetation Science 13:603-606.
  Beven, K.J. and Kirkby, M.J. (1979). A physically based variable contributing
      area model. Hydrological Sciences Bulletin 24(1):43-69.
  Weiss, A. (2001). Topographic position and landforms analysis. ESRI User Conf.
  Hutto, C.J., Shelburne, V.B., and Jones, S.M. (1999). Preliminary ecological
      land classification of the Chauga Ridges. For. Ecol. Mgmt. 114:385-393.
  Jones, S.M. and Lloyd, F.T. (1993). Landscape ecosystem classification.
      In: Defining Sustainable Forestry. Island Press. pp. 181-201.
"""

import math
import warnings
import numpy as np
from typing import Union

Array = Union[np.ndarray, float]

# ---------------------------------------------------------------------------
# 1. Terrain Shape Index (TSI) — McNab 1989, 1993
# ---------------------------------------------------------------------------

def terrain_shape_index(dem_3x3: np.ndarray) -> float:
    """
    Compute Terrain Shape Index for a single 3×3 DEM window.

    TSI_i = (1/8) * Σ(z_j, j∈neighbors) − z_i

    where z_i is the center cell and z_j are the 8 cardinal and
    diagonal neighbors (equally weighted).

    Interpretation:
      TSI > 0 → concave position (hollow, valley — center lower than surrounds)
      TSI < 0 → convex position (ridge, knob — center higher than surrounds)
      TSI ≈ 0 → planar slope

    Parameters
    ----------
    dem_3x3 : np.ndarray, shape (3, 3)
        3×3 elevation array centered on the cell of interest.

    Returns
    -------
    float : TSI value in same units as elevation (meters)

    Reference
    ---------
    McNab (1989): TSI = mean(8 neighbors) - center
    """
    if dem_3x3.shape != (3, 3):
        raise ValueError("dem_3x3 must be shape (3,3)")

    z_center = dem_3x3[1, 1]
    neighbors = dem_3x3.flatten()
    # Exclude center (index 4 in flattened 3×3)
    neighbor_mask = np.ones(9, dtype=bool)
    neighbor_mask[4] = False
    z_neighbors = neighbors[neighbor_mask]

    valid = z_neighbors[~np.isnan(z_neighbors)]
    if len(valid) == 0:
        return np.nan

    return float(np.mean(valid) - z_center)


def terrain_shape_index_raster(dem: np.ndarray, nodata: float = -9999) -> np.ndarray:
    """
    Apply terrain_shape_index over an entire DEM raster using sliding window.

    Parameters
    ----------
    dem : np.ndarray, shape (rows, cols)
    nodata : value treated as no-data

    Returns
    -------
    np.ndarray of same shape as dem, with TSI values.
    """
    dem = dem.astype(float)
    dem[dem == nodata] = np.nan
    rows, cols = dem.shape
    tsi = np.full((rows, cols), np.nan)

    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            window = dem[r-1:r+2, c-1:c+2]
            if not np.isnan(dem[r, c]):
                tsi[r, c] = terrain_shape_index(window)

    return tsi


# ---------------------------------------------------------------------------
# 2. Landform Index (LI) — McNab 1993
# ---------------------------------------------------------------------------

def landform_index(tsi: Array, slope_deg: Array) -> Array:
    """
    Compute McNab's Landform Index.

    LI = TSI / (tan(β) + 1)

    where β is slope angle in degrees (converted to radians internally).

    The denominator dampens TSI on steep slopes — a hollow on a steep
    slope is less "effective" as a moisture accumulation site than the
    same hollow on a gentle slope.

    Higher LI → more sheltered/concave/productive
    Lower LI  → more exposed/convex/xeric

    Parameters
    ----------
    tsi : TSI value(s) in meters
    slope_deg : slope angle in degrees

    Reference
    ---------
    McNab (1993): "A topographic index to quantify the effect of mesoscale
    landform on site productivity." CJFR 23:1100-1107.
    """
    slope_rad = np.deg2rad(slope_deg)
    return tsi / (np.tan(slope_rad) + 1.0)


# ---------------------------------------------------------------------------
# 3. Topographic Wetness Index (TWI) — Beven & Kirkby 1979
# ---------------------------------------------------------------------------

def topographic_wetness_index(
    contributing_area_m2: Array,
    slope_deg: Array,
    min_slope_deg: float = 0.1,
) -> Array:
    """
    Compute Topographic Wetness Index.

    TWI = ln(A / tan(β))

    where A = specific upslope contributing area (m²/m of contour width)
              = total contributing area / cell width
    and   β = local slope angle in radians.

    TWI is a steady-state wetness proxy. Higher TWI → wetter site.
    Bottomlands typically TWI > 9; ridges TWI < 4.

    Parameters
    ----------
    contributing_area_m2 : upslope contributing area in m²
    slope_deg : local slope in degrees
    min_slope_deg : minimum slope to avoid division by zero (default 0.1°)

    Reference
    ---------
    Beven & Kirkby (1979). Hydrological Sciences Bulletin 24(1):43-69.
    """
    slope_deg = np.maximum(slope_deg, min_slope_deg)
    slope_rad = np.deg2rad(slope_deg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        twi = np.log(contributing_area_m2 / np.tan(slope_rad))
    return twi


# ---------------------------------------------------------------------------
# 4. Folded Aspect — Beers et al. 1966
# ---------------------------------------------------------------------------

def folded_aspect(aspect_deg: Array) -> Array:
    """
    Transform circular aspect to linear heat-load index.

    FA = |180 − |aspect − 225||

    Range: 0 to 180
      FA = 0   → SW-facing (225°) — hottest, most xeric
      FA = 180 → NE-facing (45°)  — coolest, most mesic

    This transformation is required before using aspect as a predictor
    in linear discriminant analysis (raw aspect is circular/periodic).

    Parameters
    ----------
    aspect_deg : aspect in degrees, 0 = north, clockwise

    Reference
    ---------
    Beers, T.W., Dress, P.E., and Wensel, L.C. (1966). Aspect transformation
    in site productivity research. J. Forestry 64:691-692.
    """
    return np.abs(180.0 - np.abs(np.asarray(aspect_deg, dtype=float) - 225.0))


# ---------------------------------------------------------------------------
# 5. Heat Load Index — McCune & Keon 2002
# ---------------------------------------------------------------------------

def heat_load_index(
    slope_deg: Array,
    aspect_deg: Array,
    latitude_deg: float = 34.85,
) -> Array:
    """
    Compute potential annual direct incident radiation (heat load index).

    HLI = exp(
        −1.467
        + 1.582 · cos(L) · cos(β)
        − 1.500 · cos(A) · sin(β) · sin(L)
        − 0.262 · sin(L) · sin(β)
        + 0.607 · sin(A) · sin(β)
    )

    where:
      L = latitude in radians
      β = slope in radians
      A = aspect in radians, folded to SW (= π - |aspect_rad - (5π/4)|)

    Higher HLI → more solar radiation → hotter, drier site.
    More physically rigorous than folded aspect alone.

    Parameters
    ----------
    slope_deg : slope angle in degrees
    aspect_deg : aspect in degrees (0 = north, clockwise)
    latitude_deg : site latitude (default 34.85° = Pickens Co., SC)

    Reference
    ---------
    McCune, B. and Keon, D. (2002). J. Vegetation Science 13:603-606.
    """
    L = math.radians(latitude_deg)
    beta = np.deg2rad(slope_deg)
    # Fold aspect to NE-SW axis: 0 = NE (cool), π = SW (hot)
    A_fold = np.pi - np.abs(np.deg2rad(aspect_deg) - (5 * np.pi / 4))
    hli = np.exp(
        -1.467
        + 1.582 * math.cos(L) * np.cos(beta)
        - 1.500 * np.cos(A_fold) * np.sin(beta) * math.sin(L)
        - 0.262 * math.sin(L) * np.sin(beta)
        + 0.607 * np.sin(A_fold) * np.sin(beta)
    )
    return hli


# ---------------------------------------------------------------------------
# 6. Slope Position Index (relative elevation)
# ---------------------------------------------------------------------------

def slope_position_index(
    elevation: Array,
    elev_min: float,
    elev_max: float,
) -> Array:
    """
    Normalize elevation within the local watershed (0–1).

    SPI = (z − z_min) / (z_max − z_min)

    SPI = 0 → valley bottom
    SPI = 1 → ridge top

    This captures the relative position within the landscape unit,
    which is more ecologically meaningful than absolute elevation
    in the gently rolling Piedmont.

    Parameters
    ----------
    elevation : array of cell elevations
    elev_min : minimum elevation in watershed
    elev_max : maximum elevation in watershed
    """
    elev_range = elev_max - elev_min
    if elev_range == 0:
        return np.zeros_like(elevation, dtype=float)
    return (np.asarray(elevation, dtype=float) - elev_min) / elev_range


# ---------------------------------------------------------------------------
# 7. Convergence Index
# ---------------------------------------------------------------------------

def convergence_index(aspect_raster_3x3: np.ndarray) -> float:
    """
    Compute Convergence Index for a 3×3 aspect window.

    CI = mean(Δaspect from radial directions) − 90

    Measures whether terrain converges (hollow) or diverges (ridge/spur).
      CI > 0 → diverging (ridge, convex)
      CI < 0 → converging (hollow, concave)
      CI ≈ 0 → planar slope

    Parameters
    ----------
    aspect_raster_3x3 : np.ndarray (3,3)
        Aspect values for the neighborhood in degrees.

    Reference
    ---------
    Adapted from Köthe & Lehmeier (1993) SARA system.
    """
    if aspect_raster_3x3.shape != (3, 3):
        raise ValueError("Must be 3×3")

    center_aspect = aspect_raster_3x3[1, 1]
    # Directions from center to each neighbor
    directions = np.array([
        315, 0, 45,
        270, np.nan, 90,
        225, 180, 135,
    ]).reshape(3, 3)

    diffs = []
    for r in range(3):
        for c in range(3):
            if r == 1 and c == 1:
                continue
            d = directions[r, c]
            a = aspect_raster_3x3[r, c]
            if np.isnan(a) or np.isnan(d):
                continue
            diff = abs(a - d)
            if diff > 180:
                diff = 360 - diff
            diffs.append(diff)

    if not diffs:
        return np.nan
    return float(np.mean(diffs) - 90.0)


# ---------------------------------------------------------------------------
# 8. Soil depth to clay horizon (normalize for use in LDA)
# ---------------------------------------------------------------------------

def normalize_clay_depth(clay_depth_cm: Array, max_cm: float = 200.0) -> Array:
    """
    Normalize clay horizon depth to 0–1 scale.

    Shallow (<40 cm) → xeric ridge classes
    Deep (>120 cm) → mesic cove and bottomland classes
    """
    return np.clip(np.asarray(clay_depth_cm, dtype=float) / max_cm, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 9. Full predictor vector assembly
# ---------------------------------------------------------------------------

# LEC predictor variable names (must match order used in LDA)
PREDICTOR_NAMES = [
    "slope_deg",          # Slope angle in degrees
    "folded_aspect",      # Beers 1966 heat-load direction (0=SW, 180=NE)
    "heat_load_index",    # McCune & Keon 2002 HLI
    "tsi",                # McNab 1989 Terrain Shape Index
    "landform_index",     # McNab 1993 LI = TSI / (tan(slope)+1)
    "twi",                # Topographic Wetness Index
    "slope_position",     # Normalized elevation within watershed (0=valley, 1=ridge)
    "clay_depth_norm",    # Normalized depth to clay horizon (0–1)
    "clay_pct_b",         # Clay % in B horizon (%)
    "drainage_class",     # Soil drainage class (1=very poor → 7=excessive)
]

N_PREDICTORS = len(PREDICTOR_NAMES)


def assemble_predictors(
    slope_deg: float,
    aspect_deg: float,
    tsi: float,
    twi: float,
    slope_position: float,
    clay_depth_cm: float,
    clay_pct_b: float,
    drainage_class: float,
    latitude_deg: float = 34.85,
    elev_min: float = 0.0,
    elev_max: float = 1.0,
    elevation: float = 0.5,
) -> np.ndarray:
    """
    Compute all predictor variables from raw inputs and return as a
    1D array in the order specified by PREDICTOR_NAMES.

    This is the single entry point for computing the predictor vector
    used in the LDA classification.
    """
    li = landform_index(tsi, slope_deg)
    fa = folded_aspect(aspect_deg)
    hli = float(heat_load_index(slope_deg, aspect_deg, latitude_deg))
    clay_d_norm = normalize_clay_depth(clay_depth_cm)

    return np.array([
        slope_deg,
        fa,
        hli,
        tsi,
        li,
        twi,
        slope_position,
        float(clay_d_norm),
        clay_pct_b,
        drainage_class,
    ], dtype=float)


def assemble_predictor_stack(
    slope: np.ndarray,
    aspect: np.ndarray,
    tsi: np.ndarray,
    twi: np.ndarray,
    elevation: np.ndarray,
    clay_depth: np.ndarray,
    clay_pct_b: np.ndarray,
    drainage_class: np.ndarray,
    latitude_deg: float = 34.85,
    nodata: float = -9999.0,
) -> np.ndarray:
    """
    Assemble full predictor stack from raster arrays.

    Parameters — all np.ndarray of same shape (rows, cols)
    Returns np.ndarray of shape (rows * cols, N_PREDICTORS)
    """
    shape = slope.shape
    n = shape[0] * shape[1]

    s = slope.reshape(-1).astype(float)
    a = aspect.reshape(-1).astype(float)
    t = tsi.reshape(-1).astype(float)
    w = twi.reshape(-1).astype(float)
    e = elevation.reshape(-1).astype(float)
    cd = clay_depth.reshape(-1).astype(float)
    cp = clay_pct_b.reshape(-1).astype(float)
    dr = drainage_class.reshape(-1).astype(float)

    # Derived
    li = landform_index(t, s)
    fa = folded_aspect(a)
    hli = heat_load_index(s, a, latitude_deg)

    e_min = np.nanmin(e[e != nodata]) if np.any(e != nodata) else 0.0
    e_max = np.nanmax(e[e != nodata]) if np.any(e != nodata) else 1.0
    sp = slope_position_index(e, e_min, e_max)
    cd_norm = normalize_clay_depth(cd)

    stack = np.column_stack([s, fa, hli, t, li, w, sp, cd_norm, cp, dr])

    # Mask nodata rows
    nodata_mask = (
        (s == nodata) | (a == nodata) | (t == nodata) |
        (w == nodata) | (e == nodata)
    )
    stack[nodata_mask] = np.nan

    return stack, shape, nodata_mask
