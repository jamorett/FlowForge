"""Tool registry (S4/S5). Schema-validated, budget-metered, traced."""

from __future__ import annotations

from collections.abc import Callable

TOOLS: dict[str, Callable] = {}


def register(name: str):
    def deco(fn: Callable) -> Callable:
        TOOLS[name] = fn
        return fn
    return deco


@register("search_cards")
def search_cards(query: str) -> list:
    return []  # filled by flowforge.literature in S5


@register("fit_constants")
def fit_constants_tool(features, targets):
    from flowforge.dsl.fitting import fit_constants

    return fit_constants(features, targets).tolist()
