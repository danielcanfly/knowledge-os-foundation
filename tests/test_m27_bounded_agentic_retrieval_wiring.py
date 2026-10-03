from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_engine import m26_aq_semantic_contract as contract
from knowledge_engine import m26_ask_api
from knowledge_engine.m26_production_promotion_closure import load_json
from tests.test_m26_aq_semantic_closure_runtime import (
    _AbstainingProvider,
    _rich_passage,
    _stub_public_retrieval,
)

ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = ROOT / "pilot/m26/m26-pa-7-resolved-production-gate.json"
OWNER_SUBJECT_HASH = "93c8aaae82e498dc2e6bfdcaa48b8823fe21a5ceef44ca2cf9cf35cf6350e05b"


def _supported_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = [
        _rich_passage(
            "ev_durable",
            "Persisted server-side state preserves run progress after a client disconnect.",
            "durable-note",
        ),
        _rich_passage(
            "ev_completion",
            "Completion verification happens before terminal success.",
            "completion-note",
        ),
        _rich_passage(
            "ev_observability",
            "Observability exposes status and reattachment for the continuing run.",
            "observability-note",
        ),
    ]
    _stub_public_retrieval(monkeypatch, evidence=evidence)


def test_canonical_runtime_crosses_stage6_boundary_once_with_flags_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _supported_fixture(monkeypatch)
    monkeypatch.delenv("M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED", raising=False)
    monkeypatch.delenv("M27_ISOLATED_RUNTIME", raising=False)

    original = contract.run_bounded_agentic_second_round
    calls = 0

    def tracked(**kwargs):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(contract, "run_bounded_agentic_second_round", tracked)
    response = m26_ask_api.run_owner_arbitrary_query(
        root=ROOT,
        gate=load_json(GATE_PATH),
        question=(
            "Why is persisted run state important when a client disconnects "
            "before a long-running workflow has finished?"
        ),
        owner_subject_hash=OWNER_SUBJECT_HASH,
        provider_client=_AbstainingProvider(),
    )
    assert calls == 1
    assert response["unsupported_accepted_claims"] == 0
    assert response["citations"]


def test_requested_flag_without_isolated_marker_still_runs_only_initial_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _supported_fixture(monkeypatch)
    monkeypatch.setenv("M27_BOUNDED_AGENTIC_RETRIEVAL_ENABLED", "true")
    monkeypatch.delenv("M27_ISOLATED_RUNTIME", raising=False)

    original_retrieval = contract.legacy._run_lexical_primary_retrieval
    retrieval_calls = 0

    def tracked_retrieval(**kwargs):
        nonlocal retrieval_calls
        retrieval_calls += 1
        return original_retrieval(**kwargs)

    monkeypatch.setattr(
        contract.legacy,
        "_run_lexical_primary_retrieval",
        tracked_retrieval,
    )
    response = contract.run_owner_arbitrary_query(
        root=ROOT,
        gate=load_json(GATE_PATH),
        question=(
            "Why is persisted run state important when a client disconnects "
            "before a long-running workflow has finished?"
        ),
        owner_subject_hash=OWNER_SUBJECT_HASH,
        provider_client=_AbstainingProvider(),
    )
    assert retrieval_calls == 1
    assert response["unsupported_accepted_claims"] == 0
