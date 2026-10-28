"""Ingest raw CSV dataset (McConkey et al.) into processed Zarr stores.

Extracts canonical cases from data/raw/komegasst.csv and data/raw/REF.csv:
  - periodic_hill_re5600 (case_1p0) -> data/processed/periodic_hill_re5600
  - periodic_hill_re10595 (case_1p5) -> data/processed/periodic_hill_re10595
  - curved_step (cbfs13700) -> data/processed/curved_step
  - converging_diverging_channel (convdiv12600) -> data/processed/converging_diverging_channel
  - square_duct (squareDuctAve_Re_2205) -> data/locked/square_duct

Computes invariants, tensor basis, and SpaRTA frozen-RANS targets.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from flowforge.data.split_guard import guard_swarm_path
from flowforge.data.zarr_store import write_case
from flowforge.physics.frozen_rans import anisotropy_target, production_target
from flowforge.physics.tensors import invariants, is_realizable, normalized_tensors, tensor_basis

CASE_MAPPING = {
    "periodic_hill_re5600": ("case_1p0", "data/processed/periodic_hill_re5600", "train"),
    "periodic_hill_re10595": ("case_1p5", "data/processed/periodic_hill_re10595", "train"),
    "curved_step": ("cbfs13700", "data/processed/curved_step", "validation"),
    "converging_diverging_channel": ("convdiv12600", "data/processed/converging_diverging_channel", "validation"),
    "square_duct": ("squareDuctAve_Re_2205", "data/locked/square_duct", "locked"),
}


def load_raw_case_tables(raw_dir: Path, raw_case_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load matching rows for raw_case_id from komegasst.csv and REF.csv."""
    k_path = raw_dir / "komegasst.csv"
    r_path = raw_dir / "REF.csv"
    if not k_path.exists() or not r_path.exists():
        raise FileNotFoundError(f"Raw CSV files missing in {raw_dir}")

    chunks_k = []
    for chunk in pd.read_csv(k_path, chunksize=100_000):
        matched = chunk[chunk["Case"] == raw_case_id]
        if not matched.empty:
            chunks_k.append(matched)
    if not chunks_k:
        raise ValueError(f"Case {raw_case_id} not found in {k_path}")
    df_k = pd.concat(chunks_k, ignore_index=True)

    chunks_r = []
    for chunk in pd.read_csv(r_path, chunksize=100_000):
        matched = chunk[chunk["Case"] == raw_case_id]
        if not matched.empty:
            chunks_r.append(matched)
    if not chunks_r:
        raise ValueError(f"Case {raw_case_id} not found in {r_path}")
    df_r = pd.concat(chunks_r, ignore_index=True)

    assert len(df_k) == len(df_r), (
        f"Row count mismatch for {raw_case_id}: {len(df_k)} vs {len(df_r)}"
    )
    return df_k, df_r


def extract_case_arrays(df_k: pd.DataFrame, df_r: pd.DataFrame) -> dict[str, np.ndarray]:
    """Convert raw dataframe rows into canonical FlowForge array hierarchy."""
    n = len(df_k)

    coords = df_k[["komegasst_C_1", "komegasst_C_2", "komegasst_C_3"]].to_numpy(dtype=float)
    u_base = df_k[["komegasst_U_1", "komegasst_U_2", "komegasst_U_3"]].to_numpy(dtype=float)
    p = df_k["komegasst_p"].to_numpy(dtype=float)
    k = np.maximum(df_k["komegasst_k"].to_numpy(dtype=float), 1e-12)
    omega = np.maximum(df_k["komegasst_omega"].to_numpy(dtype=float), 1e-6)
    wall_dist = df_k["komegasst_wallDistance"].to_numpy(dtype=float)
    cell_vol = np.ones(n, dtype=float)

    # Velocity gradient tensor (N, 3, 3)
    grad_u_cols = [f"komegasst_gradU_{i}{j}" for i in (1, 2, 3) for j in (1, 2, 3)]
    grad_u = df_k[grad_u_cols].to_numpy(dtype=float).reshape(n, 3, 3)

    # Invariants and Pope basis
    s, w = normalized_tensors(grad_u, omega)
    inv = invariants(s, w)
    basis = tensor_basis(s, w)

    # Baseline RANS anisotropy b_sst from turbR
    turb_r_cols = [f"komegasst_turbR_{i}{j}" for i in (1, 2, 3) for j in (1, 2, 3)]
    turb_r = df_k[turb_r_cols].to_numpy(dtype=float).reshape(n, 3, 3)
    b_sst = turb_r / (2.0 * k[:, None, None]) - (1.0 / 3.0) * np.eye(3)[None, :, :]
    b_sst = 0.5 * (b_sst + np.swapaxes(b_sst, -1, -2))
    tr_sst = np.trace(b_sst, axis1=-2, axis2=-1)[:, None, None]
    b_sst = b_sst - (tr_sst / 3.0) * np.eye(3)[None, :, :]

    # DNS anisotropy b_dns from REF
    b_dns = np.zeros((n, 3, 3), dtype=float)
    b_dns[:, 0, 0] = df_r["REF_b_11"]
    b_dns[:, 0, 1] = b_dns[:, 1, 0] = df_r["REF_b_12"]
    b_dns[:, 0, 2] = b_dns[:, 2, 0] = df_r["REF_b_13"]
    b_dns[:, 1, 1] = df_r["REF_b_22"]
    b_dns[:, 1, 2] = b_dns[:, 2, 1] = df_r["REF_b_23"]
    b_dns[:, 2, 2] = df_r["REF_b_33"]

    # SpaRTA frozen-RANS targets
    a_delta = anisotropy_target(b_dns, b_sst)
    strain = 0.5 * (grad_u + np.swapaxes(grad_u, -1, -2))
    pk_delta = production_target(a_delta, k, strain)

    arrays: dict[str, np.ndarray] = {
        "coordinates": coords,
        "cell_volumes": cell_vol,
        "wall_distance": wall_dist,
        "U": u_base,
        "p": p,
        "k": k,
        "omega": omega,
        "grad_u": grad_u,
    }
    arrays.update({f"invariants/{k}": v for k, v in inv.items()})
    arrays.update({f"tensor_basis/{k}": v for k, v in basis.items()})
    arrays["targets/a_delta"] = a_delta
    arrays["targets/Pk_delta"] = pk_delta
    return arrays


def ingest_all_canonical_cases(raw_dir: Path = Path("data/raw")) -> dict[str, Path]:
    out_paths: dict[str, Path] = {}
    for case_id, (raw_case, target_path_str, split) in CASE_MAPPING.items():
        print(f"Ingesting {case_id} (source: {raw_case})...")
        df_k, df_r = load_raw_case_tables(raw_dir, raw_case)
        arrays = extract_case_arrays(df_k, df_r)
        target_path = Path(target_path_str)
        role = "evaluator" if split == "locked" else "swarm"
        guard_swarm_path(target_path, role="evaluator")  # ingestion runs as evaluator
        store = write_case(target_path, arrays)
        out_paths[case_id] = store
        print(f"  -> Successfully stored {len(df_k)} points in {store}")
    return out_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest raw CSV cases into Zarr")
    parser.add_argument("--raw-dir", default="data/raw", type=str)
    args = parser.parse_args()
    ingest_all_canonical_cases(Path(args.raw_dir))


if __name__ == "__main__":
    main()
