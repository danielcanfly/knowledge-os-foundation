from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from knowledge_engine import m26_pa7_arbitrary_query_runtime as runtime
from knowledge_engine.m26_production_promotion_closure import load_json
from tests.test_m26_pa_7_fast_public_path import (
    ROOT,
    GATE_PATH,
    OWNER_SUBJECT_HASH,
    FastAnswerProvider,
    LeakyProvider,
    fast_path_bundle,
)

CANONICAL_V2 = "m26-fast-public/canonical-semantic-v2"


def _execute(monkeypatch, provider, *, max_calls=2, max_cost=Decimal("0.10")):
    bundle, evidence, retrieval = fast_path_bundle.__wrapped__()
    monkeypatch.setattr(runtime, "load_production_answer_bundle", lambda: bundle)
    monkeypatch.setattr(
        runtime, "_run_lexical_primary_retrieval",
        lambda **_kw: (retrieval["lexical"], retrieval["dense"]),
    )
    monkeypatch.setattr(runtime, "_select_evidence", lambda **_kw: [evidence])
    monkeypatch.setattr(runtime, "_has_meaningful_overlap", lambda _q, _ev: True)
    return runtime.run_owner_arbitrary_query(
        root=ROOT,
        gate=load_json(GATE_PATH),
        question="What is a skill in an AI agent architecture?",
        owner_subject_hash=OWNER_SUBJECT_HASH,
        provider_client=provider,
        max_provider_calls=max_calls,
        max_cost=max_cost,
    )


def test_v2_positive_retains_semantic_proof_and_single_call(monkeypatch):
    provider = FastAnswerProvider(
        answer_text="A skill is a method an agent follows for a class of task.",
        citation_ids=["ev_skill"],
    )
    response = _execute(monkeypatch, provider)
    assert provider.calls == response["provider_call_count"] == 1
    assert response["status"] == "owner_only_cited_answer"
    assert response["fast_public_contract_version"] == CANONICAL_V2
    closure = response["semantic_closure"]
    assert isinstance(closure, dict) and closure
    assert closure["canonical_fast_candidate"]["accepted"] is True
    assert closure["semantic_contract"]["fingerprint"]


@pytest.mark.parametrize("kind", ["missing_citation", "private_leak"])
def test_v2_invalid_outputs_fail_closed_with_bounded_attempts(monkeypatch, kind):
    provider = (
        FastAnswerProvider(answer_text="Fine answer", citation_ids=["missing"])
        if kind == "missing_citation"
        else LeakyProvider(answer_text="ignored", citation_ids=["ev_skill"])
    )
    response = _execute(monkeypatch, provider)
    assert 1 <= provider.calls <= 2
    assert provider.calls == response["provider_usage_contract"]["request_provider_calls"]
    assert response["provider_usage_contract"]["physical_attempts_observed"] == provider.calls
    assert response["fast_public_contract_version"] == CANONICAL_V2
    assert response["status"] == "owner_only_safe_abstention"
    assert not response.get("citations")
    assert not response.get("answer_text")
    assert isinstance(response["semantic_closure"], dict)
    assert Decimal(str(response.get("payg_equivalent_cost_usd", "0"))) <= Decimal("0.10")


def test_v2_explicit_single_attempt_cap_never_retries(monkeypatch):
    provider = FastAnswerProvider(answer_text="Fine answer", citation_ids=["missing"])
    response = _execute(monkeypatch, provider, max_calls=1)
    assert provider.calls == 1
    assert response["status"] == "owner_only_safe_abstention"
    assert not response.get("citations")


class UnknownEffectProvider(FastAnswerProvider):
    def call(self, payload, call_class):
        self.calls += 1
        self.payloads.append(payload)
        self.call_classes.append(call_class)
        raise ValueError("simulated response lost after side effect")


def test_v2_unknown_effect_prohibits_retry(monkeypatch):
    provider = UnknownEffectProvider(answer_text="unused", citation_ids=["ev_skill"])
    response = _execute(monkeypatch, provider)
    assert provider.calls == 1
    assert response["status"] == "owner_only_safe_abstention"
    assert not response.get("citations")


class ExpensiveProvider(FastAnswerProvider):
    def call(self, payload, call_class):
        result = super().call(payload, call_class)
        result["cost_usd"] = "1.5"
        return result


def test_v2_cost_cap_rejects_publication(monkeypatch):
    provider = ExpensiveProvider(
        answer_text="A skill is a method an agent follows for a class of task.",
        citation_ids=["ev_skill"],
    )
    response = _execute(monkeypatch, provider)
    assert provider.calls == 1
    assert response["status"] == "owner_only_safe_abstention"
    assert not response.get("citations")
