"""Run identity/oracle logic test bodies without pytest (pytest absent).
Imports the real test modules and calls the non-skipped functions.
Exit 0 only if all 4 logic functions pass. Solver tests are NOT called."""
import sys, tempfile, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# pytest is not installed (evidence: versions-env). Inject a minimal stub
# ONLY in this probe process so the test modules can be imported; the
# mark.skip decorator is identity here because solver tests are never called.
import types
_stub = types.ModuleType("pytest")
class _Mark:
    def skip(self, *a, **k):
        return lambda f: f
    def __getattr__(self, name):
        return lambda *a, **k: (lambda f: f)
_stub.mark = _Mark()
sys.modules.setdefault("pytest", _stub)
import tests.integration.test_identity as ti
import tests.integration.test_oracle as to

ok = True
for name, fn, args in [
    ("test_identity_logic", ti.test_identity_logic, ()),
    ("test_zero_correction_is_exact_identity", ti.test_zero_correction_is_exact_identity, None),
    ("test_oracle_logic", to.test_oracle_logic, ()),
    ("test_dns_injection_targets_reduce_error", to.test_dns_injection_targets_reduce_error, ()),
]:
    try:
        if args is None:
            with tempfile.TemporaryDirectory() as d:
                fn(Path(d))
        else:
            fn()
        print(f"PASS {name}")
    except Exception:
        ok = False
        print(f"FAIL {name}")
        traceback.print_exc()
print("solver tests present:", hasattr(ti, "test_identity_solver"), hasattr(to, "test_oracle_solver"))
sys.exit(0 if ok else 1)
