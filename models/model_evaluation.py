"""
Model Evaluation and Cross-Validation for Piedmont LEC Classifier

Implements:
  1. k-fold cross-validation
  2. Leave-one-out cross-validation (LOOCV)
  3. Confusion matrix and per-class accuracy metrics
  4. Cohen's Kappa coefficient
  5. Brier score (calibration quality)
  6. Feature importance via permutation
  7. Class separability (canonical discriminant scores)
  8. Diagnostic plots (when matplotlib available)

Usage
-----
    # Evaluate literature model on synthetic data
    python models/model_evaluation.py --synthetic --n 300

    # Evaluate on field training CSV
    python models/model_evaluation.py --training-csv data/field/training/field_data.csv

    # Full cross-validation report
    python models/model_evaluation.py --training-csv data/field/training/field_data.csv \\
        --kfold 10 --report
"""

import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from models.terrain_math import PREDICTOR_NAMES, N_PREDICTORS
from models.lda_model import PiedmontLDA
from models.piedmont_classes import CLASS_CODES, LEC_CLASSES


# ---------------------------------------------------------------------------
# Confusion matrix
# ---------------------------------------------------------------------------

def confusion_matrix(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    class_codes: np.ndarray = CLASS_CODES,
) -> np.ndarray:
    """
    Compute K×K confusion matrix.

    C[i, j] = number of observations of true class i predicted as class j.

    Returns
    -------
    np.ndarray (K, K) of counts
    """
    K = len(class_codes)
    C = np.zeros((K, K), dtype=int)
    code_idx = {c: i for i, c in enumerate(class_codes)}

    for true, pred in zip(y_true, y_pred):
        if true in code_idx and pred in code_idx:
            C[code_idx[true], code_idx[pred]] += 1

    return C


def accuracy_metrics(
    C: np.ndarray,
    class_codes: np.ndarray = CLASS_CODES,
) -> pd.DataFrame:
    """
    Compute per-class precision, recall (producer's accuracy),
    F1 score, and overall accuracy from a confusion matrix.

    Terminology (remote sensing convention):
      Producer's Accuracy = Recall = TP / (TP + FN) = diagonal / row sum
      User's Accuracy    = Precision = TP / (TP + FP) = diagonal / col sum
      F1 = 2 * PA * UA / (PA + UA)
    """
    rows = []
    K = len(class_codes)
    total = C.sum()

    for i, code in enumerate(class_codes):
        n_true = C[i, :].sum()      # all observations of this class
        n_pred = C[:, i].sum()      # all predictions of this class
        tp = C[i, i]

        pa = tp / n_true if n_true > 0 else 0.0   # producer's accuracy
        ua = tp / n_pred if n_pred > 0 else 0.0   # user's accuracy
        f1 = 2 * pa * ua / (pa + ua) if (pa + ua) > 0 else 0.0

        rows.append({
            "class": code,
            "name": LEC_CLASSES[code],
            "n_samples": int(n_true),
            "producers_acc": round(pa, 4),
            "users_acc": round(ua, 4),
            "f1_score": round(f1, 4),
            "correct": int(tp),
        })

    df = pd.DataFrame(rows)
    overall_acc = np.diag(C).sum() / total if total > 0 else 0.0
    df.attrs["overall_accuracy"] = overall_acc
    return df


def cohens_kappa(C: np.ndarray) -> float:
    """
    Cohen's Kappa coefficient — measures agreement correcting for chance.

    κ = (P_o − P_e) / (1 − P_e)

    where P_o = observed accuracy, P_e = expected (chance) accuracy.

    κ interpretation:
      > 0.80 → almost perfect agreement
      0.60–0.80 → substantial
      0.40–0.60 → moderate
      0.20–0.40 → fair
      < 0.20 → slight
    """
    N = C.sum()
    if N == 0:
        return 0.0
    P_o = np.diag(C).sum() / N
    row_sums = C.sum(axis=1)
    col_sums = C.sum(axis=0)
    P_e = (row_sums * col_sums).sum() / (N ** 2)
    return float((P_o - P_e) / (1.0 - P_e)) if P_e < 1.0 else 0.0


