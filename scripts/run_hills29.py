"""Solve + ingest all 29 parameterized hills (6 Docker solves at a time).

usage: python scripts/run_hills29.py [DNS_DIR]   (unzipped NASA TMR dns-29-periodic-hills.zip)
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flowforge.data import hills29 as h

src = sorted(Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw/hills29/DNS_29_Periodic_Hills").glob("*.dat"))
done = {p.name for p in Path("data/features").glob("hill29_*.npz")}
todo = [p for p in src if f"{h.case_name(p)}.npz" not in done]
print(f"{len(src)} files, {len(todo)} to do", flush=True)
results = {}


def one(p):
    t = time.time()
    c = h.solve(p, Path("scratch/h29"))
    info = h.ingest(c, p)
    info.update(seconds=round(time.time() - t), case_dir=str(c))
    return info


with ThreadPoolExecutor(max_workers=6) as ex:
    futs = {ex.submit(one, p): p for p in todo}
    for f in as_completed(futs):
        p = futs[f]
        try:
            results[p.name] = f.result()
        except Exception as exc:
            results[p.name] = {"error": str(exc)[-1500:]}
        print(p.name, json.dumps(results[p.name])[:300], flush=True)
Path("runs/arms").mkdir(parents=True, exist_ok=True)
Path("runs/arms/hills29-ingest.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print("done", sum("error" not in r for r in results.values()), "ok of", len(results))
