"""S0 probe: print versions/shapes. Run: uv run python scratch/probe_env.py"""

import sys

print(sys.version)
for name in ("numpy", "scipy", "sympy", "sklearn", "pydantic", "zarr"):
    try:
        mod = __import__(name)
        print(name, getattr(mod, "__version__", "?"))
    except ImportError as exc:
        print(name, "MISSING", exc)
