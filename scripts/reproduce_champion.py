"""Reproduce champion scores from its content hash (S7). Scaffold."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--champion-hash", required=True)
    args = parser.parse_args()
    print(f"Reproducing champion {args.champion_hash} from cached hashes...")
    raise SystemExit("Needs S1-S3 verification first; hashes only, no re-fit.")


if __name__ == "__main__":
    main()