# ---------------------------------------------------------------------------
# Brier score (probability calibration quality)
# ---------------------------------------------------------------------------

def brier_score(
    y_true: np.ndarray,
    y_proba: np.ndarray,
    class_codes: np.ndarray = CLASS_CODES,
) -> float:
    """
    Multi-class Brier score — measures calibration of posterior probabilities.

    BS = (1/N) * Σ_i Σ_k (p_ik − 1{y_i == k})²

    Lower is better. Perfect model = 0. Random classifier ≈ (K-1)/K.

    Parameters
    ----------
    y_true : (N,) true class labels
    y_proba : (N, K) predicted posterior probabilities
    """
    K = len(class_codes)
    code_idx = {c: i for i, c in enumerate(class_codes)}
    N = len(y_true)

    BS = 0.0
    for i in range(N):
        true_k = code_idx.get(int(y_true[i]), -1)
        if true_k < 0:
            continue
        for k in range(K):
            indicator = 1.0 if k == true_k else 0.0
            BS += (y_proba[i, k] - indicator) ** 2

    return BS / N


# ---------------------------------------------------------------------------
# k-fold cross-validation
# ---------------------------------------------------------------------------

def kfold_cross_validate(
    X: np.ndarray,
    y: np.ndarray,
    k: int = 10,
    seed: int = 42,
    augment_synthetic: bool = False,
    min_per_class: int = 30,
) -> Dict:
    """
    Perform stratified k-fold cross-validation on the LDA model.

    In each fold:
      - Fit LDA on k-1 folds
      - Predict on held-out fold
      - Record predictions and posterior probabilities

    Returns dict with:
      overall_accuracy, kappa, brier_score, confusion_matrix,
      per_class_metrics, fold_accuracies
    """
    rng = np.random.default_rng(seed)
    N = len(X)

    # Stratified fold assignments
    fold_ids = np.zeros(N, dtype=int)
    for code in CLASS_CODES:
        idx = np.where(y == code)[0]
        rng.shuffle(idx)
        folds_for_class = np.array_split(idx, k)
        for fold, members in enumerate(folds_for_class):
            fold_ids[members] = fold

    y_pred_all = np.zeros(N, dtype=int)
    y_proba_all = np.zeros((N, len(CLASS_CODES)))
    fold_accs = []

    for fold in range(k):
        test_mask  = fold_ids == fold
        train_mask = ~test_mask

        X_train, y_train = X[train_mask], y[train_mask]
        X_test,  y_test  = X[test_mask],  y[test_mask]

        if augment_synthetic:
            from models.synthetic_data import augment_with_synthetic
            df_train = pd.DataFrame(X_train, columns=PREDICTOR_NAMES)
            df_train["lec_class"] = y_train
            df_train = augment_with_synthetic(df_train, min_per_class=min_per_class)
            X_train = df_train[PREDICTOR_NAMES].values
            y_train = df_train["lec_class"].values

        model = PiedmontLDA()
        try:
            model.fit(X_train, y_train, standardize=True)
        except ValueError as e:
            print(f"  Fold {fold+1} skipped: {e}")
            continue

        preds, proba, _ = model.predict_with_confidence(X_test)
        y_pred_all[test_mask]   = preds
        y_proba_all[test_mask]  = proba

        fold_acc = (preds == y_test).mean()
        fold_accs.append(fold_acc)
        print(f"  Fold {fold+1}/{k}: acc={fold_acc:.3f}")

    C = confusion_matrix(y, y_pred_all)
    metrics = accuracy_metrics(C)
    kappa = cohens_kappa(C)
    bs = brier_score(y, y_proba_all)
    oa = metrics.attrs["overall_accuracy"]

    return {
        "overall_accuracy": oa,
        "kappa": kappa,
        "brier_score": bs,
        "confusion_matrix": C,
        "per_class_metrics": metrics,
        "fold_accuracies": fold_accs,
        "fold_acc_mean": float(np.mean(fold_accs)),
        "fold_acc_std": float(np.std(fold_accs)),
        "y_pred": y_pred_all,
        "y_proba": y_proba_all,
    }


