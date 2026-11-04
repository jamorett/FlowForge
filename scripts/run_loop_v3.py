"""Run loop v3 sessions (exploratory, frozen) and report curved_step for each champion.

usage: python scripts/run_loop_v3.py --tag v3-pilot --seeds 42,43,44,45,46 [--rounds 5] [--dry]
--dry uses a fixed fake physicist (no API). Output: runs/arms/loop-v3-<tag>.json.
Arms reported per seed at the same node cap: the LLM's features (champion round) and the
LLM's features plus the standard set; the controls "invariants" (I1, I2) and "standard"
(I1, I2 + standard features) are computed once (deterministic, no LLM).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from flowforge.data.features import STANDARD  # noqa: E402
from flowforge.data.frozen_fields import redteam_case_ids, train_case_ids, validation_case_ids  # noqa: E402
from flowforge.orchestrator import loop_v3  # noqa: E402
from flowforge.search import omp  # noqa: E402

FAKE = [
    [("f_wall", "sqrt(k) / (omega * d)", "near-wall vs free shear"),
     ("f_noneq", "Pk / eps", "non-equilibrium")],
    [("f_apg", "UgradP * d / (k * Umag)", "adverse pressure gradient")],
]


def fake_dispatch(context):
    from flowforge.agents.schemas import FeatureProposal

    batch = FAKE[(context["round"] - 1) % len(FAKE)]
    return FeatureProposal.model_validate({"risk_audit": "dry run", "drop": [], "features": [
        {"name": n, "formula": f, "rationale": r} for n, f, r in batch]})


def live_dispatch(runtime):
    from flowforge.agents import dispatcher

    def dispatch(context):
        try:
            return dispatcher.dispatch_role("physicist", runtime, context,
                                            max_tokens=loop_v3.MAX_COMPLETION_TOKENS)
        except dispatcher.RoleDispatchError as exc:
            print(f"  physicist failed: {exc}", flush=True)
            return None
    return dispatch


def control(names, loop, val_sets):
    D, P, T, y = loop.train
    model = omp.search(names, (D, T, y), loop.max_nodes)
    return {"formula": model["formula"], "nodes": model["nodes"],
            "curved_step": omp.score(model, {c: (Dv, Tv, yv) for c, (Dv, Pv, Tv, yv) in val_sets.items()})}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--seeds", default="42,43,44,45,46")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--max-nodes", type=int, default=40, dest="max_nodes")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--max-features", type=int, default=10, dest="max_features")
    ap.add_argument("--train-points", type=int, default=3000, dest="train_points")
    ap.add_argument("--seed-standard", action="store_true", dest="seed_standard",
                    help="start every session with the 10 standard features active")
    args = ap.parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",")]
    train, heldout, val = train_case_ids(), list(redteam_case_ids()), list(validation_case_ids())

    from flowforge.agents.runtime.client import ModelRuntime

    out = {"label": "exploratory", "mode": "frozen", "tag": args.tag, "rounds": args.rounds,
           "max_nodes": args.max_nodes, "dry": args.dry, "max_features": args.max_features,
           "seed_standard": args.seed_standard, "seeds": {}, "spent_usd": 0.0}
    loop = None
    for seed in seeds:
        runtime = ModelRuntime(logger=None)
        dispatch = fake_dispatch if args.dry else live_dispatch(runtime)
        initial = [loop_v3.FixedFeature(q) for q in STANDARD] if args.seed_standard else None
        res = loop_v3.run_session(f"{args.tag}-s{seed}", args.rounds, dispatch, train, heldout,
                                  max_nodes=args.max_nodes, max_features=args.max_features,
                                  initial_features=initial, train_points=args.train_points)
        loop = res["loop"]
        feats, model = res["champion_features"], res["champion_model"]
        val_llm = loop.score_cases(feats, model, val)
        D, P, T, y = loop.train
        names = ["I1", "I2", *STANDARD, *[f.name for f in feats if f.name not in STANDARD]]
        combo = omp.search(names, ({**D, **{f.name: f(P) for f in feats}}, T, y), loop.max_nodes)
        sets = {c: loop_v3.load_set([c], 4000) for c in val}
        val_combo = omp.score(combo, {c: ({**Dv, **{f.name: f(Pv) for f in feats}}, Tv, yv)
                                      for c, (Dv, Pv, Tv, yv) in sets.items()})
        out["seeds"][seed] = {"champion_round": res["champion_round"], "features": [(f.name, f.formula, f.rationale) for f in feats],
                              "formula": model["formula"], "nodes": model["nodes"],
                              "worst_heldout": model["worst_heldout"], "curved_step": val_llm,
                              "llm_plus_standard": {"formula": combo["formula"], "nodes": combo["nodes"], "curved_step": val_combo},
                              "history": res["history"], "spent_usd": runtime.spent}
        out["spent_usd"] += runtime.spent
        print(f"seed {seed}: round {res['champion_round']}, {len(feats)} features, nodes {model['nodes']}, "
              f"curved_step {val_llm['curved_step']:.3f}, +standard {val_combo['curved_step']:.3f}, "
              f"spent ${runtime.spent:.2f}", flush=True)
    sets = {c: loop_v3.load_set([c], 4000) for c in val}
    out["controls"] = {"invariants": control(["I1", "I2"], loop, sets),
                       "standard": control(["I1", "I2", *STANDARD], loop, sets)}
    for k, v in out["controls"].items():
        print(f"control {k}: nodes {v['nodes']}, curved_step {v['curved_step']['curved_step']:.3f}")
    Path("runs/arms").mkdir(parents=True, exist_ok=True)
    Path(f"runs/arms/loop-v3-{args.tag}-{args.seeds.replace(',', '_')}.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"total spent ${out['spent_usd']:.2f}")


if __name__ == "__main__":
    main()
