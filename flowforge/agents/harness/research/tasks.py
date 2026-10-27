"""Research harness tasks. Scaffold only."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CardTask:
    """Extract a closure card from one open-access paper."""

    doi: str
    title: str
    abstract: str


@dataclass(frozen=True)
class CardResult:

    parses_in_sympy: bool
    mechanism_cited: bool
    prediction_testable: bool