# ---------------------------------------------------------------------------
# Permutation feature importance
# ---------------------------------------------------------------------------

def permutation_importance(
    model: PiedmontLDA,
    X: np.ndarray,
    y: np.ndarray,
    n_repeats: int = 20,
    seed: int = 0,
) -> pd.DataFrame:
    """
    Measure predictor importance by permuting each feature and measuring
    the drop in overall accuracy.

    Importance_j = baseline_accuracy − mean(accuracy with column j shuffled)

    Higher value → that predictor contributes more to classification accuracy.

    Parameters
    ----------
    model : fitted PiedmontLDA
    X : (N, p) predictor matrix
    y : (N,) true class labels
    n_repeats : number of shuffles per feature
    """
    rng = np.random.default_rng(seed)
    baseline = (model.predict(X) == y).mean()

    results = []
    for j, name in enumerate(PREDICTOR_NAMES):
        drops = []
        for _ in range(n_repeats):
            X_perm = X.copy()
            rng.shuffle(X_perm[:, j])
            acc_perm = (model.predict(X_perm) == y).mean()
            drops.append(baseline - acc_perm)
        results.append({
            "predictor": name,
            "importance_mean": float(np.mean(drops)),
            "importance_std":  float(np.std(drops)),
        })

    df = pd.DataFrame(results).sort_values("importance_mean", ascending=False)
    df.attrs["baseline_accuracy"] = baseline
    return df


# ---------------------------------------------------------------------------
# Canonical discriminant scores (2D projection)
# ---------------------------------------------------------------------------

