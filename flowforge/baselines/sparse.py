"""Classical sparse-regression baseline (RP2 control).

Deterministic ElasticNet + OLS refit baseline that emits an ordinary DSL
candidate so it is scored by exactly the same code as agent candidates.
"""
from __future__ import annotations

import numpy as np

__all__ = ["evaluate_sparse_baseline", "fit_sparse_baseline"]

_FEATURE_NAMES = ("1", "I1", "I2", "I3", "I4", "I5", "I1*I2", "tanh(I1)", "tanh(I2)")
_TENSOR_NAMES = ("T1", "T2", "T3")
_ALPHA_GRID = (1e-6, 1e-5, 1e-4, 1e-3, 1e-2)
_N_FOLDS = 3
_N_COMPONENTS = 9
# Frozen collinearity rule (RP2 fairness, decided before experiments):
# scalar features duplicating an earlier one with |corr > threshold| are
# removed from the library. 0.999 keeps tanh() on unit-scale synthetic data
# (corr ~0.998) but drops it on real frozen-RANS data where tanh(I) == I to
# 1e-6 (corr > 0.999999), along with I1*I2 which duplicates I5 exactly.
_COLLINEARITY_THRESHOLD = 0.999


def _feature_values(name: str, invariants: dict[str, np.ndarray]) -> np.ndarray:
    """Evaluate scalar feature ``name`` on ``invariants``."""
    if name == "1":
        ref = np.asarray(invariants["I1"], dtype=float)
        return np.ones_like(ref)
    if name == "I1*I2":
        first = np.asarray(invariants["I1"], dtype=float)
        second = np.asarray(invariants["I2"], dtype=float)
        return first * second
    if name == "tanh(I1)":
        return np.tanh(np.asarray(invariants["I1"], dtype=float))
    if name == "tanh(I2)":
        return np.tanh(np.asarray(invariants["I2"], dtype=float))
    return np.asarray(invariants[name], dtype=float)


def _scalar_corr(first: np.ndarray, second: np.ndarray) -> float:
    """Pearson correlation, 0.0 when either input is constant."""
    a = np.asarray(first, dtype=float).reshape(-1)
    b = np.asarray(second, dtype=float).reshape(-1)
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.sqrt(float(a @ a) * float(b @ b)))
    if denom == 0.0:
        return 0.0
    return float((a @ b) / denom)


def collinearity_dropped_features(
    invariants: dict[str, np.ndarray],
    feature_names: tuple[str, ...] | list[str] | None = None,
    threshold: float = _COLLINEARITY_THRESHOLD,
) -> tuple[list[str], list[str]]:
    """Split scalar features into kept/dropped by the frozen collinearity rule.

    The first feature in ``_FEATURE_NAMES`` order is always kept (in
    particular the constant ``"1"``); a later feature is dropped when its
    absolute correlation with any kept feature exceeds ``threshold``.
    Deterministic: same inputs always give the same split.
    """
    names = list(feature_names) if feature_names is not None else list(_FEATURE_NAMES)
    values = {name: _feature_values(name, invariants) for name in names}
    kept: list[str] = []
    dropped: list[str] = []
    for name in names:
        duplicate = any(
            abs(_scalar_corr(values[name], values[other])) > float(threshold)
            for other in kept
        )
        (dropped if duplicate else kept).append(name)
    return kept, dropped


def _project_symmetric_traceless(raw: np.ndarray) -> np.ndarray:
    """Symmetric-traceless projection (same as ``candidate_anisotropy``)."""
    sym = 0.5 * (raw + np.swapaxes(raw, -1, -2))
    trace = np.trace(sym, axis1=-2, axis2=-1)[..., None, None]
    return sym - (1.0 / 3.0) * trace * np.eye(3)


def _format_term(coef: float, feature: str, tensor: str) -> str:
    """Format one DSL term ``c * f * T_k`` (``c * T_k`` for f == 1)."""
    coef_text = repr(float(coef))
    if float(coef) < 0:
        coef_text = f"({coef_text})"
    if feature == "1":
        return f"{coef_text} * {tensor}"
    return f"{coef_text} * {feature} * {tensor}"


def _round_sig(value: float, digits: int = 4) -> float:
    """Round to ``digits`` significant digits (0 stays 0)."""
    if value == 0.0 or not np.isfinite(value):
        return float(value)
    return float(f"{value:.{digits}g}")


