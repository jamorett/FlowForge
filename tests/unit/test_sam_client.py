"""SAM 3.1 client: offline fallback, replay discipline, source honesty (S6).

No test here touches the network: the API path is exercised only via
replay mode (disabled) and injected transport failures.
"""
from pathlib import Path

import numpy as np
import pytest

from flowforge.render.error_map import render_png
from flowforge.render.sam_client import segment_error_regions


def _render(tmp_path: Path) -> str:
    rng = np.random.default_rng(7)
    errors = np.abs(rng.standard_normal((16, 16)))
    errors[3:7, 3:7] += 5.0  # dominant high-error cluster
    out = tmp_path / "err.png"
    render_png(errors, out)
    return str(out)


def test_missing_image_returns_canned_global_box(tmp_path: Path) -> None:
    res = segment_error_regions(str(tmp_path / "nope.png"), use_api=False)
    assert res["source"] == "local-fallback"
    assert res["regions"][0]["box"] == [0, 0, 100, 100]


def test_rendered_map_segments_offline_with_source(tmp_path: Path) -> None:
    res = segment_error_regions(_render(tmp_path), use_api=False)
    assert res["source"] == "local-fallback"
    assert res["model"] is None
    assert len(res["regions"]) > 0
    assert "box" in res["regions"][0]
    assert res["regions"][0]["source"] == "local-fallback"


def test_replay_mode_never_calls_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLOWFORGE_REPLAY", "1")
    monkeypatch.setenv("MODEL_API_KEY", "fake-key-for-test")
    called = []

    import httpx

    def _boom(*args: object, **kwargs: object) -> object:
        called.append(True)
        raise AssertionError("network must not be touched in replay mode")

    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "stream", _boom)
    res = segment_error_regions(_render(tmp_path), use_api=True)
    assert res["source"] == "local-fallback"
    assert called == []


def test_api_failure_falls_back_without_raising(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLOWFORGE_REPLAY", raising=False)
    monkeypatch.setenv("MODEL_API_KEY", "fake-key-for-test")

    import flowforge.render.sam_client as sam_client

    # Hermetic cache: a previous live probe may have cached this digest.
    monkeypatch.setattr(sam_client, "CACHE_DIR", tmp_path / "sam_cache")

    import httpx

    def _fail(*args: object, **kwargs: object) -> object:
        raise httpx.ConnectError("endpoint unconfirmed")

    monkeypatch.setattr(httpx, "post", _fail)
    monkeypatch.setattr(httpx, "stream", _fail)
    res = segment_error_regions(_render(tmp_path), use_api=True)
    assert res["source"] == "local-fallback"
    assert len(res["regions"]) > 0


def test_parse_sam_token_text() -> None:
    from flowforge.render.sam_client import _parse_sam_text

    text = ("<0f>0<|box;x1=353;y1=382;x2=453;y2=427;w=537;h=561|>"
            "<|mask;x=0;y=0;data=46,101,~abc|>,"
            "1<|box;x1=260;y1=382;x2=340;y2=427;w=537;h=561|>"
            "<|mask;x=0;y=0;data=46,81,~def|>")
    regions = _parse_sam_text(text)
    assert len(regions) == 2
    assert regions[0]["box"] == [353, 382, 453, 427]
    assert regions[0]["image_size"] == [537, 561]
    assert regions[0]["mask_shape"] == [46, 101]
    assert regions[0]["mask"] == "~abc"
    assert regions[1]["box"] == [260, 382, 340, 427]
    assert all(r["source"] == "sam-3.1" for r in regions)


def test_parse_empty_text_is_zero_matches() -> None:
    from flowforge.render.sam_client import _parse_sam_text

    assert _parse_sam_text("") == []


def test_build_box_prompt_matches_grammar() -> None:
    from flowforge.render.sam_client import build_box_prompt

    assert (build_box_prompt([444, 626, 675, 849], [1800, 1200])
            == "<0f>1<|box;x1=444;y1=626;x2=675;y2=849;w=1800;h=1200|>")


def test_parse_sparse_ids_and_mask_shape() -> None:
    from flowforge.render.sam_client import _parse_sam_text

    text = ("<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
            "<|mask;x=0;y=0;data=27,60,~abc|>,"
            "2<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
            "<|mask;x=0;y=0;data=27,48,!def|>")
    regions = _parse_sam_text(text)
    assert [r["object_id"] for r in regions] == [0, 2]
    assert regions[0]["mask_shape"] == [27, 60]
    assert regions[0]["mask_encoding"] == "~"
    assert regions[1]["mask_shape"] == [27, 48]
    assert regions[1]["mask_encoding"] == "!"


def test_parse_confidence_by_key() -> None:
    from flowforge.render.sam_client import _parse_sam_text

    text = ("<0f>1<|box;x1=444;y1=625;x2=679;y2=850;w=1800;h=1200;c=0.9609375|>"
            "<|mask;x=0;y=0;c=0.9609375;data=226,236,!xyz|>")
    regions = _parse_sam_text(text)
    assert len(regions) == 1
    assert regions[0]["confidence"] == 0.9609375
    assert regions[0]["box"] == [444, 625, 679, 850]


def test_registry_tool_keeps_contract_and_reports_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Replay discipline: unit tests never touch the network, even though
    # the tool defaults to use_api=True (live SAM is verified by probe).
    monkeypatch.setenv("FLOWFORGE_REPLAY", "1")
    import flowforge.render.sam_client as sam_client

    monkeypatch.setattr(sam_client, "CACHE_DIR", tmp_path / "sam_cache")
    from flowforge.agents.tools.registry import TOOLS

    segments = TOOLS["sam_segment"](_render(tmp_path))
    assert isinstance(segments, list) and len(segments) > 0
    assert "box" in segments[0]
    assert segments[0]["source"] == "local-fallback"
