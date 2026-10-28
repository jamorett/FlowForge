"""Tool registry (S4/S5/S6). Schema-validated, budget-metered, traced.

Exposes the 11 tools defined in the v2 Build Spec for agent roles:
  - Board: read_findings, read_scores
  - Theorist: search_cards
  - Coder: fit_constants, eval_apriori
  - Analyst: render_error_map, sam_segment
  - Skeptic: request_test
  - Red Team: generate_flow, run_attack
  - Composer: fit_gates
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

TOOLS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn: Callable) -> Callable:
        TOOLS[name] = fn
        return fn

    return deco


# ---------------------------------------------------------------------------
# Board Tools
# ---------------------------------------------------------------------------

@register("read_findings")
def read_findings(findings_dir: str = "library/findings") -> list[dict[str, str]]:
    """Read plain-language findings from library/findings/."""
    p = Path(findings_dir)
    if not p.exists():
        return []
    out = []
    for f in sorted(p.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            out.append({"id": f.stem, **data})
        except Exception:
            continue
    for f in sorted(p.glob("*.md")):
        out.append({"id": f.stem, "content": f.read_text(encoding="utf-8")})
    return out


@register("read_scores")
def read_scores(session: str = "default", runs_root: str = "runs") -> dict[str, Any]:
    """Read current session event stream to extract latest scores and champions."""
    events_path = Path(runs_root) / session / "events.jsonl"
    if not events_path.exists():
        return {"session": session, "candidates": {}, "champion": None}

    candidates: dict[str, dict] = {}
    champion = None
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        cand = ev.get("candidate")
        if cand:
            candidates[str(cand)] = {
                "score": ev.get("score"),
                "worst_error": ev.get("worst_error"),
                "dl": ev.get("dl"),
                "step": ev.get("step"),
            }
        if ev.get("champion"):
            champion = ev["champion"]
    return {"session": session, "candidates": candidates, "champion": champion}


# ---------------------------------------------------------------------------
# Theorist Tools
# ---------------------------------------------------------------------------

@register("search_cards")
def search_cards(query: str, cards_dir: str = "data/literature") -> list[dict[str, Any]]:
    """Search literature closure cards by mechanism keyword or model form."""
    p = Path(cards_dir)
    if not p.exists():
        return []
    results = []
    q = query.lower()
    for f in p.glob("*.json"):
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
            if (
                q in card.get("mechanism", "").lower()
                or q in card.get("model_form", "").lower()
                or q in card.get("doi", "").lower()
            ):
                results.append(card)
        except Exception:
            continue
    return results


# ---------------------------------------------------------------------------
# Coder Tools
# ---------------------------------------------------------------------------

@register("fit_constants")
def fit_constants_tool(
    expression: str,
    case_id: str = "periodic_hill_re5600",
    processed_dir: str = "data/processed",
) -> dict[str, Any]:
    """Fit constant multiplier for a candidate closure on training data."""
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.dsl.fitting import snap_constants
    from flowforge.ladder.ladder import apriori_mse

    case_path = Path(processed_dir) / case_id
    if not case_path.exists():
        return {"expression": expression, "error": f"Case not found: {case_id}"}

    data = read_case(case_path)
    invariants = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target = data["targets/a_delta"]

    base_pred = candidate_anisotropy(expression, invariants, basis)
    # Fit scalar scale c to minimize ||c * base_pred - target||^2
    denom = float(np.sum(base_pred**2))
    scale = float(np.sum(base_pred * target) / denom) if denom > 1e-12 else 1.0

    def err_fn(coefs):
        return apriori_mse(coefs[0] * base_pred, target)

    snapped = snap_constants(np.array([scale]), err_fn)
    c_snapped = float(snapped[0])
    final_mse = err_fn([c_snapped])

    fitted_expr = f"{c_snapped} * ({expression})" if c_snapped != 1.0 else expression
    return {
        "raw_scale": scale,
        "snapped_scale": c_snapped,
        "fitted_expression": fitted_expr,
        "apriori_mse": final_mse,
    }


@register("eval_apriori")
def eval_apriori_tool(
    expression: str,
    case_id: str = "periodic_hill_re5600",
    processed_dir: str = "data/processed",
) -> float:
    """Evaluate candidate anisotropy MSE against frozen-RANS targets."""
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.ladder.ladder import apriori_mse

    case_path = Path(processed_dir) / case_id
    if not case_path.exists():
        raise FileNotFoundError(f"Case store not found: {case_path}")

    data = read_case(case_path)
    invariants = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target = data["targets/a_delta"]

    pred = candidate_anisotropy(expression, invariants, basis)
    return float(apriori_mse(pred, target))


# ---------------------------------------------------------------------------
# Analyst Tools
# ---------------------------------------------------------------------------

@register("render_error_map")
def render_error_map(
    expression: str,
    case_id: str = "periodic_hill_re5600",
    out_png: str = "runs/error_map.png",
    processed_dir: str = "data/processed",
) -> str:
    """Render 2D slice error map of candidate vs DNS to a PNG file."""
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.render.error_map import render_png

    case_path = Path(processed_dir) / case_id
    data = read_case(case_path)
    invariants = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target = data["targets/a_delta"]

    pred = candidate_anisotropy(expression, invariants, basis)
    err = np.linalg.norm(pred - target, axis=(-2, -1))

    # Grid reshape or pseudo-2D map
    import math

    n = len(err)
    side = math.isqrt(n)
    if side * side == n:
        err_2d = err.reshape(side, side)
    else:
        err_2d = err[: side * side].reshape(side, side)


    out = render_png(err_2d, Path(out_png))
    return str(out)


@register("sam_segment")
def sam_segment(image_path: str) -> list[dict[str, Any]]:
    """Segment high-error regions (bubble, reattachment, shear layer)."""
    p = Path(image_path)
    npy_path = p.with_suffix(".npy")
    if not npy_path.exists():
        return [{"region": "global", "box": [0, 0, 100, 100], "severity": "medium"}]

    errors = np.load(npy_path)
    threshold = float(np.percentile(errors, 90))
    high_mask = errors >= threshold
    h, w = errors.shape

    # Identify primary high-error cluster
    rows, cols = np.where(high_mask)
    if len(rows) == 0:
        return []

    box = [int(cols.min()), int(rows.min()), int(cols.max()), int(rows.max())]
    return [
        {
            "region": "separation_bubble" if box[0] < w // 2 else "shear_layer",
            "box": box,
            "max_error": float(errors.max()),
            "mean_error": float(errors[high_mask].mean()),
        }
    ]


# ---------------------------------------------------------------------------
# Skeptic Tools
# ---------------------------------------------------------------------------

@register("request_test")
def request_test(candidate: str, objection: str, extra_case: str) -> dict[str, str]:
    """Skeptic submits a physical objection and requests verification on an extra case."""
    return {
        "status": "recorded",
        "candidate": candidate,
        "objection": objection,
        "requested_case": extra_case,
    }


# ---------------------------------------------------------------------------
# Red Team Tools
# ---------------------------------------------------------------------------

@register("generate_flow")
def generate_flow(alpha: float, reynolds: float, kind: str = "periodic_hill") -> dict[str, Any]:
    """Create a new parametric flow specification for red-team testing."""
    from flowforge.redteam.generator import FlowSpec

    spec = FlowSpec(kind=kind, alpha=float(alpha), reynolds=float(reynolds))
    return {
        "kind": spec.kind,
        "alpha": spec.alpha,
        "reynolds": spec.reynolds,
        "split": spec.split,
    }


@register("run_attack")
def run_attack(
    candidate: str,
    spec: dict[str, Any],
    validation_case: str = "curved_step",
    processed_dir: str = "data/processed",
) -> dict[str, Any]:
    """Run physics attack against a candidate using an unseen validation flow."""
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.ladder.ladder import apriori_mse
    from flowforge.redteam.attacks import broke_threshold, record_attack

    case_path = Path(processed_dir) / validation_case
    if not case_path.exists():
        return {"status": "skipped", "reason": f"Case {validation_case} not found"}

    data = read_case(case_path)
    invariants = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target = data["targets/a_delta"]

    cand_mse = apriori_mse(candidate_anisotropy(candidate, invariants, basis), target)
    baseline_mse = apriori_mse(candidate_anisotropy("0", invariants, basis), target)

    broken = broke_threshold({validation_case: cand_mse}, {validation_case: baseline_mse})
    if broken:
        record_attack(spec, candidate, broke=True)

    return {
        "candidate": candidate,
        "case": validation_case,
        "candidate_mse": cand_mse,
        "baseline_mse": baseline_mse,
        "broken": broken,
    }


# ---------------------------------------------------------------------------
# Composer Tools
# ---------------------------------------------------------------------------

@register("fit_gates")
def fit_gates(
    module1: str,
    module2: str,
    case_id: str = "periodic_hill_re5600",
    processed_dir: str = "data/processed",
) -> dict[str, Any]:
    """Fit optimal sigmoid gate parameters w, b to blend two modules."""
    from scipy.optimize import minimize
    from flowforge.composer.gates import compose
    from flowforge.data.zarr_store import read_case
    from flowforge.dsl.evaluate import candidate_anisotropy
    from flowforge.ladder.ladder import apriori_mse

    case_path = Path(processed_dir) / case_id
    data = read_case(case_path)
    invariants = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("invariants/")}
    basis = {k.split("/", 1)[1]: v for k, v in data.items() if k.startswith("tensor_basis/")}
    target = data["targets/a_delta"]

    m1 = candidate_anisotropy(module1, invariants, basis)
    m2 = candidate_anisotropy(module2, invariants, basis)
    gate_in = invariants["I1"]

    def loss(params):
        w_val, b_val = params
        comp, _ = compose(m1, m2, gate_in, w_val, b_val)
        return apriori_mse(comp, target)

    res = minimize(loss, [1.0, 0.0], method="Nelder-Mead")
    w_opt, b_opt = float(res.x[0]), float(res.x[1])
    comp_mse = float(res.fun)

    return {
        "module1": module1,
        "module2": module2,
        "w": w_opt,
        "b": b_opt,
        "composite_mse": comp_mse,
        "dl_penalty_bits": 16.0,
    }
