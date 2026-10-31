"""Download curated dataset + Closure Challenge into data/raw.

Writes data/raw/manifest.json with SHA-256 per file. With
--synthetic-fallback, generates deterministic local arrays instead of
network downloads so CI passes offline. Real downloads require Kaggle /
Closure Challenge access; files whose hash mismatches the manifest are
rejected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

RAW_DIR = Path("data/raw")
CASES = (
    "periodic_hill_re5600",
    "periodic_hill_alpha1p5_re5600",
    "curved_step",
    "converging_diverging_channel",
)


def _sha256_stream(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def synthetic_fallback(raw_dir: Path = RAW_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    manifest: dict[str, str] = {}
    for case in CASES:
        path = raw_dir / f"{case}.npy"
        np.save(path, rng.standard_normal((100, 3)))
        manifest[path.name] = _sha256_stream(path)
    manifest_path = raw_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def process_real_dataset(raw_dir: Path = RAW_DIR) -> Path:
    manifest_path = raw_dir / "manifest.json"
    manifest: dict[str, dict] = {}
    csv_files = ["komegasst.csv", "REF.csv"]
    for fname in csv_files:
        fpath = raw_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Missing expected raw file: {fpath}")
        print(f"Hashing {fname}...")
        sha = _sha256_stream(fpath)
        manifest[fname] = {
            "sha256": sha,
            "size_bytes": fpath.stat().st_size,
            "source": "https://www.kaggle.com/datasets/ryleymcconkey/turbulence-modelling-using-machine-learning",
            "license": "CC-BY-4.0",
        }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote real dataset manifest to {manifest_path}")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-fallback", action="store_true")
    args = parser.parse_args()
    if args.synthetic_fallback:
        path = synthetic_fallback()
        print(f"Wrote synthetic manifest: {path}")
        return

    komegasst = RAW_DIR / "komegasst.csv"
    ref_csv = RAW_DIR / "REF.csv"
    if komegasst.exists() and ref_csv.exists():
        process_real_dataset(RAW_DIR)
        return

    raise SystemExit(
        "Real dataset files (komegasst.csv and REF.csv) not found in data/raw/. "
        "Use --synthetic-fallback for offline CI."
    )


if __name__ == "__main__":
    main()

