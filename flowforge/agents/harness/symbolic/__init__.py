"""Symbolic harness: DSL, fitting, snapping, elegance.

Pass requires SymPy round-trip identity, a priori error vs frozen-RANS
targets, and snapping cost within the frozen 1% tolerance.
Positive control: zero correction (passes, description length minimal).
Negative control: deliberately wrong-limit expression; rung 0 rejects it.
"""
