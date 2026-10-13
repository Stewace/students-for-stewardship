"""
Synthetic Training Data Generator — Piedmont LEC Classes
EPA Level III Ecoregion 45

Generates statistically representative training samples for each LEC class
using the literature-based multivariate normal parameters in piedmont_classes.py.

Purpose:
  - Bootstraps the LDA model before field data is collected
  - Demonstrates expected data distributions
  - Validates that class parameters are ecologically coherent

These synthetic samples SHOULD be replaced with real field data as
surveys are completed. Run with --augment to blend synthetic + field data.

Usage:
    # Generate synthetic training dataset
    python models/synthetic_data.py --n-per-class 200 --output data/field/training/

    # Plot class distributions
    python models/synthetic_data.py --plot

    # Check separability between classes
    python models/synthetic_data.py --check-separation
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from models.terrain_math import PREDICTOR_NAMES
from models.piedmont_classes import (
    ALL_CLASSES, LEC_CLASSES,
    CLASS_CODES, MU, COV, PRIORS
)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def generate_class_samples(
    class_code: int,
    n: int,
    rng: np.random.Generator,
    enforce_bounds: bool = True,
) -> np.ndarray:
    """
    Draw n samples from the multivariate normal distribution for a class.

    Parameters
    ----------
    class_code : LEC class code (1–6)
    n : number of samples
    rng : numpy random generator
    enforce_bounds : clip generated values to physically reasonable ranges

    Returns
    -------
    np.ndarray, shape (n, n_predictors)
    """
    cls = ALL_CLASSES[class_code]
    samples = rng.multivariate_normal(cls.mu, cls.cov_matrix, size=n)

    if enforce_bounds:
        samples = _apply_bounds(samples)

    return samples


def _apply_bounds(X: np.ndarray) -> np.ndarray:
    """
    Clip predictor values to physically realizable ranges.
    Indices match PREDICTOR_NAMES order.
    """
    X = X.copy()
    # slope_deg: 0–60°
    X[:, 0] = np.clip(X[:, 0], 0.0, 60.0)
    # folded_aspect: 0–180
    X[:, 1] = np.clip(X[:, 1], 0.0, 180.0)
    # heat_load_index: 0.5–1.5 (dimensionless)
    X[:, 2] = np.clip(X[:, 2], 0.5, 1.5)
    # tsi: -10 to +20 (meters)
    X[:, 3] = np.clip(X[:, 3], -10.0, 20.0)
    # landform_index: no hard bounds but clip extremes
    X[:, 4] = np.clip(X[:, 4], -15.0, 25.0)
    # twi: 2–18
    X[:, 5] = np.clip(X[:, 5], 2.0, 18.0)
    # slope_position: 0–1
    X[:, 6] = np.clip(X[:, 6], 0.0, 1.0)
    # clay_depth_norm: 0–1
    X[:, 7] = np.clip(X[:, 7], 0.0, 1.0)
    # clay_pct_b: 5–65%
    X[:, 8] = np.clip(X[:, 8], 5.0, 65.0)
    # drainage_class: 1–7
    X[:, 9] = np.clip(X[:, 9], 1.0, 7.0)
    return X


def generate_training_dataset(
    n_per_class: int = 150,
    seed: int = 42,
    class_proportional: bool = False,
) -> pd.DataFrame:
    """
    Generate a full synthetic training dataset with all LEC classes.

    Parameters
    ----------
    n_per_class : samples per class (equal) OR minimum if proportional
    seed : random seed for reproducibility
    class_proportional : if True, scale sample count by class prior probability

    Returns
    -------
    DataFrame with columns = PREDICTOR_NAMES + ['lec_class', 'lec_name', 'source']
    """
    rng = np.random.default_rng(seed)
    frames = []

    for code in CLASS_CODES:
        if class_proportional:
            n = max(30, int(n_per_class * ALL_CLASSES[code].prior / PRIORS.max()))
        else:
            n = n_per_class

        samples = generate_class_samples(code, n, rng)
        df = pd.DataFrame(samples, columns=PREDICTOR_NAMES)
        df["lec_class"] = code
        df["lec_name"] = LEC_CLASSES[code]
        df["source"] = "synthetic"
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Class separability analysis
# ---------------------------------------------------------------------------

def mahalanobis_between_classes() -> pd.DataFrame:
    """
    Compute pairwise Mahalanobis distance between all class mean vectors
    using the pooled within-class covariance matrix.

    D²(i,j) = (μ_i - μ_j)^T * Σ_pooled^{-1} * (μ_i - μ_j)

    Higher D² → better separation between classes.
    D² < 1 → poor separation (classes may be confused).
    """
    # Pooled covariance: equal-weighted average of class covariances
    Sigma_pooled = np.mean(COV, axis=0)
    Sigma_inv = np.linalg.pinv(Sigma_pooled)

    n_classes = len(CLASS_CODES)
    D2 = np.zeros((n_classes, n_classes))

    for i in range(n_classes):
        for j in range(n_classes):
            diff = MU[i] - MU[j]
            D2[i, j] = float(diff @ Sigma_inv @ diff)

    class_names = [ALL_CLASSES[c].name for c in CLASS_CODES]
    return pd.DataFrame(D2, index=class_names, columns=class_names)


def check_class_separation():
    """Print separability analysis and flag poorly separated class pairs."""
    D2 = mahalanobis_between_classes()
    print("\n=== Pairwise Mahalanobis D² (higher = better separation) ===\n")
    print(D2.round(2).to_string())

    print("\n=== Potentially Confused Pairs (D² < 4.0) ===")
    found = False
    names = D2.columns.tolist()
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            d = D2.iloc[i, j]
            if d < 4.0:
                print(f"  {names[i]:30s} ↔ {names[j]:30s}  D²={d:.2f}")
                found = True
    if not found:
        print("  None — all class pairs are well separated.")

    print("\n=== Most Similar Class Pairs (smallest D²) ===")
    pairs = []
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            pairs.append((D2.iloc[i, j], names[i], names[j]))
    pairs.sort()
    for d, a, b in pairs[:4]:
        print(f"  D²={d:6.2f}  {a}  ↔  {b}")


# ---------------------------------------------------------------------------
# Predictor statistics per class
# ---------------------------------------------------------------------------

def class_summary_table(df: pd.DataFrame = None) -> pd.DataFrame:
    """
    Show mean and SD of each predictor per LEC class.
    If df is None, uses the literature-based means directly.
    """
    if df is not None:
        rows = []
        for code in CLASS_CODES:
            subset = df[df["lec_class"] == code]
            row = {"class": LEC_CLASSES[code]}
            for pred in PREDICTOR_NAMES:
                row[f"{pred}_mean"] = subset[pred].mean()
                row[f"{pred}_sd"] = subset[pred].std()
            rows.append(row)
        return pd.DataFrame(rows)
    else:
        # Use literature parameters directly
        rows = []
        for code, cls in ALL_CLASSES.items():
            row = {"class": cls.name}
            for i, pred in enumerate(PREDICTOR_NAMES):
                row[f"{pred}_mean"] = cls.mu[i]
                row[f"{pred}_sd"] = cls.sigma[i]
            rows.append(row)
        return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Augment field data with synthetic samples
# ---------------------------------------------------------------------------

def augment_with_synthetic(
    field_df: pd.DataFrame,
    min_per_class: int = 50,
    seed: int = 0,
) -> pd.DataFrame:
    """
    Add synthetic samples to any class that has fewer than min_per_class
    field observations. Helps stabilize LDA estimation with small samples.

    Parameters
    ----------
    field_df : DataFrame with columns matching PREDICTOR_NAMES + 'lec_class'
    min_per_class : minimum training samples per class
    seed : random seed

    Returns
    -------
    Augmented DataFrame with 'source' column marking synthetic rows
    """
    rng = np.random.default_rng(seed)
    frames = [field_df.copy()]

    if "source" not in frames[0].columns:
        frames[0]["source"] = "field"

    for code in CLASS_CODES:
        n_field = len(field_df[field_df["lec_class"] == code])
        n_needed = max(0, min_per_class - n_field)
        if n_needed == 0:
            continue

        print(f"  Class {code} ({LEC_CLASSES[code]}): {n_field} field → "
              f"adding {n_needed} synthetic")
        samples = generate_class_samples(code, n_needed, rng)
        df = pd.DataFrame(samples, columns=PREDICTOR_NAMES)
        df["lec_class"] = code
        df["lec_name"] = LEC_CLASSES[code]
        df["source"] = "synthetic"
        frames.append(df)

    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate synthetic Piedmont LEC training data"
    )
    parser.add_argument("--n-per-class", type=int, default=200)
    parser.add_argument("--output", type=str, default="data/field/training/")
    parser.add_argument("--plot", action="store_true",
                        help="Plot predictor distributions per class")
    parser.add_argument("--check-separation", action="store_true",
                        help="Print class separability analysis")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.check_separation:
        check_class_separation()
        summary = class_summary_table()
        print("\n=== Literature-Based Class Means ===")
        key_preds = ["slope_deg", "tsi", "twi", "slope_position",
                     "clay_depth_norm", "drainage_class"]
        cols = ["class"] + [f"{p}_mean" for p in key_preds]
        print(summary[cols].to_string(index=False))
        return

    print(f"Generating {args.n_per_class} samples per class...")
    df = generate_training_dataset(args.n_per_class, seed=args.seed)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "synthetic_training_data.csv"
    df.to_csv(path, index=False)
    print(f"Saved {len(df)} samples → {path}")
    print(f"\nClass distribution:")
    print(df.groupby("lec_name").size().to_string())

    if args.plot:
        try:
            import matplotlib.pyplot as plt
            from models.piedmont_classes import LEC_COLORS

            key_preds = ["slope_deg", "tsi", "twi", "folded_aspect",
                         "slope_position", "clay_depth_norm"]
            fig, axes = plt.subplots(2, 3, figsize=(14, 8))
            axes = axes.flatten()

            for ax, pred in zip(axes, key_preds):
                for code in CLASS_CODES:
                    subset = df[df["lec_class"] == code][pred]
                    ax.hist(subset, bins=30, alpha=0.5,
                            color=LEC_COLORS[code],
                            label=LEC_CLASSES[code] if pred == key_preds[0] else "")
                ax.set_title(pred)
                ax.set_xlabel(pred)

            axes[0].legend(fontsize=7, loc="upper right")
            plt.suptitle("Piedmont LEC Class Predictor Distributions (Synthetic)",
                         fontsize=12)
            plt.tight_layout()
            plot_path = str(out / "class_distributions.png")
            plt.savefig(plot_path, dpi=150)
            print(f"\nDistribution plot saved → {plot_path}")
        except ImportError:
            print("matplotlib not installed — skipping plot")


if __name__ == "__main__":
    main()
