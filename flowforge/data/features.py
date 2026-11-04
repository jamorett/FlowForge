"""Extra scalar flow features for loop v3 (exploratory branch).

Each feature is dimensionless and bounded, computed from the baseline k-omega SST
fields of the raw McConkey CSV, row-aligned with the processed store of the same
case (``ingest_csv.extract_case_arrays`` keeps the CSV row order). Stored apart from
the processed stores, in ``data/features/<case_id>.npz``, so existing loaders and
stores are untouched. Locked cases are never featurized.

Standard set (after Ling & Templeton 2015 and Wang, Wu & Xiao 2017):
  q_qcrit   (|W|^2 - |S|^2) / (|W|^2 + |S|^2)          rotation vs strain
  q_ti      k / (0.5 |U|^2 + k)                         turbulence intensity
  q_wall    x / (1 + x), x = sqrt(k) / (0.09 omega d)   near-wall vs free shear (SST F1 argument)
  q_pgrad   U.grad p / (|grad p| |U| + |U.grad p|)       streamwise pressure gradient
  q_tscale  (k/eps)|S| / (1 + (k/eps)|S|)               turbulent vs mean time scale
  q_pnorm   |grad p| / (|grad p| + |DU/Dt|)              pressure gradient vs inertia
  q_curv    streamline curvature (Wang et al. q7)
  q_conv    U.grad k / (|U.grad k| + |P_k|)              convection vs production of k
  q_aniso   |tau - 2/3 k I| / (k + |tau - 2/3 k I|)       baseline stress anisotropy
  q_lim     nu_t omega / k                               SST stress-limiter activity
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

FEATURES_DIR = Path("data/features")
STANDARD = ("q_qcrit", "q_ti", "q_wall", "q_pgrad", "q_tscale", "q_pnorm",
            "q_curv", "q_conv", "q_aniso", "q_lim")
# Human-readable definitions, shown to the loop-v3 physicist when the standard set seeds a session.
STANDARD_FORMULAS = {
    "q_qcrit": "(|W|^2 - |S|^2) / (|W|^2 + |S|^2)", "q_ti": "k / (0.5 |U|^2 + k)",
    "q_wall": "x / (1 + x), x = sqrt(k) / (0.09 omega d)", "q_pgrad": "U.grad p / (|grad p| |U| + |U.grad p|)",
    "q_tscale": "(k/eps)|S| / (1 + (k/eps)|S|)", "q_pnorm": "|grad p| / (|grad p| + |DU/Dt|)",
    "q_curv": "streamline curvature |U U : grad U| / (...)", "q_conv": "U.grad k / (|U.grad k| + |P_k|)",
    "q_aniso": "|tau - 2/3 k I| / (k + |tau - 2/3 k I|)", "q_lim": "nu_t omega / k (SST limiter)",
}


def _col(df, name, n=None):
    return df[[f"komegasst_{name}_{i}" for i in range(1, (n or 3) + 1)]].to_numpy(float)


def _ratio(a, b):
    return a / (np.abs(a) + np.abs(b) + 1e-30)


def standard_features(df_k) -> dict[str, np.ndarray]:
    """Standard feature set from one case's raw k-omega SST rows (row order kept)."""
    n = len(df_k)
    U = _col(df_k, "U")
    gradU = df_k[[f"komegasst_gradU_{i}{j}" for i in (1, 2, 3) for j in (1, 2, 3)]].to_numpy(float).reshape(n, 3, 3)
    gradp, gradk, dudt = _col(df_k, "gradp"), _col(df_k, "gradk"), _col(df_k, "DUDt")
    k = np.maximum(df_k["komegasst_k"].to_numpy(float), 1e-12)
    omega = np.maximum(df_k["komegasst_omega"].to_numpy(float), 1e-12)
    eps = np.maximum(df_k["komegasst_epsilon"].to_numpy(float), 1e-12)
    nut = df_k["komegasst_nut"].to_numpy(float)
    tau = df_k[[f"komegasst_turbR_{i}{j}" for i in (1, 2, 3) for j in (1, 2, 3)]].to_numpy(float).reshape(n, 3, 3)
    dist = np.maximum(np.abs(df_k["komegasst_wallDistance"].to_numpy(float)), 1e-12)

    S = 0.5 * (gradU + np.swapaxes(gradU, 1, 2))
    W = 0.5 * (gradU - np.swapaxes(gradU, 1, 2))
    s2, w2 = np.einsum("nij,nij->n", S, S), np.einsum("nij,nij->n", W, W)
    snorm = np.sqrt(s2)
    umag = np.linalg.norm(U, axis=1)
    u_gp = np.einsum("ni,ni->n", U, gradp)
    u_gk = np.einsum("ni,ni->n", U, gradk)
    prod = -np.einsum("nij,nij->n", tau, S)  # P_k = -tau_ij S_ij with tau = <u_i u_j>
    # Wang et al. q7: |U_i U_j dU_i/dx_j| / (sqrt(U_l U_l U_i dU_i/dx_j U_k dU_k/dx_j) + |...|)
    a = np.einsum("ni,nj,nij->n", U, U, gradU)
    g = np.einsum("ni,nij->nj", U, gradU)
    curv = np.abs(a) / (np.sqrt(umag ** 2 * np.einsum("nj,nj->n", g, g)) + np.abs(a) + 1e-30)
    tscale = (k / eps) * snorm
    wall = np.sqrt(k) / (0.09 * omega * dist)
    tau_dev = np.linalg.norm((tau - (2.0 / 3.0) * k[:, None, None] * np.eye(3)).reshape(n, 9), axis=1)
    raw = {  # dimensional primitives for loop v3's feature language (flowforge.data.feature_dsl)
        "raw_Umag": umag, "raw_k": k, "raw_omega": omega, "raw_eps": eps, "raw_nut": nut,
        "raw_d": dist, "raw_Snorm": snorm, "raw_Wnorm": np.sqrt(w2),
        "raw_gradp_mag": np.linalg.norm(gradp, axis=1), "raw_gradk_mag": np.linalg.norm(gradk, axis=1),
        "raw_DUDt_mag": np.linalg.norm(dudt, axis=1), "raw_UgradP": u_gp, "raw_UgradK": u_gk,
        "raw_Pk": prod, "raw_tau_dev": tau_dev,
    }
    return {
        **raw,
        "q_qcrit": (w2 - s2) / (w2 + s2 + 1e-30),
        "q_ti": k / (0.5 * umag ** 2 + k),
        "q_wall": wall / (1.0 + wall),
        "q_pgrad": u_gp / (np.linalg.norm(gradp, axis=1) * umag + np.abs(u_gp) + 1e-30),
        "q_tscale": tscale / (1.0 + tscale),
        "q_pnorm": _ratio(np.linalg.norm(gradp, axis=1), np.linalg.norm(dudt, axis=1)),
        "q_curv": curv,
        "q_conv": _ratio(u_gk, prod),
        "q_aniso": tau_dev / (k + tau_dev),
        "q_lim": np.clip(nut * omega / k, 0.0, 2.0),
    }


