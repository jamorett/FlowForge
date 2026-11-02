"""Error maps are spatial; regions reach the Analyst in physical units; SAM is opt-in and counts as spend."""
import json
from pathlib import Path

import numpy as np

from flowforge.render.error_map import box_to_physical, rasterize, render_png


def _blob_field():
    xs, ys = np.meshgrid(np.linspace(0, 9, 90), np.linspace(0, 3, 30))
    coords = np.stack([xs.ravel(), ys.ravel()], axis=1)
    err = np.full(len(coords), 0.1)
    hot = (np.abs(coords[:, 0] - 2.0) < 0.5) & (np.abs(coords[:, 1] - 1.0) < 0.3)
    err[hot] = 1.0
    return coords, err


def test_rasterize_keeps_space_and_boxes_map_back():
    coords, err = _blob_field()
    img, ext = rasterize(coords, err, width=180)
    r, c = np.unravel_index(np.argmax(img), img.shape)
    phys = box_to_physical([c, r, c, r], ext)
    assert 1.4 < np.mean(phys["x_range"]) < 2.6 and 0.6 < np.mean(phys["y_range"]) < 1.4  # where the blob is
    assert img.shape[1] == 180 and ext["height"] >= 40


def test_local_segment_finds_separate_blobs(tmp_path):
    from flowforge.render.sam_client import local_segment

    coords, err = _blob_field()
    far = (np.abs(coords[:, 0] - 7.0) < 0.5) & (np.abs(coords[:, 1] - 2.0) < 0.3)
    err[far] = 0.9
    img, _ = rasterize(coords, err, width=180)
    regions = local_segment(str(render_png(img, tmp_path / "m.png")))
    assert len(regions) >= 2 and all(r["source"] == "local-fallback" for r in regions)
    assert regions[0]["box"] != regions[1]["box"]  # two places, not one box around everything


def test_analyst_regions_pass_use_api_and_add_physical_ranges(tmp_path, monkeypatch):
    import flowforge.orchestrator.round as rnd
    from flowforge.agents.tools import registry

    coords, err = _blob_field()

    def fake_render(expr, case_id, out_png):
        img, ext = rasterize(coords, err, width=180)
        out = render_png(img, Path(out_png))
        out.with_suffix(".extent.json").write_text(json.dumps(ext), encoding="utf-8")
        return str(out)

    seen = {}

    def fake_segment(image, use_api=True):
        seen["use_api"] = use_api
        return {"source": "sam-3.1" if use_api else "local-fallback", "regions": [{"region": "r", "box": [30, 5, 50, 15]}]}

    monkeypatch.setitem(registry.TOOLS, "render_error_map", fake_render)
    monkeypatch.setattr("flowforge.render.sam_client.segment_error_regions", fake_segment)
    out = rnd._analyst_regions(["I1*T1"], tmp_path, 1, use_api=True)
    assert seen["use_api"] is True and out[0]["source"] == "sam-3.1"
    assert "x_range" in out[0]["regions"][0] and "y_range" in out[0]["regions"][0]
    brief = rnd._regions_for_analyst(out)
    assert brief[0]["segmentation_source"] == "sam-3.1" and "box" not in brief[0]["regions"][0]


def test_sam_counts_as_spend(tmp_path, monkeypatch):
    from flowforge.api import run_control as rc

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rc, "_session_cap", lambda: 50.0)
    res = rc.RunManager().start_session("s", 1, 1, True, mock=True, budget_usd=1.0, sam=True)
    assert "confirm_live" in res["reason"]
