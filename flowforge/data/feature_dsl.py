"""Feature language for loop v3: the LLM writes scalar flow features, the code checks them.

A feature is a formula over the dimensional primitives below (baseline k-omega SST fields,
per point). Checks, all deterministic:
  * only whitelisted symbols and functions (sqrt, abs, tanh, exp, log, Min, Max);
  * dimensionless: the value must not change when velocities scale by 2 and lengths by 3
    (each primitive scales by V**a * L**b), so no unit sneaks in;
  * finite on at least 99 % of the training points.
The accepted raw value x is mapped to (-1, 1) by x / (|x| + median|x| on train), so every
feature is bounded and comparable, like the standard set.
"""
from __future__ import annotations

import numpy as np
import sympy as sp

# name -> (velocity exponent, length exponent); pressure is kinematic (p / rho)
PRIMITIVES: dict[str, tuple[int, int]] = {
    "Umag": (1, 0), "k": (2, 0), "omega": (1, -1), "eps": (3, -1), "nut": (1, 1), "d": (0, 1),
    "Snorm": (1, -1), "Wnorm": (1, -1), "gradp_mag": (2, -1), "gradk_mag": (2, -1),
    "DUDt_mag": (2, -1), "UgradP": (3, -1), "UgradK": (3, -1), "Pk": (3, -1), "tau_dev": (2, 0),
}
DESCRIPTIONS = {
    "Umag": "mean velocity magnitude", "k": "turbulent kinetic energy", "omega": "specific dissipation",
    "eps": "dissipation", "nut": "eddy viscosity", "d": "wall distance",
    "Snorm": "|S|, mean strain-rate magnitude", "Wnorm": "|W|, mean rotation-rate magnitude",
    "gradp_mag": "|grad p| (kinematic)", "gradk_mag": "|grad k|", "DUDt_mag": "|DU/Dt|, mean acceleration",
    "UgradP": "U . grad p (signed; > 0 adverse pressure gradient)", "UgradK": "U . grad k (signed)",
    "Pk": "production of k (signed)", "tau_dev": "|tau - 2/3 k I|, baseline anisotropic stress",
}
_FUNCS = {"sqrt": sp.sqrt, "abs": sp.Abs, "tanh": sp.tanh, "exp": sp.exp, "log": sp.log,
          "Min": sp.Min, "Max": sp.Max}
_SCALE_V, _SCALE_L = 2.0, 3.0


class FeatureError(ValueError):
    """A proposed feature failed a check; the message goes back to the LLM."""


def compile_feature(formula: str):
    """Parse ``formula`` and return a numpy function of a primitives dict."""
    syms = {n: sp.Symbol(n, positive=n not in ("UgradP", "UgradK", "Pk")) for n in PRIMITIVES}
    try:
        expr = sp.sympify(formula, locals={**syms, **_FUNCS})
    except (sp.SympifyError, SyntaxError, TypeError) as exc:
        raise FeatureError(f"cannot parse {formula!r}: {exc}") from exc
    unknown = {str(s) for s in expr.free_symbols} - set(PRIMITIVES)
    if unknown:
        raise FeatureError(f"unknown symbols {sorted(unknown)}; allowed: {sorted(PRIMITIVES)}")
    if not expr.free_symbols:
        raise FeatureError("a feature must depend on the flow")
    used = sorted(str(s) for s in expr.free_symbols)
    fn = sp.lambdify([syms[n] for n in used], expr, modules="numpy")

    def evaluate(P: dict[str, np.ndarray]) -> np.ndarray:
        with np.errstate(all="ignore"):
            return np.asarray(fn(*[P[n] for n in used]), dtype=float) * np.ones(len(P[used[0]]))
    return evaluate, used


def check_dimensionless(evaluate, P: dict[str, np.ndarray]) -> None:
    """Same value after scaling velocities by 2 and lengths by 3, or FeatureError."""
    scaled = {n: P[n] * _SCALE_V ** a * _SCALE_L ** b for n, (a, b) in PRIMITIVES.items() if n in P}
    x0, x1 = evaluate(P), evaluate(scaled)
    ok = np.isfinite(x0) & np.isfinite(x1)
    if ok.mean() < 0.5:
        raise FeatureError("not finite on most points")
    rel = np.abs(x1[ok] - x0[ok]) / (np.abs(x0[ok]) + 1e-12)
    if np.median(rel) > 1e-6:
        raise FeatureError("not dimensionless: its value changes with the velocity/length scale; "
                           "combine primitives so units cancel")


class Feature:
    """An accepted, normalized feature."""

    def __init__(self, name: str, formula: str, rationale: str, P_train: dict[str, np.ndarray]):
        if not name.isidentifier() or not name.startswith("f_"):
            raise FeatureError(f"name {name!r} must be an identifier starting with 'f_'")
        self.name, self.formula, self.rationale = name, formula, rationale
        self._eval, self.uses = compile_feature(formula)
        check_dimensionless(self._eval, P_train)
        x = self._eval(P_train)
        finite = np.isfinite(x)
        if finite.mean() < 0.99:
            raise FeatureError(f"non-finite on {100 * (1 - finite.mean()):.1f}% of training points")
        self.scale = float(np.median(np.abs(x[finite]))) or 1.0
        if np.std(x[finite]) < 1e-9 * (self.scale + 1e-30):
            raise FeatureError("constant on the training data")

    def __call__(self, P: dict[str, np.ndarray]) -> np.ndarray:
        x = self._eval(P)
        y = x / (np.abs(x) + self.scale)
        return np.where(np.isfinite(y), y, 0.0)
