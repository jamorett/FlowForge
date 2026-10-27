"""Frozen harness thresholds. Change only via a new evals version."""

# Research: fraction of extracted cards that must parse and cite a source.
RESEARCH_MIN_PARSE_RATE = 0.95
# Physics: numerical tolerance for invariance and limit checks.
PHYSICS_TOLERANCE = 1e-8
# Symbolic: worst-case a priori error must beat baseline by this margin.
SYMBOLIC_MIN_IMPROVEMENT = 0.0
# Solver: short runs that diverge are failures, never silent retries.
SOLVER_MAX_DIVERGED_FRACTION = 0.0
