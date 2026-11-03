from flowforge.agents.dispatcher import ROLE_SCHEMAS, dispatch_role_mock
from flowforge.dsl.parser import tensor_coefficients
from scripts import run_controls


def _never(*_args, **_kwargs):
    raise AssertionError("constant control must never reach the live dispatcher")


def test_constant_control_is_llm_free_and_constant_only() -> None:
    dispatch = run_controls.make_dispatch("constant", _never, dispatch_role_mock, ROLE_SCHEMAS, 42, {"calls": 0})
    for role in ("board", "coder", "analyst", "skeptic", "composer"):
        dispatch(role, None, {})
    proposal = dispatch("theorist", None, {})
    assert proposal.expressions == list(run_controls.CONSTANT_EXPRESSIONS)
    for expr in proposal.expressions:  # every coefficient is a pure number (no I1/I2)
        assert all(coeff.is_number for coeff in tensor_coefficients(expr).values())
    flows = [{"kind": "periodic_hill", "alpha": 0.5, "reynolds": 5600}]
    assert dispatch("redteam", None, {"available_frozen_flows": flows}).flows == flows
    assert dispatch("redteam", None, {}).flows == [{"kind": "none"}]


def test_stub_redteam_applies_to_random_grammar() -> None:
    dispatch = run_controls.make_dispatch("random_grammar", _never, dispatch_role_mock, ROLE_SCHEMAS,
                                          42, {"calls": 0}, stub_redteam=True)
    flows = [{"kind": "periodic_hill", "alpha": 0.8, "reynolds": 5600}]
    assert dispatch("redteam", None, {"available_frozen_flows": flows}).flows == flows
    assert len(dispatch("theorist", None, {}).expressions) == 3  # seeded, no LLM


def test_heldout_dl_charges_free_constants() -> None:
    from flowforge.elegance.engine import constant_bits, description_length_v2

    assert constant_bits(1.5) < 4 < constant_bits(0.00394136) == 16.0
    assert description_length_v2(5, [0.333, -3.05432]) < description_length_v2(5, [0.00394, -3.05432])


def test_heldout_champion_prefers_transfer_over_train_fit() -> None:
    """Under heldout, a train-overfit candidate loses to one that holds on selection flows."""
    import numpy as np

    from flowforge.orchestrator.round import select_champion_by_train_attack

    pool = [{"expression": "0.333 * T1 + 1.5 * T3", "selection": 0.70},
            {"expression": "0.333 * T1 + 2 * I1 * T3", "selection": 1.30}]
    z = np.zeros((2, 3, 3))
    inv = {k: np.zeros(2) for k in ("I1", "I2", "I3", "I4", "I5")}
    basis = {k: z for k in ("T1", "T2", "T3", "T4")}
    champ = select_champion_by_train_attack(pool, inv, basis, z, attack_cases=[], selection="heldout")
    assert champ["expression"] == "0.333 * T1 + 1.5 * T3" and champ["selection"] == "heldout"
