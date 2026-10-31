"""Curated literature cards for the Theorist."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from flowforge.dsl.parser import validate_candidate

logger = logging.getLogger(__name__)


def load_literature_cards(directory: str | Path = "library/literature") -> list[dict]:
    """Load curated literature cards sorted by id.

    Invalid JSON files and cards whose ``dsl_expression`` fails
    :func:`flowforge.dsl.parser.validate_candidate` are skipped with a
    logged warning and never raise. ``ImportError`` always propagates.
    """
    cards_dir = Path(directory)
    if not cards_dir.is_dir():
        return []
    cards: list[dict] = []
    for card_path in sorted(cards_dir.glob("*.json")):
        try:
            raw_text = card_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("skipping literature card %s: %s", card_path.name, exc)
            continue
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.warning("skipping literature card %s: %s", card_path.name, exc)
            continue
        if not isinstance(payload, dict):
            logger.warning("skipping literature card %s: not a JSON object", card_path.name)
            continue
        expr = payload.get("dsl_expression")
        if not isinstance(expr, str) or not expr.strip():
            logger.warning("skipping literature card %s: missing dsl_expression", card_path.name)
            continue
        try:
            validate_candidate(expr)
        except (ValueError, SyntaxError, TypeError, AttributeError) as exc:
            logger.warning("skipping literature card %s: %s", card_path.name, exc)
            continue
        cards.append(payload)
    cards.sort(key=lambda card: str(card.get("id", "")))
    return cards
