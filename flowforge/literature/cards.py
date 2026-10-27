"""Closure cards (S5.3). Cards whose equations fail SymPy parse are rejected."""

from __future__ import annotations

from dataclasses import dataclass

from flowforge.dsl.parser import parse_expression


@dataclass(frozen=True)
class ClosureCard:
    doi: str
    mechanism: str
    model_form: str
    flows_calibrated: tuple[str, ...] = ()

    def validate(self) -> bool:
        try:
            parse_expression(self.model_form)
            return True
        except Exception:
            return False
