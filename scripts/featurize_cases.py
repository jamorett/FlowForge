"""Featurize every non-locked case in configs/cases.yaml plus the attack hills (exploratory)."""
import time
import numpy as np
from flowforge.data.features import featurize_case, load_features, STANDARD
from flowforge.data.frozen_fields import train_case_ids, validation_case_ids, redteam_case_ids, load_frozen_fields

# featurize every non-locked case of the default registry (data v3); hills are featurized by run_hills29.py
cases = list(train_case_ids()) + list(validation_case_ids()) + list(redteam_case_ids())
for c in cases:
    t = time.time()
    p = featurize_case(c)
    print(c, p, f"{time.time() - t:.0f}s", flush=True)
# alignment of the subset: same rows as load_frozen_fields
inv, basis, y = load_frozen_fields(cases[:3], max_points_per_case=3000, seed=0)
f = load_features(cases[:3], max_points_per_case=3000, seed=0)
print("subset sizes", len(y), len(f["q_ti"]))
for n in STANDARD:
    v = f[n]
    print(f"{n:9s} finite {np.isfinite(v).mean():.3f}  min {np.nanmin(v):+.3f}  med {np.nanmedian(v):+.3f}  max {np.nanmax(v):+.3f}")
