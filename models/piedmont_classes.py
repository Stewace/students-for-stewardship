"""
Piedmont LEC Class Definitions and Literature-Based Parameters
EPA Level III Ecoregion 45 — Piedmont

Encodes the known ecological characteristics of each LEC class
as multivariate normal distributions fitted to published data from:

  Jones & Lloyd (1993) — original LEC framework, SE United States
  Hutto, Shelburne & Jones (1999) — Chauga Ridges discriminant functions
  McNab (1989, 1993) — TSI and LI field measurements
  Peet & Christensen (1988) — Piedmont vegetation gradients, NC
  Schafale & Weakley (1990) — Classification of natural communities of NC
  USDA NRCS SSURGO — Piedmont soil series characteristics

These parameters are used to:
  1. Generate synthetic training data (when field data is not yet collected)
  2. Seed the LDA prior means (informative priors)
  3. Validate field-collected training data against expected ranges

ALL PARAMETERS CAN AND SHOULD BE UPDATED when field data is collected.
Run models/lda_model.py --fit --training-data data/field/training/ to
refit the model from field observations.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict

# ---------------------------------------------------------------------------
# LEC class codes and names
# ---------------------------------------------------------------------------

LEC_CLASSES = {
    1: "Xeric Ridge / Upper Slope",
    2: "Dry-Mesic Slope",
    3: "Mesic Slope",
    4: "Cove / Hollow",
    5: "Bottomland / Riparian",
    6: "Upland Flat",
}

LEC_COLORS = {
    1: "#c62828",  # red
    2: "#f57f17",  # orange
    3: "#558b2f",  # green
    4: "#1565c0",  # blue
    5: "#00695c",  # teal
    6: "#9e9e9e",  # gray
}

# Indicator species assemblages for field validation (Piedmont SC)
LEC_INDICATOR_SPECIES = {
    1: [
        "Quercus stellata (post oak)",
        "Quercus marilandica (blackjack oak)",
        "Pinus echinata (shortleaf pine)",
        "Vaccinium arboreum (sparkleberry)",
        "Smilax glauca (sawbrier)",
    ],
    2: [
        "Quercus alba (white oak)",
        "Quercus velutina (black oak)",
        "Carya tomentosa (mockernut hickory)",
        "Oxydendrum arboreum (sourwood)",
        "Kalmia latifolia (mountain laurel)",
    ],
    3: [
        "Quercus rubra (northern red oak)",
        "Acer rubrum (red maple)",
        "Liriodendron tulipifera (tulip poplar)",
        "Cornus florida (flowering dogwood)",
        "Trillium spp.",
    ],
    4: [
        "Liriodendron tulipifera (tulip poplar)",
        "Aesculus sylvatica (painted buckeye)",
        "Fagus grandifolia (American beech)",
        "Trillium erectum",
        "Sanguinaria canadensis (bloodroot)",
    ],
    5: [
        "Platanus occidentalis (sycamore)",
        "Betula nigra (river birch)",
        "Acer rubrum (red maple)",
        "Liquidambar styraciflua (sweetgum)",
        "Carpinus caroliniana (ironwood)",
    ],
    6: [
        "Pinus taeda (loblolly pine)",
        "Liquidambar styraciflua (sweetgum)",
        "Quercus falcata (southern red oak)",
        "Smilax rotundifolia (greenbrier)",
        "Vitis rotundifolia (muscadine)",
    ],
}

# Soil series commonly associated with each LEC class in SC Piedmont
LEC_SOIL_SERIES = {
    1: ["Cecil-shallow phase", "Pacolet", "Wedowee-rocky", "Hard labor"],
    2: ["Cecil", "Pacolet", "Madison", "Musella"],
    3: ["Appling", "Madison", "Hiwassee", "Louisa"],
    4: ["Hayesville", "Fannin", "Greenlee", "Tate"],
    5: ["Chewacla", "Wehadkee", "Congaree", "Cartecay"],
    6: ["Cecil-smooth", "Helena", "Vance", "White Store"],
}


# ---------------------------------------------------------------------------
# Literature-based class parameter distributions
# ---------------------------------------------------------------------------
# Predictor order matches terrain_math.PREDICTOR_NAMES:
#   [slope_deg, folded_aspect, hli, tsi, landform_index, twi,
#    slope_position, clay_depth_norm, clay_pct_b, drainage_class]
#
# Sources for each class:
#   Slope: McNab (1993) field measurements; Hutto et al. (1999)
#   Aspect/FA: Peet & Christensen (1988) Piedmont gradient analysis
#   TSI: McNab (1989, 1993) field data; Hutto et al. (1999)
#   TWI: estimated from SSURGO drainage class and Piedmont topography
#   Slope position: derived from relative elevation analysis
#   Clay depth/pct: SSURGO Piedmont series averages
#   Drainage: SSURGO drainage class codes

@dataclass
class LECClassParams:
    name: str
    code: int
    # Mean vector for each predictor (10 values)
    mu: np.ndarray
    # Standard deviation for each predictor
    sigma: np.ndarray
    # Prior probability (proportion of Piedmont landscape)
    prior: float
    # Pairwise correlation matrix for predictors (10×10)
    # Key ecological correlations encoded here
    corr_matrix: np.ndarray = field(default=None)

    def __post_init__(self):
        if self.corr_matrix is None:
            self.corr_matrix = np.eye(len(self.mu))

    @property
    def cov_matrix(self) -> np.ndarray:
        """Convert correlation matrix to covariance matrix."""
        D = np.diag(self.sigma)
        return D @ self.corr_matrix @ D


def _make_corr(n: int, pairs: dict) -> np.ndarray:
    """
    Build a correlation matrix from a dict of {(i,j): r} pairs.
    Enforces symmetry and diagonal = 1.
    """
    C = np.eye(n)
    for (i, j), r in pairs.items():
        C[i, j] = r
        C[j, i] = r
    # Ensure positive semi-definite via nearest PD approximation
    eigvals = np.linalg.eigvalsh(C)
    if np.any(eigvals < 0):
        C += np.eye(n) * (-eigvals.min() + 1e-6)
        d = np.sqrt(np.diag(C))
        C = C / np.outer(d, d)
    return C


# Predictor index map for readable correlation specification
P = {name: i for i, name in enumerate([
    "slope", "fa", "hli", "tsi", "li", "twi", "sp", "clay_d", "clay_pct", "drain"
])}


# ---------------------------------------------------------------------------
# Class 1: Xeric Ridge / Upper Slope
# ---------------------------------------------------------------------------
# Steep, convex, south-facing, shallow soils, excessively drained
# Indicator: post oak, blackjack oak, shortleaf pine
# Soil: Cecil-shallow, Pacolet (Ultisols, shallow phase)
# Source: Hutto et al. 1999 Table 1; McNab 1993 field sites

CLASS_1 = LECClassParams(
    name="Xeric Ridge / Upper Slope",
    code=1,
    mu=np.array([
        24.0,   # slope_deg: steep — Hutto et al. Table 2
        55.0,   # folded_aspect: mixed, slightly SW-biased (0=SW, 180=NE)
        1.18,   # heat_load_index: high solar load
        -2.8,   # tsi: strongly convex — McNab 1989 ridge sites
        -1.9,   # landform_index: negative (exposed)
        3.8,    # twi: dry — low wetness
        0.78,   # slope_position: high in watershed
        0.20,   # clay_depth_norm: shallow (<40 cm)
        17.0,   # clay_pct_b: low clay %
        6.5,    # drainage_class: well to excessively drained
    ]),
    sigma=np.array([7.0, 42.0, 0.08, 1.5, 1.2, 0.9, 0.12, 0.09, 6.0, 0.6]),
    prior=0.12,
    corr_matrix=_make_corr(10, {
        (P["slope"], P["hli"]): 0.35,     # steeper → more radiation
        (P["slope"], P["sp"]): 0.45,      # steeper → higher in watershed
        (P["tsi"], P["li"]): 0.88,        # TSI and LI highly correlated
        (P["tsi"], P["twi"]): 0.40,       # convex → drier
        (P["slope"], P["twi"]): -0.35,    # steeper → drier
        (P["sp"], P["twi"]): -0.55,       # higher → drier
        (P["clay_d"], P["drain"]): -0.60, # shallower clay → better drainage
        (P["fa"], P["hli"]): -0.70,       # SW-facing (low FA) → high HLI
    }),
)

# ---------------------------------------------------------------------------
# Class 2: Dry-Mesic Slope
# ---------------------------------------------------------------------------
# Moderate-steep slope, variable aspect, moderate soils
# Indicator: white oak, black oak, hickory, sourwood
# Soil: Cecil, Pacolet, Madison (typical Piedmont Ultisols)

CLASS_2 = LECClassParams(
    name="Dry-Mesic Slope",
    code=2,
    mu=np.array([
        17.0,   # slope_deg
        90.0,   # folded_aspect: mixed aspects (middle of range)
        1.05,   # hli
        -0.9,   # tsi: slightly convex
        -0.7,   # li
        4.6,    # twi
        0.56,   # slope_position: middle-upper
        0.30,   # clay_depth_norm: ~60 cm
        22.0,   # clay_pct_b
        5.5,    # drainage_class: well drained
    ]),
    sigma=np.array([5.5, 48.0, 0.10, 1.2, 0.9, 1.0, 0.12, 0.10, 7.0, 0.8]),
    prior=0.22,
    corr_matrix=_make_corr(10, {
        (P["tsi"], P["li"]): 0.87,
        (P["slope"], P["sp"]): 0.40,
        (P["tsi"], P["twi"]): 0.35,
        (P["clay_d"], P["drain"]): -0.55,
        (P["fa"], P["hli"]): -0.68,
    }),
)

# ---------------------------------------------------------------------------
# Class 3: Mesic Slope
# ---------------------------------------------------------------------------
# Moderate slope, north/northeast facing, moderate-deep soils
# Indicator: red oak, tulip poplar, red maple, dogwood
# Soil: Appling, Madison, Hiwassee (Piedmont Ultisols, deeper)
# Source: Peet & Christensen 1988 gradient position; Hutto 1999

CLASS_3 = LECClassParams(
    name="Mesic Slope",
    code=3,
    mu=np.array([
        13.0,   # slope_deg: moderate
        138.0,  # folded_aspect: N/NE facing (closer to 180 = NE)
        0.88,   # hli: lower solar load due to N-facing
        0.4,    # tsi: near-zero to slightly concave
        0.3,    # li
        5.6,    # twi: moderately wet
        0.46,   # slope_position: middle
        0.38,   # clay_depth_norm: ~75 cm
        26.0,   # clay_pct_b
        5.0,    # drainage_class: moderately well drained
    ]),
    sigma=np.array([5.0, 38.0, 0.12, 1.0, 0.8, 1.1, 0.12, 0.10, 7.0, 0.7]),
    prior=0.28,
    corr_matrix=_make_corr(10, {
        (P["tsi"], P["li"]): 0.86,
        (P["fa"], P["hli"]): -0.72,       # N-facing (high FA) → low HLI
        (P["slope"], P["sp"]): 0.35,
        (P["tsi"], P["twi"]): 0.45,
        (P["clay_d"], P["drain"]): -0.50,
        (P["sp"], P["twi"]): -0.40,
    }),
)

# ---------------------------------------------------------------------------
# Class 4: Cove / Hollow
# ---------------------------------------------------------------------------
# Lower slope, concave, north-facing, deep soils, high moisture
# Indicator: tulip poplar, beech, buckeye, hepatica, trillium
# Soil: Hayesville, Fannin, Tate (deep colluvial Ultisols)
# Source: Hutto et al. 1999 discriminant function for Blue Ridge coves

CLASS_4 = LECClassParams(
    name="Cove / Hollow",
    code=4,
    mu=np.array([
        9.5,    # slope_deg: low-moderate
        152.0,  # folded_aspect: strongly NE-facing (near 180 = NE)
        0.75,   # hli: low solar load
        3.8,    # tsi: clearly concave — McNab 1993 cove sites
        3.0,    # li: high landform index
        7.2,    # twi: wet
        0.33,   # slope_position: lower-middle
        0.50,   # clay_depth_norm: ~100 cm
        30.0,   # clay_pct_b: higher clay
        4.0,    # drainage_class: moderately well drained
    ]),
    sigma=np.array([4.0, 28.0, 0.12, 1.5, 1.2, 1.3, 0.10, 0.12, 7.0, 0.8]),
    prior=0.15,
    corr_matrix=_make_corr(10, {
        (P["tsi"], P["li"]): 0.87,
        (P["tsi"], P["twi"]): 0.60,       # concave → wetter
        (P["fa"], P["hli"]): -0.70,
        (P["sp"], P["twi"]): -0.50,
        (P["clay_d"], P["clay_pct"]): 0.45,
        (P["clay_d"], P["drain"]): -0.55,
    }),
)

# ---------------------------------------------------------------------------
# Class 5: Bottomland / Riparian
# ---------------------------------------------------------------------------
# Nearly flat, valley bottom, deep alluvial soils, flooded periodically
# Indicator: sycamore, river birch, sweetgum, ironwood
# Soil: Chewacla, Wehadkee, Congaree (Fluvents, Aquults)
# Source: Cole 1995 (forested wetlands); SSURGO floodplain series

CLASS_5 = LECClassParams(
    name="Bottomland / Riparian",
    code=5,
    mu=np.array([
        2.5,    # slope_deg: nearly flat
        90.0,   # folded_aspect: variable / irrelevant on flat ground
        0.95,   # hli: moderate (flat, no shading)
        9.5,    # tsi: highly concave/flat valley — very high
        5.0,    # li
        11.0,   # twi: very high wetness
        0.09,   # slope_position: valley bottom
        0.72,   # clay_depth_norm: ~140 cm — deep alluvial
        36.0,   # clay_pct_b: high clay
        2.0,    # drainage_class: poorly to somewhat poorly drained
    ]),
    sigma=np.array([1.5, 60.0, 0.10, 2.5, 2.0, 2.0, 0.07, 0.14, 9.0, 0.8]),
    prior=0.10,
    corr_matrix=_make_corr(10, {
        (P["tsi"], P["twi"]): 0.72,       # very concave → very wet
        (P["tsi"], P["li"]): 0.80,
        (P["sp"], P["twi"]): -0.75,       # lowest position → wettest
        (P["clay_d"], P["clay_pct"]): 0.55,
        (P["clay_d"], P["drain"]): -0.65,
        (P["slope"], P["sp"]): 0.50,      # flat → low in watershed
    }),
)

# ---------------------------------------------------------------------------
# Class 6: Upland Flat
# ---------------------------------------------------------------------------
# Gently rolling upland interfluves, moderate soils, mixed composition
# Indicator: loblolly pine, sweetgum, southern red oak, blackgum
# Soil: Cecil-smooth, Helena, Vance (typical Piedmont interfluves)

CLASS_6 = LECClassParams(
    name="Upland Flat",
    code=6,
    mu=np.array([
        5.0,    # slope_deg: gentle
        90.0,   # folded_aspect: mixed (irrelevant on gentle slopes)
        1.00,   # hli: moderate (low slope angle reduces effect)
        0.1,    # tsi: near-planar
        0.09,   # li: near-zero
        5.2,    # twi: moderate
        0.62,   # slope_position: upper-middle interfluve
        0.38,   # clay_depth_norm: ~75 cm
        23.0,   # clay_pct_b
        5.0,    # drainage_class: moderately well to well drained
    ]),
    sigma=np.array([2.5, 55.0, 0.06, 0.8, 0.6, 1.2, 0.14, 0.10, 7.0, 0.8]),
    prior=0.13,
    corr_matrix=_make_corr(10, {
        (P["tsi"], P["li"]): 0.88,
        (P["tsi"], P["twi"]): 0.30,
        (P["clay_d"], P["drain"]): -0.45,
    }),
)

# ---------------------------------------------------------------------------
# All classes together
# ---------------------------------------------------------------------------

ALL_CLASSES: Dict[int, LECClassParams] = {
    1: CLASS_1,
    2: CLASS_2,
    3: CLASS_3,
    4: CLASS_4,
    5: CLASS_5,
    6: CLASS_6,
}

# Prior probabilities (must sum to 1.0)
PRIORS = np.array([c.prior for c in ALL_CLASSES.values()])
assert abs(PRIORS.sum() - 1.0) < 0.01, f"Priors sum to {PRIORS.sum():.3f}, must be 1.0"

CLASS_CODES = np.array(list(ALL_CLASSES.keys()))   # [1,2,3,4,5,6]
CLASS_NAMES = [c.name for c in ALL_CLASSES.values()]

# Mean matrix (6 × 10): one row per class
MU = np.vstack([c.mu for c in ALL_CLASSES.values()])

# Per-class covariance matrices (6 × 10 × 10)
COV = np.stack([c.cov_matrix for c in ALL_CLASSES.values()])
