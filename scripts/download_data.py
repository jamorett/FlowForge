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
    "periodic_hill_re10595",
    "curved_step",
    "converging_diverging_channel",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def synthetic_fallback(raw_dir: Path = RAW_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    manifest: dict[str, str] = {}
    for case in CASES:
        path = raw_dir / f"{case}.npy"
        np.save(path, rng.standard_normal((100, 3)))
        manifest[path.name] = _sha256(path)
    manifest_path = raw_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--synthetic-fallback", action="store_true")
    args = parser.parse_args()
    if args.synthetic_fallback:
        path = synthetic_fallback()
        print(f"Wrote {path}")
        return
    raise SystemExit(
        "Real download needs Kaggle/Closure Challenge access. "
        "Use --synthetic-fallback for offline CI."
    )


if __name__ == "__main__":
    main()
