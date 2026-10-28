"""Positive and negative control fixtures for agent capability evals (S5.1).

Negative controls are mandatory: a harness that only rewards hits teaches guessing.
"""

from __future__ import annotations
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ResearchFixture:
    doi: str
    title: str
    text: str
    expected_valid: bool
    description: str


RESEARCH_FIXTURES: list[ResearchFixture] = [
    # Positive: valid SymPy expression and clear mechanism citation
    ResearchFixture(
        doi="10.1017/jfm.2019.100",
        title="Curvature correction in separated shear layers",
        text="We propose an eddy viscosity correction a_delta = -0.05 * T1 * tanh(I1). "
             "Mechanism: streamline curvature stabilizes turbulent kinetic energy.",
        expected_valid=True,
        description="Standard valid curvature correction card",
    ),
    ResearchFixture(
        doi="10.1063/1.868758",
        title="Nonlinear k-omega constitutive closure model",
        text="A quadratic model equation a_delta = 0.08 * T2 + 0.02 * T3. "
             "Mechanism: secondary flows in non-circular ducts driven by Reynolds stress anisotropy.",
        expected_valid=True,
        description="Valid quadratic constitutive relation",
    ),
    # Negative: syntax error / unparsable SymPy
    ResearchFixture(
        doi="10.1000/bad.syntax",
        title="Defective closure proposal",
        text="The correction is a_delta = ((T1 + * / 5)). Mechanism: none.",
        expected_valid=False,
        description="Corrupt syntax that fails SymPy parsing",
    ),
    # Negative: valid math but zero mechanism citation
    ResearchFixture(
        doi="10.1000/no.mechanism",
        title="Unsubstantiated fit",
        text="We fit a_delta = 0.1 * T1 on some data points without physical justification.",
        expected_valid=False,
        description="Missing physical mechanism citation",
    ),
]


@dataclass(frozen=True)
class PhysicsFixture:
    candidate_id: str
    a_delta: np.ndarray
    expected_pass: bool
    description: str


def generate_physics_fixtures() -> list[PhysicsFixture]:
    # Positive: symmetric, traceless, realizable
    a_good = np.zeros((4, 3, 3))
    a_good[:, 0, 1] = a_good[:, 1, 0] = 0.02
    a_good[:, 0, 0] = 0.01
    a_good[:, 1, 1] = -0.01

    # Negative 1: Asymmetric
    a_asym = a_good.copy()
    a_asym[:, 0, 1] = 0.05
    a_asym[:, 1, 0] = -0.05

    # Negative 2: Non-traceless
    a_nontrace = a_good.copy()
    a_nontrace[:, 0, 0] = 0.5
    a_nontrace[:, 1, 1] = 0.5
    a_nontrace[:, 2, 2] = 0.5

    # Negative 3: Unphysical eigenvalues violating Lumley triangle
    a_unrealizable = np.zeros((4, 3, 3))
    a_unrealizable[:, 0, 0] = 1.5
    a_unrealizable[:, 1, 1] = -0.75
    a_unrealizable[:, 2, 2] = -0.75

    return [
        PhysicsFixture("phys_pos_1", a_good, True, "Physically realizable symmetric traceless"),
        PhysicsFixture("phys_neg_asym", a_asym, False, "Asymmetric tensor"),
        PhysicsFixture("phys_neg_nontrace", a_nontrace, False, "Non-zero trace tensor"),
        PhysicsFixture("phys_neg_unreal", a_unrealizable, False, "Eigenvalue outside Lumley triangle"),
    ]


@dataclass(frozen=True)
class SymbolicFixture:
    expression: str
    expected_valid: bool
    description: str


SYMBOLIC_FIXTURES: list[SymbolicFixture] = [
    # Positive
    SymbolicFixture("0", True, "Identity zero correction"),
    SymbolicFixture("I1", True, "Linear first invariant"),
    SymbolicFixture("-0.08 * tanh(I1)", True, "Bounded nonlinear damping"),
    SymbolicFixture("div(I1, I2)", True, "Protected safe division"),
    # Negative
    SymbolicFixture("I1 +", False, "Invalid AST trailing operator"),
    SymbolicFixture("I1 / I2", False, "Unprotected raw division"),
    SymbolicFixture("I1 + I2 + I3 + I4 + I5 + I1*I2 + I2*I3 + I3*I4 + I4*I5 + I1*I3 + I2*I4 + I1*I5 + I1**2 + I2**2 + I3**2 + I4**2 + I5**2", False, "Complexity exceeds 25 node cap"),
]
