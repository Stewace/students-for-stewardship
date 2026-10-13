"""
Linear Discriminant Analysis Model for Piedmont LEC Classification
EPA Level III Ecoregion 45

Implements the full LDA pipeline:
  1. Fit from training data (field or synthetic)
  2. Predict class membership
  3. Compute posterior probabilities and Mahalanobis distances
  4. Serialize / deserialize model parameters

Mathematical Foundation
-----------------------
For K classes and p predictors, LDA assigns observation x to the class
k* that maximizes the linear discriminant function:

    δ_k(x) = x^T Σ⁻¹ μ_k  −  ½ μ_k^T Σ⁻¹ μ_k  +  log(π_k)

where:
  μ_k     = class k mean vector (p × 1)
  Σ       = pooled within-class covariance matrix (p × p)
  π_k     = prior probability of class k
  x       = predictor vector (p × 1)

The pooled covariance is:
    Σ = (1 / (N − K)) * Σ_k (n_k − 1) * S_k

Posterior probability via softmax:
    P(G=k | X=x) = exp(δ_k(x)) / Σ_l exp(δ_l(x))

Mahalanobis distance to class k:
    D²_k(x) = (x − μ_k)^T Σ⁻¹ (x − μ_k)

The predicted class is the one with minimum D² (equivalent to
maximum δ when priors are equal).

References
----------
Fisher, R.A. (1936). The use of multiple measurements in taxonomic problems.
    Annals of Eugenics 7(2):179-188.
McLachlan, G.J. (2004). Discriminant Analysis and Statistical Pattern
    Recognition. Wiley.
Hutto, C.J., Shelburne, V.B., Jones, S.M. (1999). Preliminary ecological
    land classification of the Chauga Ridges. For. Ecol. Mgmt. 114:385-393.
"""

import json
import warnings
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from models.terrain_math import PREDICTOR_NAMES, N_PREDICTORS
from models.piedmont_classes import (
    ALL_CLASSES, CLASS_CODES, LEC_CLASSES, MU as LIT_MU, COV as LIT_COV, PRIORS
)


# ---------------------------------------------------------------------------
# LDA Model
# ---------------------------------------------------------------------------