def _build_design(
    invariants: dict[str, np.ndarray],
    basis: dict[str, np.ndarray],
    feature_names: tuple[str, ...] | list[str] | None = None,
) -> tuple[np.ndarray, list[tuple[str, str]], int]:
    """Build the flattened library matrix.

    Args:
        invariants: Mapping ``I1..I5`` to ``(N,)`` arrays.
        basis: Mapping with at least ``T1..T3`` to ``(N, 3, 3)`` arrays.
        feature_names: Scalar features to include (default: all of
            ``_FEATURE_NAMES``; pass the kept list from
            :func:`collinearity_dropped_features`).

    Returns:
        ``(design, pairs, n_points)`` where ``design`` is ``(N*9, P)``,
        ``pairs`` lists the ``(feature, tensor)`` for each column and
        ``n_points`` is ``N``.
    """
    names = list(feature_names) if feature_names is not None else list(_FEATURE_NAMES)
    pairs: list[tuple[str, str]] = []
    flat_columns: list[np.ndarray] = []
    for tensor in _TENSOR_NAMES:
        basis_arr = np.asarray(basis[tensor], dtype=float)
        for feature in names:
            feat = _feature_values(feature, invariants)
            raw = feat[..., None, None] * basis_arr
            dev = _project_symmetric_traceless(raw)
            flat_columns.append(np.asarray(dev.reshape(-1), dtype=float))
            pairs.append((feature, tensor))
    design = np.column_stack(flat_columns)
    ref = np.asarray(invariants["I1"], dtype=float)
    n_points = int(ref.shape[0])
    return design, pairs, n_points


def _fit_pruned_refit(
    design_train: np.ndarray,
    response_train: np.ndarray,
    alpha: float,
    l1_ratio: float,
    seed: int,
    max_terms: int,
) -> tuple[list[int], np.ndarray]:
    """Standardized ElasticNet + prune + OLS refit on one train block.

    Columns are standardized to unit L2 norm before the elastic net and
    coefficients are mapped back to the original scale afterwards. Ranking
    uses ``|coef_orig| * col_norm`` (equal to ``|coef_scaled|``).

    Args:
        design_train: ``(M, P)`` library matrix on train rows.
        response_train: ``(M,)`` response on train rows.
        alpha: ElasticNet penalty strength.
        l1_ratio: ElasticNet mixing parameter.
        seed: Random seed for ElasticNet.
        max_terms: Keep at most this many columns.

    Returns:
        ``(kept, refit)`` with kept column indices and OLS coefficients on
        the original scale (empty when nothing survives)."
    """
    from sklearn.linear_model import ElasticNet

    norms = np.linalg.norm(design_train, axis=0)
    safe = np.where(norms == 0.0, 1.0, norms)
    scaled = design_train / safe
    model = ElasticNet(
        alpha=alpha,
        l1_ratio=l1_ratio,
        fit_intercept=False,
        random_state=seed,
        max_iter=20000,
    )
    model.fit(scaled, response_train)
    coef_scaled = np.asarray(model.coef_, dtype=float)
    coef_orig = coef_scaled / safe
    scores = np.abs(coef_orig) * norms
    order = np.argsort(-scores, kind="stable")
    kept: list[int] = [int(i) for i in order if scores[int(i)] > 0.0][: int(max_terms)]
    if not kept:
        return [], np.zeros((0,), dtype=float)
    refit, _, _, _ = np.linalg.lstsq(design_train[:, kept], response_train, rcond=None)
    return kept, np.asarray(refit, dtype=float)


def _contiguous_point_folds(n_points: int, n_folds: int = _N_FOLDS) -> list[np.ndarray]:
    """Split point indices into contiguous folds.

    Args:
        n_points: Number of training points (rows before flattening).
        n_folds: Number of folds.

    Returns:
        List of ``(n_fold,)`` index arrays in point order.
    """
    indices = np.arange(int(n_points))
    return [np.asarray(part, dtype=int) for part in np.array_split(indices, int(n_folds))]


