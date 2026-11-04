"""Loop v3 (exploratory): the LLM proposes flow features, a deterministic search writes the formula.

Each round:
  1. physicist (LLM) sees the active features with their measured usefulness, the current
     best formula and its per-flow error ratios on TRAIN and HELD-OUT flows (redteam split;
     never validation), and the rejected features with reasons; proposes 1-3 features and
     may drop useless ones;
  2. each proposal is checked (feature_dsl: whitelist, dimensionless, finite) and normalized;
  3. OMP (flowforge.search.omp) builds the largest formula within ``max_nodes`` from I1, I2
     and the active features, constants fitted on train only;
  4. each active feature's held-out gain is measured by re-running the search without it.
The session's champion is the round with the lowest WORST held-out ratio (selection never
sees validation). Events go to runs/<session>/events.jsonl.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from flowforge.data.feature_dsl import DESCRIPTIONS, Feature, FeatureError, PRIMITIVES
from flowforge.data.features import STANDARD, load_features
from flowforge.search import omp

logger = logging.getLogger(__name__)
MAX_COMPLETION_TOKENS = 50_000


def load_set(cases, n: int, seed: int = 0):
    """(D, P, T, y) for ``cases``: D = I1, I2 and standard features; P = primitives."""
    from flowforge.data.frozen_fields import load_frozen_fields

    inv, basis, y = load_frozen_fields(cases, max_points_per_case=n, seed=seed)
    names = list(STANDARD) + [f"raw_{p}" for p in PRIMITIVES]
    f = load_features(cases, names=tuple(names), max_points_per_case=n, seed=seed)
    D = {"I1": inv["I1"], "I2": inv["I2"], **{q: f[q] for q in STANDARD}}
    P = {**{p: f[f"raw_{p}"] for p in PRIMITIVES}, **{q: f[q] for q in STANDARD}}
    T = np.stack([basis[f"T{k}"] for k in (1, 2, 3)], 1)
    y = np.asarray(y, float)
    m = (np.isfinite(T).reshape(len(T), -1).all(1) & np.isfinite(y).reshape(len(y), -1).all(1)
         & np.all([np.isfinite(v) for v in D.values()], axis=0))
    return {k: v[m] for k, v in D.items()}, {k: v[m] for k, v in P.items()}, T[m], y[m]


class FixedFeature:
    """A standard feature (precomputed, already bounded) used to seed a session."""

    def __init__(self, name: str):
        from flowforge.data.features import STANDARD_FORMULAS

        self.name, self.formula = name, STANDARD_FORMULAS[name]
        self.rationale = "standard feature (Ling & Templeton 2015; Wang et al. 2017)"

    def __call__(self, P):
        return P[self.name]


def with_features(D, P, features: list[Feature]):
    return {**{k: D[k] for k in ("I1", "I2")}, **{f.name: f(P) for f in features}}


class Loop:
    def __init__(self, train_cases, heldout_cases, max_nodes: int = 40, max_features: int = 10,
                 train_points: int = 3000):
        self.train = load_set(train_cases, train_points)
        self.heldout = {c: load_set([c], 4000) for c in heldout_cases}
        self.max_nodes, self.max_features = max_nodes, max_features

    def run_search(self, features: list[Feature]) -> dict:
        D, P, T, y = self.train
        names = ["I1", "I2", *[f.name for f in features]]
        model = omp.search(names, (with_features(D, P, features), T, y), self.max_nodes)
        model["train"] = omp.score(model, {"train": (with_features(D, P, features), T, y)})["train"]
        model["heldout"] = omp.score(model, {c: (with_features(D2, P2, features), T2, y2)
                                             for c, (D2, P2, T2, y2) in self.heldout.items()})
        model["worst_heldout"] = max(model["heldout"].values())
        return model

    def gains(self, features: list[Feature], model: dict) -> dict[str, float]:
        base = np.mean(list(model["heldout"].values()))
        out = {}
        for f in features:
            rest = [g for g in features if g is not f]
            out[f.name] = float(np.mean(list(self.run_search(rest)["heldout"].values())) - base)
        return out

    def score_cases(self, features: list[Feature], model: dict, cases) -> dict[str, float]:
        sets = {c: load_set([c], 4000) for c in cases}
        return omp.score(model, {c: (with_features(D, P, features), T, y) for c, (D, P, T, y) in sets.items()})


def context_for(features, model, gains, rejected, max_features, round_no) -> dict:
    return {
        "round": round_no,
        "primitives": DESCRIPTIONS,
        "active_features": [{"name": f.name, "formula": f.formula, "rationale": f.rationale,
                             "terms_using": model["uses"].count(f.name),
                             "heldout_gain": round(gains.get(f.name, 0.0), 4)} for f in features],
        "best": {"formula": model["formula"], "nodes": model["nodes"],
                 "train_ratio": round(model["train"], 4),
                 "heldout_cases": {c: round(r, 4) for c, r in model["heldout"].items()}},
        "rejected": rejected[-10:],
        "max_features": max_features,
        "free_slots": max_features - len(features),
    }


def run_session(session: str, rounds: int, dispatch, train_cases, heldout_cases,
                max_nodes: int = 40, max_features: int = 10, runs_root: Path = Path("runs"),
                initial_features: list | None = None, train_points: int = 3000) -> dict:
    """One loop-v3 session. ``dispatch(context) -> FeatureProposal | None``."""
    loop = Loop(train_cases, heldout_cases, max_nodes, max_features, train_points)
    events = runs_root / session / "events.jsonl"
    events.parent.mkdir(parents=True, exist_ok=True)

    def log(kind, **data):
        with events.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"type": kind, **data}, default=float) + "\n")

    features: list = list(initial_features or [])
    rejected: list[dict] = []
    model = loop.run_search(features)
    gains: dict[str, float] = {}
    history = []
    log("baseline", formula=model["formula"], nodes=model["nodes"], heldout=model["heldout"])
    for round_no in range(1, rounds + 1):
        proposal = dispatch(context_for(features, model, gains, rejected, max_features, round_no))
        accepted = []
        if proposal is not None:
            drop = set(proposal.drop)
            features = [f for f in features if f.name not in drop]
            taken = {f.name for f in features}
            for spec in proposal.features:
                try:
                    if spec.name in taken:
                        raise FeatureError(f"name {spec.name!r} already active")
                    feat = Feature(spec.name, spec.formula, spec.rationale, loop.train[1])
                except FeatureError as exc:
                    rejected.append({"name": spec.name, "formula": spec.formula, "reason": str(exc)})
                    continue
                features.append(feat)
                taken.add(feat.name)
                accepted.append(feat.name)
        if len(features) > max_features:  # keep the most useful when over the cap
            features = sorted(features, key=lambda f: -gains.get(f.name, 0.0))[:max_features]
        model = loop.run_search(features)
        gains = loop.gains(features, model)
        row = {"round": round_no, "features": [(f.name, f.formula) for f in features],
               "accepted": accepted, "formula": model["formula"], "nodes": model["nodes"],
               "train": model["train"], "heldout": model["heldout"],
               "worst_heldout": model["worst_heldout"], "gains": gains,
               "proposal": proposal.model_dump() if proposal is not None else None}
        history.append((row, list(features), model))
        log("round", **row, rejected=rejected[-3:])
    best_row, best_feats, best_model = min(history, key=lambda h: h[0]["worst_heldout"])
    return {"session": session, "history": [h[0] for h in history], "champion_round": best_row["round"],
            "champion": best_row, "champion_features": best_feats, "champion_model": best_model, "loop": loop}
