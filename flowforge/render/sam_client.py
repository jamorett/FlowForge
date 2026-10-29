"""SAM 3.1 error-region segmentation client (S6).

Spec (v2 Build spec.md): PyVista renders plus SAM 3.1 segment error regions
(bubble, reattachment, shear layer) and pixel masks map back to mesh cells;
vision goes through the Meta Model API (confirm the endpoint at kickoff).

This module is the honest implementation of that contract:

- Live path: stream the error-map PNG to ``POST <base>/responses``
  with ``model: sam-3.1`` (same Bearer ``MODEL_API_KEY`` as the rest of
  the API). First a one-concept noun phrase; on zero matches the local
  box is re-sent as a box prompt (:func:`build_box_prompt`) and SAM
  answers with a refined box plus mask under our id. Mask payloads are
  stored raw (base85, ``~``/``!``); raster decoding needs the
  ``@meta-sam/parser`` alphabet, so only boxes are consumed downstream.
  ``FLOWFORGE_SAM_ENDPOINT`` remains as a second attempt for a
  kickoff-configured custom endpoint.
- Offline path: deterministic local high-error segmentation (90th-percentile
  cluster) from the ``.npy`` sidecar written by ``render_png``.
- No network when ``FLOWFORGE_REPLAY=1``, when no API key is configured,
  or when ``use_api=False``. API successes are cached by content hash under
  ``runs/.sam_cache`` so identical images are never re-billed.
- Every result carries ``source``: ``"sam-3.1"`` or ``"local-fallback"``.
  Callers must surface it; fallback output is never reported as SAM.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

SAM_MODEL = "sam-3.1"
META_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_SAM_PATH = "/sam/segment"
CACHE_DIR = Path("runs/.sam_cache")


def _sam_endpoint() -> str:
    override = os.environ.get("FLOWFORGE_SAM_ENDPOINT")
    if override:
        return override
    base = os.environ.get("MODEL_API_BASE", META_BASE_URL).rstrip("/")
    return base + DEFAULT_SAM_PATH


def _api_enabled(use_api: bool) -> bool:
    if not use_api:
        return False
    if os.environ.get("FLOWFORGE_REPLAY") == "1":
        return False
    return bool(os.environ.get("MODEL_API_KEY"))


def _content_hash(image_path: Path, prompt: str = "") -> str:
    h = hashlib.sha256()
    h.update(image_path.read_bytes())
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def local_segment(image_path: str) -> list[dict[str, Any]]:
    """Deterministic offline segmentation from the .npy error sidecar."""
    p = Path(image_path)
    npy_path = p.with_suffix(".npy")
    if not npy_path.exists():
        return [{"region": "global", "box": [0, 0, 100, 100],
                 "severity": "medium", "source": "local-fallback"}]

    errors = np.load(npy_path)
    if errors.ndim != 2 or errors.size == 0 or not np.all(np.isfinite(errors)):
        return [{"region": "global", "box": [0, 0, 100, 100],
                 "severity": "medium", "source": "local-fallback"}]
    threshold = float(np.percentile(errors, 90))
    high_mask = errors >= threshold
    h, w = errors.shape

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
            "source": "local-fallback",
        }
    ]


def _png_size(image_path: Path) -> tuple[int, int]:
    """Pixel (width, height) from a PNG IHDR header (stdlib only)."""
    import struct

    data = image_path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def build_box_prompt(box: list[int], image_size: list[int],
                     obj_id: int = 1, frame: int = 0) -> str:
    """Render a box-prompt token line (SAM prompt grammar).

    The text holds box prompts, never mixed with a noun phrase.
    Coordinates are media pixels; ``image_size`` is ``[w, h]``.
    """
    x1, y1, x2, y2 = (int(v) for v in box)
    w, h = (int(v) for v in image_size)
    assert x1 <= x2 and y1 <= y2, "a box names the object; it cannot be negative"
    assert 0 <= x1 < w and 0 <= x2 < w and 0 <= y1 < h and 0 <= y2 < h, (
        f"box {box} lies outside the {w}x{h} media")
    return (f"<{frame}f>{obj_id}<|box;x1={x1};y1={y1};x2={x2};y2={y2};"
            f"w={w};h={h}|>")


def _parse_sam_text(text: str) -> list[dict[str, Any]]:
    """Parse SAM 3.1 segmentation token text into region records.

    Grammar: ``<Nf>id<|box;...|>...<|mask;...|>`` per record; ids are
    stable per object but NOT dense (a line can carry 0, 2). Boxes are
    source pixels; mask ``data`` is ``H,W,enc+payload`` (base85). Empty
    text = zero matches (valid, not failure). Fields are read by key so
    optional confidence ``c`` tokens parse identically.
    """
    import re

    regions: list[dict[str, Any]] = []
    frame = 0
    frame_match = re.search(r"<(\d+)f>", text)
    if frame_match:
        frame = int(frame_match.group(1))
    box_re = re.compile(
        r"(\d+)<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);"
        r"w=(\d+);h=(\d+)(?:;c=([0-9]+(?:\.[0-9]+)?))?\|>")
    mask_re = re.compile(
        r"<\|mask;x=(\d+);y=(\d+)(?:;c=([0-9]+(?:\.[0-9]+)?))?;data="
        r"(\d+),(\d+),([^|]*)\|>")
    boxes = box_re.findall(text)
    masks = mask_re.findall(text)
    for ordinal, found in enumerate(boxes):
        obj_id, x1, y1, x2, y2, w, h, conf = found
        record: dict[str, Any] = {
            "region": f"error_region_{obj_id}",
            "object_id": int(obj_id),
            "box": [int(x1), int(y1), int(x2), int(y2)],
            "image_size": [int(w), int(h)],
            "frame": frame,
            "source": "sam-3.1",
        }
        if conf:
            record["confidence"] = float(conf)
        if ordinal < len(masks):
            mx, my, mconf, mh, mw, payload = masks[ordinal]
            record["mask_origin"] = [int(mx), int(my)]
            record["mask_shape"] = [int(mh), int(mw)]
            record["mask_encoding"] = (payload[:1] if payload else "")
            record["mask"] = payload
            if mconf:
                record.setdefault("confidence", float(mconf))
        regions.append(record)
    return regions


def _stream_responses_text(url: str, headers: dict, body: dict) -> str | None:
    """POST a streaming Responses request; return the output_text or None."""
    import httpx
    import json as jsonlib

    chunks: list[str] = []
    try:
        with httpx.stream("POST", url, headers=headers, json=body,
                          timeout=180.0) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                payload_text = line[len("data: "):].strip()
                if payload_text == "[DONE]":
                    break
                try:
                    event = jsonlib.loads(payload_text)
                except ValueError:
                    continue
                etype = event.get("type", "")
                if etype == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str):
                        chunks.append(delta)
                elif etype in ("response.failed", "response.incomplete"):
                    logger.warning("sam_segment: stream %s (%s)",
                                   etype, event.get("error") or event.get("incomplete_details"))
                    return None
                elif etype == "response.completed":
                    break
    except Exception as exc:
        logger.warning("sam_segment: stream request failed (%s: %s)",
                       type(exc).__name__, exc)
        return None
    return "".join(chunks)


def _sam_api_segment(image_path: Path,
                     prompt: str) -> list[dict[str, Any]] | None:
    """Query SAM 3.1 over the Responses stream.

    Returns a regions list on transport success — possibly EMPTY, which
    is SAM's valid zero-match outcome, not a failure. Returns None only
    when the request itself failed (caller falls back to local).
    """
    import httpx

    key = os.environ.get("MODEL_API_KEY", "")
    digest = _content_hash(image_path, prompt)
    cached = CACHE_DIR / f"{digest}.json"
    if cached.exists():
        try:
            data = json.loads(cached.read_text(encoding="utf-8"))
            regions = data.get("regions")
            if isinstance(regions, list):
                return regions
        except Exception:
            pass

    # The key lives only in request headers below; it is never logged.
    headers = {"Authorization": f"Bearer {key}"}
    image_b64 = base64.b64encode(image_path.read_bytes()).decode()
    data_url = f"data:image/png;base64,{image_b64}"
    base = os.environ.get("MODEL_API_BASE", META_BASE_URL).rstrip("/")
    attempts: list[tuple[str, dict]] = [
        # Responses API with the message/media part shape SAM expects.
        (base + "/responses",
         {"model": SAM_MODEL,
          "input": [{"type": "message", "role": "user", "content": [
              {"type": "input_text", "text": prompt},
              {"type": "input_image", "image_url": data_url}]}],
          "max_output_tokens": 1024,
          "stream": True,
          "metadata": {"mask_encoding": "one_bit"}}),
        # Kickoff-configured custom endpoint (FLOWFORGE_SAM_ENDPOINT).
        (_sam_endpoint(),
         {"model": SAM_MODEL, "image_b64": image_b64, "task": "segment_high_error"}),
    ]
    regions: list[dict[str, Any]] | None = None
    for url, body in attempts:
        if body.get("stream"):
            text = _stream_responses_text(url, headers, body)
            if text is None:
                continue
            regions = _parse_sam_text(text)
            break
        try:
            resp = httpx.post(url, headers=headers, json=body, timeout=120.0)
            resp.raise_for_status()
            payload = resp.json()
            maybe = payload.get("regions")
            regions = maybe if isinstance(maybe, list) else None
            if regions is None:
                continue
            break
        except Exception as exc:
            logger.warning("sam_segment: %s failed (%s); trying next path",
                           url, type(exc).__name__)
            continue
    if not isinstance(regions, list):
        logger.warning("sam_segment: all API paths failed; using local fallback")
        return None
    for r in regions:
        if isinstance(r, dict):
            r.setdefault("source", "sam-3.1")
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps({"model": SAM_MODEL, "regions": regions}),
                          encoding="utf-8")
    except Exception:
        pass
    return regions


def segment_error_regions(image_path: str, use_api: bool = True,
                          prompt: str = "high error region") -> dict[str, Any]:
    """Segment high-error regions, preferring SAM 3.1, else local fallback.

    ``prompt`` is the single short noun phrase sent to SAM 3.1.
    """
    p = Path(image_path)
    if not p.exists():
        return {"image": image_path, "source": "local-fallback",
                "model": None,
                "regions": [{"region": "global", "box": [0, 0, 100, 100],
                             "severity": "medium", "source": "local-fallback"}],
                "detail": "image missing; canned global box"}

    regions: list[dict[str, Any]] | None = None
    if _api_enabled(use_api):
        regions = _sam_api_segment(p, prompt)
    if regions is None:
        regions = local_segment(image_path)
        return {"image": image_path, "source": "local-fallback", "model": None,
                "regions": regions,
                "detail": "offline/local segmentation (no API call)"}
    if regions:
        return {"image": image_path, "source": "sam-3.1", "model": SAM_MODEL,
                "regions": regions,
                "detail": f"SAM 3.1 via Meta Model API (prompt {prompt!r})"}
    # Concept prompt drew zero matches (valid outcome): the offline box
    # proposes a location and SAM disposes with a mask under our id.
    # Prompt grammar holds box prompts, never mixed with a noun phrase.
    local = local_segment(image_path)
    clusters = [r for r in local if r.get("region") != "global" and "box" in r]
    if _api_enabled(use_api) and clusters:
        try:
            w, h = _png_size(p)
            box_prompt = build_box_prompt(clusters[0]["box"], [w, h])
            refined = _sam_api_segment(p, box_prompt)
        except Exception as exc:
            logger.warning("sam_segment: box refine failed (%s: %s)",
                           type(exc).__name__, exc)
            refined = None
        if refined:
            for r in refined:
                if isinstance(r, dict):
                    r["refined_from_local_box"] = clusters[0]["box"]
            return {"image": image_path, "source": "sam-3.1",
                    "model": SAM_MODEL, "regions": refined,
                    "detail": "SAM 3.1 box-refine of local proposal"}
        if refined is not None:
            return {"image": image_path, "source": "sam-3.1",
                    "model": SAM_MODEL, "regions": [],
                    "detail": "SAM 3.1 zero matches (concept + box refine)"}
    return {"image": image_path, "source": "sam-3.1", "model": SAM_MODEL,
            "regions": [],
            "detail": "SAM 3.1 via Meta Model API (zero matches for the prompt)"}