def featurize_case(case_id: str, raw_dir: Path = Path("data/raw"), out_dir: Path = FEATURES_DIR) -> Path:
    """Write ``<out_dir>/<case_id>.npz`` for one non-locked case; checks row alignment."""
    from flowforge.data.ingest_csv import CASE_MAPPING, load_raw_case_tables
    from flowforge.data.split_guard import guard_swarm_path
    from flowforge.data.zarr_store import read_case

    raw_case, store, split = CASE_MAPPING[case_id]
    assert split != "locked" and "locked" not in Path(store).parts, f"{case_id} is locked"
    guard_swarm_path(Path(store), role="swarm")
    df_k, _ = load_raw_case_tables(raw_dir, raw_case)
    feats = standard_features(df_k)
    flat = read_case(Path(store))
    assert np.allclose(flat["wall_distance"], df_k["komegasst_wallDistance"].to_numpy(float)), \
        f"{case_id}: raw rows are not aligned with the processed store"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{case_id}.npz"
    np.savez_compressed(path, **feats)
    return path


def load_features(case_ids, names=STANDARD, max_points_per_case: int | None = None, seed: int = 0,
                  features_dir: Path = FEATURES_DIR) -> dict[str, np.ndarray]:
    """Features for ``case_ids`` with the SAME row subset as ``load_frozen_fields``."""
    rng = np.random.default_rng(seed)
    parts: dict[str, list[np.ndarray]] = {n: [] for n in names}
    for cid in case_ids:
        data = np.load(features_dir / f"{cid}.npz")
        n_points = len(data[names[0]])
        if max_points_per_case is not None and n_points > max_points_per_case:
            idx = np.sort(rng.choice(n_points, size=max_points_per_case, replace=False))
        else:
            idx = slice(None)
        for name in names:
            parts[name].append(np.asarray(data[name])[idx])
    return {n: np.concatenate(v) for n, v in parts.items()}
