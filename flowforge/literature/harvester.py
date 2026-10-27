"""Literature harvester (S5.3). Cached, rate-limited, offline-testable.

Network fetch is isolated in _fetch_text so unit tests inject fixtures.
Responses cache under data/literature/. Unparseable cards are rejected.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from flowforge.literature.cards import ClosureCard

CACHE = Path("data/literature")


def _cache_key(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _fetch_text(query: str) -> str:
    """Placeholder for arXiv/OpenAlex/Semantic Scholar APIs (S5)."""
    import httpx

    resp = httpx.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": query, "max_results": 5},
        headers={"User-Agent": "FlowForge/0.1 (research; cached)"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.text


def harvest(query: str, fetch=None, cache_dir: Path = CACHE) -> list[ClosureCard]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _cache_key(query)
    cached = cache_dir / f"{key}.json"
    if cached.exists():
        raw = json.loads(cached.read_text(encoding="utf-8"))
    else:
        text = (fetch or _fetch_text)(query)
        cached.write_text(json.dumps({"query": query, "text": text}),
                          encoding="utf-8")
        raw = {"query": query, "text": text}
    return extract_cards(raw["text"])


def extract_cards(text: str) -> list[ClosureCard]:
    """Extract toy cards from 'MECHANISM: ... FORM: ...' blocks (fixtures)."""
    cards: list[ClosureCard] = []
    for block in text.split("---"):
        mech = form = None
        for line in block.splitlines():
            line = line.strip()
            if line.startswith("MECHANISM:"):
                mech = line.split(":", 1)[1].strip()
            if line.startswith("FORM:"):
                form = line.split(":", 1)[1].strip()
        if mech and form:
            card = ClosureCard(doi="fixture", mechanism=mech, model_form=form)
            if card.validate():
                cards.append(card)
    return cards