def _cv_errors_for_grid(
    design: np.ndarray,
    response: np.ndarray,
    n_points: int,
    alphas: tuple[float, ...] | list[float],
    l1_ratio: float,
    seed: int,
    max_terms: int,
) -> dict[float, float]:
    """Deterministic CV error for each alpha.

    Folds are contiguous over training points (not over flattened tensor
    components). For each held-out fold the final pruned+refit model is fit
    on the other folds and its held-out MSE is recorded; the per-alpha error
    is the mean over folds.

    Args:
        design: ``(N*9, P)`` library matrix.
        response: ``(N*9,)`` response.
        n_points: ``N`` (points before flattening).
        alphas: Grid of ElasticNet strengths in order.
        l1_ratio: ElasticNet mixing parameter.
        seed: Random seed for ElasticNet.
        max_terms: Keep at most this many columns per refit.

    Returns:
        Mapping ``alpha -> mean held-out MSE`` in grid order.
    """
    folds = _contiguous_point_folds(n_points, _N_FOLDS)
    comp = np.arange(_N_COMPONENTS)
    errors: dict[float, float] = {}
    for alpha in list(alphas):
        fold_mses: list[float] = []
        for pos in range(len(folds)):
            test_points = folds[pos]
            if test_points.size == 0:
                continue
            train_points = np.concatenate(
                [folds[j] for j in range(len(folds)) if j != pos]
            )
            test_rows = (test_points[:, None] * _N_COMPONENTS + comp).reshape(-1)
            train_rows = (train_points[:, None] * _N_COMPONENTS + comp).reshape(-1)
            design_train = design[train_rows]
            response_train = response[train_rows]
            design_test = design[test_rows]
            response_test = response[test_rows]
            kept, refit = _fit_pruned_refit(
                design_train, response_train, float(alpha), l1_ratio, seed, max_terms
            )
            if not kept:
                pred = np.zeros_like(response_test)
            else:
                pred = design_test[:, kept] @ refit
            fold_mses.append(float(np.mean((pred - response_test) ** 2)))
        errors[float(alpha)] = float(np.mean(fold_mses)) if fold_mses else float("inf")
    return errors


def _best_alpha(errors: dict[float, float], alphas: tuple[float, ...] | list[float]) -> float:
    """Pick the grid alpha with smallest CV error (first tie wins).

    Args:
        errors: Mapping ``alpha -> CV error``.
        alphas: Grid order used to break ties deterministically.

    Returns:
        The winning alpha as a float.
    """
    best = float(next(iter(alphas)))
    best_err = float(errors[best])
    for alpha in list(alphas)[1:]:
        key = float(alpha)
        err = float(errors[key])
        if err < best_err:
            best = key
            best_err = err
    return best


def _expression_from_kept(
    pairs: list[tuple[str, str]], kept: list[int], refit: np.ndarray
) -> tuple[str, list[dict]]:
    """Format the OLS refit as DSL text that passes ``validate_candidate``.

    Args:
        pairs: ``(feature, tensor)`` per library column.
        kept: Kept column indices.
        refit: OLS coefficients on the original scale.

    Returns:
        ``(expression, terms)`` with 4-significant-digit coefficients.
    """
    from flowforge.dsl.parser import validate_candidate

    if not kept:
        return "0 * T1", []
    ranked = sorted(zip(kept, refit), key=lambda item: -abs(float(item[1])))
    rounded: list[tuple[int, float]] = []
    for col, coef in ranked:
        value = _round_sig(float(coef))
        if value != 0.0:
            rounded.append((int(col), value))
    terms: list[dict] = []
    expression = "0 * T1"
    remaining = list(rounded)
    while remaining:
        candidate_terms: list[dict] = []
        for col, coef in remaining:
            feature, tensor = pairs[col]
            candidate_terms.append({"feature": feature, "tensor": tensor, "coef": coef})
        text = " + ".join(
            _format_term(item["coef"], item["feature"], item["tensor"]) for item in candidate_terms
        )
        try:
            validate_candidate(text)
        except ValueError:
            remaining = remaining[:-1]
            continue
        terms = candidate_terms
        expression = text
        break
    if not remaining:
        expression = "0 * T1"
        terms = []
    return expression, terms


