"""Physics harness tasks. Scaffold only."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PhysicsTask:
    """Check one candidate correction against physics invariants."""

    candidate_hash: str
    case_id: str


# Checks, in order: rotation invariance, symmetry, trace-free,
# barycentric realizability, zero-strain and log-layer limits.
CHECKS = (
    "rotation_invariance",
    "symmetry",
    "trace_free",
    "realizability",
    "zero_strain_limit",
    "log_layer_limit",
)
