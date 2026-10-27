"""Symbolic harness tasks. Scaffold only."""

from dataclasses import dataclass

MAX_COMPLEXITY_NODES = 25
SNAPPING_TOLERANCE = 0.01  # frozen; never tune after seeing results


@dataclass(frozen=True)
class SymbolicTask:
    """Parse, fit, and score one candidate in the closure language."""

    expression: str
    case_ids: tuple[str, ...]
