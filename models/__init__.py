"""
Piedmont LEC Classification Models
EPA Level III Ecoregion 45

Module structure:
  terrain_math.py        — All terrain index formulas with math documentation
  piedmont_classes.py    — Literature-based class parameters (means, covariances)
  synthetic_data.py      — Synthetic training data generator
  lda_model.py           — Linear Discriminant Analysis model
  ecoregion_classifier.py — Wall-to-wall raster classification pipeline
  model_evaluation.py    — Cross-validation, accuracy metrics, feature importance

Quick start:
    from models.lda_model import build_literature_model
    model = build_literature_model()

    from models.ecoregion_classifier import run_simulation
    run_simulation()

    from models.model_evaluation import full_report
    from models.synthetic_data import generate_training_dataset
    from models.terrain_math import PREDICTOR_NAMES
    df = generate_training_dataset(200)
    full_report(df[PREDICTOR_NAMES].values, df["lec_class"].values)
"""

from models.terrain_math import (
    terrain_shape_index,
    landform_index,
    topographic_wetness_index,
    folded_aspect,
    heat_load_index,
    slope_position_index,
    assemble_predictors,
    PREDICTOR_NAMES,
    N_PREDICTORS,
)

from models.piedmont_classes import (
    LEC_CLASSES,
    LEC_COLORS,
    LEC_INDICATOR_SPECIES,
    LEC_SOIL_SERIES,
    ALL_CLASSES,
    CLASS_CODES,
)

from models.lda_model import PiedmontLDA, build_literature_model, build_from_training

__all__ = [
    # terrain math
    "terrain_shape_index", "landform_index", "topographic_wetness_index",
    "folded_aspect", "heat_load_index", "slope_position_index",
    "assemble_predictors", "PREDICTOR_NAMES", "N_PREDICTORS",
    # class definitions
    "LEC_CLASSES", "LEC_COLORS", "LEC_INDICATOR_SPECIES", "LEC_SOIL_SERIES",
    "ALL_CLASSES", "CLASS_CODES",
    # model
    "PiedmontLDA", "build_literature_model", "build_from_training",
]