class PiedmontLDA:
    """
    Linear Discriminant Analysis classifier for Piedmont LEC classes.

    Attributes
    ----------
    mu_ : np.ndarray (K, p) — fitted class means
    Sigma_ : np.ndarray (p, p) — pooled within-class covariance
    Sigma_inv_ : np.ndarray (p, p) — inverse of pooled covariance
    priors_ : np.ndarray (K,) — class prior probabilities
    class_codes_ : np.ndarray (K,) — LEC class codes [1..6]
    is_fitted_ : bool
    """

    def __init__(
        self,
        class_codes: np.ndarray = CLASS_CODES,
        priors: Optional[np.ndarray] = None,
        regularization: float = 1e-4,
    ):
        """
        Parameters
        ----------
        class_codes : array of LEC class codes (default [1,2,3,4,5,6])
        priors : prior probabilities; if None, estimated from training data
        regularization : ridge term added to diagonal of Sigma to ensure
                         invertibility (λI). Larger → more regularization.
                         Default 1e-4 is appropriate for standardized data.
        """
        self.class_codes_ = np.array(class_codes)
        self._priors_user = priors
        self.regularization = regularization
        self.is_fitted_ = False

        # Parameters set by fit()
        self.mu_: Optional[np.ndarray] = None
        self.Sigma_: Optional[np.ndarray] = None
        self.Sigma_inv_: Optional[np.ndarray] = None
        self.priors_: Optional[np.ndarray] = None
        self.n_samples_: Optional[int] = None
        self.n_per_class_: Optional[dict] = None

        # Standardization parameters (fit on training X)
        self.x_mean_: Optional[np.ndarray] = None
        self.x_std_: Optional[np.ndarray] = None

    # ------------------------------------------------------------------
    # Fit
    # ------------------------------------------------------------------

    def fit(
        self,
        X: np.ndarray,
        y: np.ndarray,
        standardize: bool = True,
    ) -> "PiedmontLDA":
        """
        Fit LDA from training data.

        Parameters
        ----------
        X : np.ndarray (N, p) — predictor matrix
        y : np.ndarray (N,)   — class labels (LEC codes 1–6)
        standardize : center and scale X before fitting

        Returns self (for chaining).
        """
        X, y = np.asarray(X, dtype=float), np.asarray(y)
        assert X.ndim == 2, "X must be 2-D (N, p)"
        assert X.shape[1] == N_PREDICTORS, \
            f"Expected {N_PREDICTORS} predictors, got {X.shape[1]}"

        N, p = X.shape
        K = len(self.class_codes_)

        # --- Remove rows with NaN ---
        valid = ~np.any(np.isnan(X), axis=1)
        X, y = X[valid], y[valid]
        N = len(X)

        # --- Standardize ---
        if standardize:
            self.x_mean_ = X.mean(axis=0)
            self.x_std_ = X.std(axis=0, ddof=1)
            self.x_std_[self.x_std_ == 0] = 1.0
            X = (X - self.x_mean_) / self.x_std_

        # --- Class means and pooled covariance ---
        mu = np.zeros((K, p))
        n_per_class = {}
        S_pooled = np.zeros((p, p))

        for k, code in enumerate(self.class_codes_):
            mask = y == code
            n_k = mask.sum()
            n_per_class[int(code)] = int(n_k)
            if n_k < 2:
                raise ValueError(
                    f"Class {code} ({LEC_CLASSES[code]}) has only {n_k} samples. "
                    f"Need ≥ 2. Run synthetic_data.py to augment."
                )
            X_k = X[mask]
            mu[k] = X_k.mean(axis=0)
            S_k = np.cov(X_k.T, ddof=1) * (n_k - 1)
            S_pooled += S_k

        # Pooled covariance matrix
        Sigma = S_pooled / (N - K)

        # --- Regularization (ridge) ---
        Sigma += np.eye(p) * self.regularization

        # --- Invert pooled covariance ---
        try:
            Sigma_inv = np.linalg.inv(Sigma)
        except np.linalg.LinAlgError:
            warnings.warn("Sigma singular — using pseudo-inverse.")
            Sigma_inv = np.linalg.pinv(Sigma)

        # --- Priors ---
        if self._priors_user is not None:
            priors = np.array(self._priors_user)
        else:
            priors = np.array([n_per_class[int(c)] for c in self.class_codes_],
                               dtype=float)
            priors /= priors.sum()

        self.mu_ = mu
        self.Sigma_ = Sigma
        self.Sigma_inv_ = Sigma_inv
        self.priors_ = priors
        self.n_samples_ = N
        self.n_per_class_ = n_per_class
        self.is_fitted_ = True

        return self

    # ------------------------------------------------------------------
    # Fit from literature parameters (no field data required)
    # ------------------------------------------------------------------

    def fit_from_literature(self) -> "PiedmontLDA":
        """
        Initialize LDA directly from the literature-based parameters
        in piedmont_classes.py, bypassing the need for training data.

        The class means (μ_k) and within-class covariances are taken
        directly from the literature values. The pooled covariance is
        computed as the prior-weighted average of class covariances.

        This produces a usable model immediately. Refit with field data
        to improve accuracy.
        """
        K, p = len(self.class_codes_), N_PREDICTORS

        # Standardize literature means using their own scale
        # (we don't standardize when using literature params directly —
        #  the raw predictor scale is meaningful)
        self.x_mean_ = np.zeros(p)
        self.x_std_ = np.ones(p)

        self.mu_ = LIT_MU.copy()  # (K, p)
        self.priors_ = PRIORS.copy()

        # Pooled covariance: prior-weighted average of class covariances
        Sigma = np.zeros((p, p))
        for k in range(K):
            Sigma += self.priors_[k] * LIT_COV[k]

        Sigma += np.eye(p) * self.regularization
        try:
            Sigma_inv = np.linalg.inv(Sigma)
        except np.linalg.LinAlgError:
            Sigma_inv = np.linalg.pinv(Sigma)

        self.Sigma_ = Sigma
        self.Sigma_inv_ = Sigma_inv
        self.n_samples_ = 0
        self.n_per_class_ = {int(c): 0 for c in self.class_codes_}
        self.is_fitted_ = True

        return self

    # ------------------------------------------------------------------
    # Discriminant functions
    # ------------------------------------------------------------------

    def _discriminant_scores(self, X_std: np.ndarray) -> np.ndarray:
        """
        Compute linear discriminant score δ_k(x) for all classes.

        δ_k(x) = x^T Σ⁻¹ μ_k  −  ½ μ_k^T Σ⁻¹ μ_k  +  log(π_k)

        Parameters
        ----------
        X_std : (N, p) standardized predictor matrix

        Returns
        -------
        scores : (N, K) array of δ_k values
        """
        K = len(self.class_codes_)
        N = X_std.shape[0]
        scores = np.zeros((N, K))

        for k in range(K):
            mu_k = self.mu_[k]
            # Σ⁻¹ μ_k
            Sigma_inv_mu = self.Sigma_inv_ @ mu_k
            # x^T Σ⁻¹ μ_k  for all rows at once
            scores[:, k] = (X_std @ Sigma_inv_mu
                            - 0.5 * mu_k @ Sigma_inv_mu
                            + np.log(self.priors_[k] + 1e-12))

        return scores

    # ------------------------------------------------------------------
    # Mahalanobis distances
    # ------------------------------------------------------------------

    def mahalanobis_distances(self, X: np.ndarray) -> np.ndarray:
        """
        Compute Mahalanobis distance from each observation to each class mean.

        D²_k(x) = (x − μ_k)^T Σ⁻¹ (x − μ_k)

        Parameters
        ----------
        X : (N, p) raw predictor matrix

        Returns
        -------
        D2 : (N, K) Mahalanobis distances squared
        """
        self._check_fitted()
        X_std = self._standardize(X)
        N, K = X_std.shape[0], len(self.class_codes_)
        D2 = np.zeros((N, K))

        for k in range(K):
            diff = X_std - self.mu_[k]
            # D²_k = diag(diff @ Σ⁻¹ @ diff^T)
            D2[:, k] = np.einsum("ij,jl,il->i", diff, self.Sigma_inv_, diff)

        return D2

    # ------------------------------------------------------------------
    # Predict
    # ------------------------------------------------------------------

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict LEC class code for each observation.

        Parameters
        ----------
        X : (N, p) or (p,) predictor array

        Returns
        -------
        labels : (N,) array of LEC class codes
        """
        self._check_fitted()
        X = np.atleast_2d(np.asarray(X, dtype=float))
        X_std = self._standardize(X)
        scores = self._discriminant_scores(X_std)
        k_pred = np.argmax(scores, axis=1)
        return self.class_codes_[k_pred]

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Compute posterior probability P(G=k | X=x) for each class.

        Uses softmax of discriminant scores:
          P(G=k|x) = exp(δ_k) / Σ_l exp(δ_l)

        Parameters
        ----------
        X : (N, p) or (p,) predictor array

        Returns
        -------
        proba : (N, K) posterior probability matrix
                columns correspond to class_codes_ order
        """
        self._check_fitted()
        X = np.atleast_2d(np.asarray(X, dtype=float))
        X_std = self._standardize(X)
        scores = self._discriminant_scores(X_std)

        # Numerically stable softmax
        scores -= scores.max(axis=1, keepdims=True)
        exp_scores = np.exp(scores)
        proba = exp_scores / exp_scores.sum(axis=1, keepdims=True)
        return proba

    def predict_with_confidence(
        self, X: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Returns predicted class, posterior probabilities, and Mahalanobis D².

        Returns
        -------
        labels : (N,) predicted LEC class codes
        proba  : (N, K) posterior probabilities per class
        D2     : (N, K) Mahalanobis distances to each class mean
        """
        labels = self.predict(X)
        proba = self.predict_proba(X)
        D2 = self.mahalanobis_distances(X)
        return labels, proba, D2

    # ------------------------------------------------------------------
    # Discriminant function coefficients
    # ------------------------------------------------------------------

    def discriminant_coefficients(self) -> pd.DataFrame:
        """
        Return the LDA scoring coefficients in a readable DataFrame.

        Each column is one LEC class; each row is one predictor.
        The value is the coefficient applied to x when computing δ_k(x):

            coefficient_kj = (Σ⁻¹ μ_k)_j

        These are the direct analogs to regression coefficients.
        High absolute value → that predictor strongly separates class k.
        """
        self._check_fitted()
        coefs = self.Sigma_inv_ @ self.mu_.T  # (p, K)
        df = pd.DataFrame(
            coefs,
            index=PREDICTOR_NAMES,
            columns=[LEC_CLASSES[c] for c in self.class_codes_],
        )
        return df

    def class_centroids_raw(self) -> pd.DataFrame:
        """Class mean vectors in original (un-standardized) predictor space."""
        self._check_fitted()
        mu_raw = self.mu_ * self.x_std_ + self.x_mean_
        return pd.DataFrame(
            mu_raw,
            index=[LEC_CLASSES[c] for c in self.class_codes_],
            columns=PREDICTOR_NAMES,
        )

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save model parameters to a JSON file."""
        self._check_fitted()
        data = {
            "class_codes": self.class_codes_.tolist(),
            "priors": self.priors_.tolist(),
            "mu": self.mu_.tolist(),
            "Sigma": self.Sigma_.tolist(),
            "x_mean": self.x_mean_.tolist(),
            "x_std": self.x_std_.tolist(),
            "n_samples": self.n_samples_,
            "n_per_class": self.n_per_class_,
            "regularization": self.regularization,
            "predictor_names": PREDICTOR_NAMES,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Model saved → {path}")

    @classmethod
    def load(cls, path: str) -> "PiedmontLDA":
        """Load a saved model from JSON."""
        with open(path) as f:
            data = json.load(f)

        model = cls(
            class_codes=np.array(data["class_codes"]),
            regularization=data["regularization"],
        )
        model.mu_ = np.array(data["mu"])
        Sigma = np.array(data["Sigma"])
        model.Sigma_ = Sigma
        model.Sigma_inv_ = np.linalg.pinv(Sigma)
        model.priors_ = np.array(data["priors"])
        model.x_mean_ = np.array(data["x_mean"])
        model.x_std_ = np.array(data["x_std"])
        model.n_samples_ = data["n_samples"]
        model.n_per_class_ = data["n_per_class"]
        model.is_fitted_ = True

        # Validate predictor names match
        if data.get("predictor_names") != PREDICTOR_NAMES:
            warnings.warn("Saved model predictor names differ from current.")

        return model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        if self.x_std_ is None:
            return X
        return (X - self.x_mean_) / self.x_std_

    def _check_fitted(self):
        if not self.is_fitted_:
            raise RuntimeError("Model not fitted. Call fit() or fit_from_literature().")

    def __repr__(self):
        status = "fitted" if self.is_fitted_ else "unfitted"
        n = self.n_samples_ if self.n_samples_ else "literature"
        return f"PiedmontLDA({status}, n_training={n}, K={len(self.class_codes_)})"


# ---------------------------------------------------------------------------
# Convenience: build default literature-seeded model
# ---------------------------------------------------------------------------

def build_literature_model(save_path: str = None) -> PiedmontLDA:
    """
    Build and return the literature-seeded LDA model ready for prediction.
    Optionally save to JSON.
    """
    model = PiedmontLDA()
    model.fit_from_literature()

    print("=== Piedmont LDA (Literature-Seeded) ===")
    print(f"  Classes: {len(model.class_codes_)}")
    print(f"  Predictors: {N_PREDICTORS}")
    print(f"\nClass centroids (raw predictor space):")
    print(model.class_centroids_raw().round(2).to_string())

    print(f"\nDiscriminant coefficients (Σ⁻¹μ_k):")
    print(model.discriminant_coefficients().round(3).to_string())

    if save_path:
        model.save(save_path)

    return model


def build_from_training(
    training_csv: str,
    save_path: str = None,
    augment_synthetic: bool = True,
    min_per_class: int = 50,
) -> PiedmontLDA:
    """
    Fit LDA from a field training CSV (or synthetic CSV).

    Parameters
    ----------
    training_csv : path to CSV with PREDICTOR_NAMES columns + 'lec_class'
    save_path : if provided, save fitted model here
    augment_synthetic : add synthetic samples to undersampled classes
    min_per_class : minimum samples per class before augmenting
    """
    from models.synthetic_data import augment_with_synthetic

    df = pd.read_csv(training_csv)
    print(f"Loaded {len(df)} training observations from {training_csv}")
    print(df.groupby("lec_class").size().to_string())

    if augment_synthetic:
        print("\nAugmenting undersampled classes with synthetic data...")
        df = augment_with_synthetic(df, min_per_class=min_per_class)

    X = df[PREDICTOR_NAMES].values
    y = df["lec_class"].values

    model = PiedmontLDA()
    model.fit(X, y)

    print(f"\nFitted LDA: N={model.n_samples_}, K={len(model.class_codes_)}")
    print("Samples per class:", model.n_per_class_)

    if save_path:
        model.save(save_path)

    return model


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Piedmont LDA model builder")
    parser.add_argument("--literature", action="store_true",
                        help="Build literature-seeded model (no field data needed)")
    parser.add_argument("--training-csv", type=str,
                        help="Path to training CSV for field-data fit")
    parser.add_argument("--save", type=str, default="data/models/piedmont_lda.json",
                        help="Output path for saved model JSON")
    parser.add_argument("--coefficients", action="store_true",
                        help="Print discriminant coefficients and exit")
    args = parser.parse_args()

    if args.training_csv:
        model = build_from_training(args.training_csv, save_path=args.save)
    else:
        model = build_literature_model(save_path=args.save)

    if args.coefficients:
        print("\n=== Discriminant Coefficients ===")
        print(model.discriminant_coefficients().round(3).to_string())