def fit_sparse_baseline(
    invariants: dict[str, np.ndarray],
    basis: dict[str, np.ndarray],
    target: np.ndarray,
    max_terms: int = 4,
    alpha: float | None = None,
    l1_ratio: float = 0.9,
    seed: int = 42,
) -> dict:
    """Fit the classical sparse-regression baseline.

    Args:
        invariants: Mapping ``I1..I5`` to ``(N,)`` arrays.
        basis: Mapping with at least ``T1..T3`` to ``(N, 3, 3)`` arrays.
        target: ``(N, 3, 3)`` response array.
        max_terms: Keep at most this many ``(feature, tensor)`` columns.
        alpha: ElasticNet penalty strength, or ``None`` to choose by
            deterministic 3-fold CV over ``[1e-6, 1e-5, 1e-4, 1e-3, 1e-2]``.
        l1_ratio: ElasticNet mixing parameter.
        seed: Random seed for ElasticNet.

    Returns:
        ``{"expression", "terms", "train", "alpha", "cv", "l1_ratio",
        "max_terms", "seed", "features", "dropped_features",
        "collinearity_threshold"}`` where ``train`` is
        :func:`flowforge.data.frozen_fields.score_expression` on the emitted
        expression, ``alpha`` is the used penalty and ``cv`` maps each grid
        alpha to its mean held-out MSE (``None`` when ``alpha`` is explicit).
        ``features``/``dropped_features`` record the frozen collinearity
        split so the library is reproducible from the result alone.
    """
    from flowforge.data.frozen_fields import score_expression

    target_arr = np.asarray(target, dtype=float)
    kept_features, dropped_features = collinearity_dropped_features(invariants)
    design, pairs, n_points = _build_design(invariants, basis, kept_features)
    response = np.asarray(target_arr.reshape(-1), dtype=float)
    if alpha is None:
        grid = tuple(float(item) for item in _ALPHA_GRID)
        cv: dict[float, float] | None = _cv_errors_for_grid(
            design, response, n_points, grid, l1_ratio, seed, max_terms
        )
        chosen = _best_alpha(cv, grid)
    else:
        cv = None
        chosen = float(alpha)
    kept, refit = _fit_pruned_refit(design, response, chosen, l1_ratio, seed, max_terms)
    expression, terms = _expression_from_kept(pairs, kept, refit)
    train = score_expression(expression, invariants, basis, target_arr)
    return {
        "expression": expression,
        "terms": terms,
        "train": train,
        "alpha": chosen,
        "cv": cv,
        "l1_ratio": l1_ratio,
        "max_terms": max_terms,
        "seed": seed,
        "features": kept_features,
        "dropped_features": dropped_features,
        "collinearity_threshold": _COLLINEARITY_THRESHOLD,
    }


def evaluate_sparse_baseline(
    case_ids_train: list[str] | tuple[str, ...] | None = None,
    case_ids_validation: list[str] | tuple[str, ...] | None = None,
    seed: int = 42,
    max_points_per_case: int = 4000,
) -> dict:
    """Fit the sparse baseline on train cases and score it on validation.

    Args:
        case_ids_train: Train case ids (default: ``train_case_ids()``).
        case_ids_validation: Validation case ids (default:
            ``validation_case_ids()``).
        seed: Seed for the deterministic train subsample.
        max_points_per_case: Deterministic subset size per case.

    Returns:
        The :func:`fit_sparse_baseline` result plus ``"validation"``
        (:func:`score_on_cases` on validation ids),
        ``"worst_validation_ratio"``, ``"mode": "frozen"`` and
        ``"synthetic": False``.
    """
    from flowforge.data.frozen_fields import (
        load_frozen_fields,
        score_on_cases,
        train_case_ids,
        validation_case_ids,
        worst_ratio,
    )

    train_ids = list(case_ids_train) if case_ids_train is not None else train_case_ids()
    valid_ids = list(case_ids_validation) if case_ids_validation is not None else validation_case_ids()
    invariants, basis, target = load_frozen_fields(
        train_ids,
        max_points_per_case=max_points_per_case,
        seed=seed,
    )
    result = fit_sparse_baseline(invariants, basis, target, seed=seed)
    expression = result["expression"]
    validation = score_on_cases(
        expression,
        valid_ids,
        max_points_per_case=max_points_per_case,
        seed=seed,
    )
    result["validation"] = validation
    result["worst_validation_ratio"] = worst_ratio(validation)
    result["mode"] = "frozen"
    result["synthetic"] = False
    return result
