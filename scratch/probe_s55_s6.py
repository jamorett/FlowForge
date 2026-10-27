"""S5.5/S6 probe: generator bounds, gate formula, API pacing surface.
Run: python scratch/probe_s55_s6.py
"""
import sys
sys.path.insert(0, ".")
import numpy as np

# 1. generator current behaviour
from flowforge.redteam.generator import generate_attacks
specs = generate_attacks()
print("attacks", len(specs), specs[0])
print("alpha range", min(s.alpha for s in specs), max(s.alpha for s in specs))
try:
    generate_attacks(alphas=(2.0,))
    print("FAIL alpha 2.0 accepted")
except AssertionError as e:
    print("alpha guard OK", e)

# 2. gates formula manual oracle
from flowforge.composer.gates import compose, sigmoid
m1 = np.ones((3, 3, 3)); m2 = np.zeros((3, 3, 3))
out, pen = compose(m1, m2, np.zeros(3), w=1.0, b=0.0)
print("gate@0 expected 0.5 got", float(out[0, 0, 0]), "penalty", pen)
assert abs(float(out[0, 0, 0]) - 0.5) < 1e-12 and pen == 16.0
print("sigmoid", float(sigmoid(np.array([0.0]))[0]))

# 3. API surface
try:
    from fastapi.testclient import TestClient
    from flowforge.api.server import app
    c = TestClient(app)
    for p in ("/health", "/api/session/state", "/api/matrix"):
        r = c.get(p)
        print(p, r.status_code, r.text[:160])
except Exception as e:
    print("TestClient unavailable/failed:", type(e).__name__, e)
print("probe done")