def canonical_scores(
    model: PiedmontLDA,
    X: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Project data onto the first two canonical discriminant axes.

    The canonical axes are the eigenvectors of:
        W^{-1} B

    where W = within-class scatter, B = between-class scatter.

    This is the classical "discriminant plot" showing maximum separation.

    Returns
    -------
    Z : (N, 2) canonical scores for each observation
    eigenvalues : (2,) proportion of between-class variance explained
    """
    model._check_fitted()
    X_std = model._standardize(np.asarray(X, dtype=float))
    K = len(model.class_codes_)

    # Between-class scatter: B = Σ_k n_k (μ_k - μ_grand)(μ_k - μ_grand)^T
    n_per = np.array([model.n_per_class_.get(int(c), 1)
                      for c in model.class_codes_], dtype=float)
    mu_grand = (n_per[:, None] * model.mu_).sum(axis=0) / n_per.sum()
    B = np.zeros((N_PREDICTORS, N_PREDICTORS))
    for k in range(K):
        diff = model.mu_[k] - mu_grand
        B += n_per[k] * np.outer(diff, diff)

    W = model.Sigma_ * (model.n_samples_ - K) if model.n_samples_ > 0 else model.Sigma_

    try:
        W_inv = np.linalg.inv(W)
    except np.linalg.LinAlgError:
        W_inv = np.linalg.pinv(W)

    WB = W_inv @ B
    eigenvalues, eigenvectors = np.linalg.eig(WB)

    # Sort by descending eigenvalue (real part)
    order = np.argsort(eigenvalues.real)[::-1]
    eigenvalues = eigenvalues.real[order]
    eigenvectors = eigenvectors.real[:, order]

    Z = X_std @ eigenvectors[:, :2]
    total_var = eigenvalues.sum()
    prop_explained = eigenvalues[:2] / total_var if total_var > 0 else eigenvalues[:2]

    return Z, prop_explained


# ---------------------------------------------------------------------------
# Full evaluation report
# ---------------------------------------------------------------------------

def full_report(
    X: np.ndarray,
    y: np.ndarray,
    k_folds: int = 10,
    save_dir: Optional[str] = None,
) -> None:
    """
    Print a complete model evaluation report including:
      - Cross-validation accuracy
      - Confusion matrix
      - Per-class metrics
      - Kappa
      - Brier score
      - Feature importance
    """
    print("=" * 65)
    print("Piedmont LEC — Model Evaluation Report")
    print("=" * 65)
    print(f"\nDataset: {len(X)} observations, {N_PREDICTORS} predictors")
    print(f"Classes: {dict((c, (y==c).sum()) for c in CLASS_CODES)}")

    print(f"\n--- {k_folds}-Fold Cross-Validation ---")
    cv = kfold_cross_validate(X, y, k=k_folds)

    print(f"\n  Overall Accuracy:  {cv['overall_accuracy']:.4f}")
    print(f"  Cohen's Kappa:     {cv['kappa']:.4f}  ", end="")
    k = cv['kappa']
    if k > 0.80:   print("(Almost perfect)")
    elif k > 0.60: print("(Substantial)")
    elif k > 0.40: print("(Moderate)")
    elif k > 0.20: print("(Fair)")
    else:          print("(Slight)")
    print(f"  Brier Score:       {cv['brier_score']:.4f}  "
          f"(0=perfect, {(len(CLASS_CODES)-1)/len(CLASS_CODES):.2f}=random)")
    print(f"  Fold accuracy:     {cv['fold_acc_mean']:.3f} ± {cv['fold_acc_std']:.3f}")

    print(f"\n--- Confusion Matrix ---")
    C = cv["confusion_matrix"]
    names = [LEC_CLASSES[c][:16] for c in CLASS_CODES]
    header = f"{'True \\ Pred':<20}" + "".join(f"{n[:6]:>8}" for n in names)
    print(header)
    for i, code in enumerate(CLASS_CODES):
        row = f"  {LEC_CLASSES[code][:18]:<18}" + "".join(f"{C[i,j]:>8}" for j in range(len(CLASS_CODES)))
        print(row)

    print(f"\n--- Per-Class Accuracy ---")
    metrics = cv["per_class_metrics"]
    print(f"{'Class':<35} {'N':>6} {'PA':>8} {'UA':>8} {'F1':>8}")
    print("-" * 65)
    for _, row in metrics.iterrows():
        print(f"  {row['name']:<33} {row['n_samples']:>6} "
              f"{row['producers_acc']:>8.3f} {row['users_acc']:>8.3f} "
              f"{row['f1_score']:>8.3f}")

    print(f"\n--- Feature Importance (Permutation) ---")
    model_full = PiedmontLDA()
    model_full.fit(X, y)
    importance = permutation_importance(model_full, X, y, n_repeats=15)
    print(f"  Baseline accuracy: {importance.attrs['baseline_accuracy']:.4f}")
    print(f"  {'Predictor':<25} {'Importance':>12} {'± SD':>8}")
    print("  " + "-" * 45)
    for _, row in importance.iterrows():
        bar = "█" * max(0, int(row["importance_mean"] * 200))
        print(f"  {row['predictor']:<25} {row['importance_mean']:>12.4f} "
              f"±{row['importance_std']:>6.4f}  {bar}")

    if save_dir:
        out = Path(save_dir)
        out.mkdir(parents=True, exist_ok=True)

        # Save confusion matrix
        C_df = pd.DataFrame(C, index=[LEC_CLASSES[c] for c in CLASS_CODES],
                            columns=[LEC_CLASSES[c] for c in CLASS_CODES])
        C_df.to_csv(out / "confusion_matrix.csv")

        # Save per-class metrics
        metrics.to_csv(out / "per_class_metrics.csv", index=False)

        # Save feature importance
        importance.to_csv(out / "feature_importance.csv", index=False)

        # Save summary
        summary = {
            "overall_accuracy": cv["overall_accuracy"],
            "kappa": cv["kappa"],
            "brier_score": cv["brier_score"],
            "fold_acc_mean": cv["fold_acc_mean"],
            "fold_acc_std": cv["fold_acc_std"],
            "n_samples": len(X),
            "k_folds": k_folds,
        }
        pd.Series(summary).to_csv(out / "summary.csv", header=["value"])
        print(f"\nResults saved → {save_dir}/")

    try:
        _plot_evaluation(cv, X, y, model_full, save_dir)
    except Exception as e:
        print(f"\n(Visualization skipped: {e})")


def _plot_evaluation(cv, X, y, model, save_dir):
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    from models.piedmont_classes import LEC_COLORS

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    # 1. Confusion matrix heatmap
    ax = axes[0]
    C = cv["confusion_matrix"]
    K = len(CLASS_CODES)
    C_norm = C / C.sum(axis=1, keepdims=True).clip(min=1)
    im = ax.imshow(C_norm, cmap="Blues", vmin=0, vmax=1)
    plt.colorbar(im, ax=ax)
    labels = [LEC_CLASSES[c][:12] for c in CLASS_CODES]
    ax.set_xticks(range(K)); ax.set_xticklabels(labels, rotation=40, ha="right", fontsize=8)
    ax.set_yticks(range(K)); ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel("Predicted"); ax.set_ylabel("True")
    ax.set_title(f"Confusion Matrix (OA={cv['overall_accuracy']:.3f})")
    for i in range(K):
        for j in range(K):
            ax.text(j, i, str(C[i, j]), ha="center", va="center", fontsize=7,
                    color="white" if C_norm[i, j] > 0.5 else "black")

    # 2. Canonical discriminant plot (first 2 axes)
    ax = axes[1]
    Z, prop = canonical_scores(model, X)
    for code in CLASS_CODES:
        mask = y == code
        ax.scatter(Z[mask, 0], Z[mask, 1], c=LEC_COLORS[code],
                   label=f"{code}: {LEC_CLASSES[code][:14]}", alpha=0.4, s=12)
    ax.set_xlabel(f"CDA 1 ({100*prop[0]:.0f}% var)")
    ax.set_ylabel(f"CDA 2 ({100*prop[1]:.0f}% var)")
    ax.set_title("Canonical Discriminant Plot")
    ax.legend(fontsize=7)

    # 3. Per-class F1 bar chart
    ax = axes[2]
    metrics = cv["per_class_metrics"]
    colors = [LEC_COLORS[c] for c in metrics["class"]]
    ax.barh(metrics["name"], metrics["f1_score"], color=colors)
    ax.set_xlim(0, 1)
    ax.axvline(0.8, color="gray", linestyle="--", linewidth=1, label="0.80")
    ax.set_xlabel("F1 Score")
    ax.set_title(f"Per-Class F1  (κ={cv['kappa']:.3f})")
    for i, (_, row) in enumerate(metrics.iterrows()):
        ax.text(row["f1_score"] + 0.01, i, f"{row['f1_score']:.2f}", va="center", fontsize=8)
    ax.legend(fontsize=8)

    plt.suptitle("Piedmont LEC — Model Evaluation", fontsize=13)
    plt.tight_layout()

    if save_dir:
        path = Path(save_dir) / "evaluation_plots.png"
        plt.savefig(path, dpi=150, bbox_inches="tight")
        print(f"Plots saved → {path}")
    plt.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Piedmont LEC model")
    parser.add_argument("--synthetic", action="store_true",
                        help="Evaluate on synthetic data")
    parser.add_argument("--n-per-class", type=int, default=300)
    parser.add_argument("--training-csv", type=str)
    parser.add_argument("--kfold", type=int, default=10)
    parser.add_argument("--report", action="store_true")
    parser.add_argument("--save", type=str, default="data/outputs/evaluation/")
    args = parser.parse_args()

    if args.synthetic:
        from models.synthetic_data import generate_training_dataset
        print(f"Generating {args.n_per_class} synthetic samples per class...")
        df = generate_training_dataset(args.n_per_class)
        X = df[PREDICTOR_NAMES].values
        y = df["lec_class"].values
    elif args.training_csv:
        df = pd.read_csv(args.training_csv)
        X = df[PREDICTOR_NAMES].values
        y = df["lec_class"].values
    else:
        print("Specify --synthetic or --training-csv")
        parser.print_help()
        exit(1)

    full_report(X, y, k_folds=args.kfold,
                save_dir=args.save if args.report else None)
