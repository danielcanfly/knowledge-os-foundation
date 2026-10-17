from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from knowledge_engine import m26_aq_semantic_contract as canonical
from knowledge_engine import m26_pa7_arbitrary_query_runtime as legacy


def _call(**overrides):
    arguments = {
        "root": Path("/nonprod"),
        "gate": {},
        "question": "What is a governed skill?",
        "owner_subject_hash": "owner",
        "provider_client": object(),
        "max_provider_calls": 1,
        "max_cost": Decimal("0.01"),
    }
    arguments.update(overrides)
    return legacy.run_owner_arbitrary_query(**arguments)


def test_legacy_entrypoint_forwards_compatibility_loader_bundle(monkeypatch):
    bundle = object()
    captured = {}
    monkeypatch.setattr(legacy, "load_production_answer_bundle", lambda: bundle)

    def canonical_run(**kwargs):
        captured.update(kwargs)
        return {"status": "delegated"}

    monkeypatch.setattr(canonical, "run_owner_arbitrary_query", canonical_run)
    assert _call() == {"status": "delegated"}
    assert captured["answer_bundle"] is bundle


def test_explicit_bundle_does_not_touch_environment_loader(monkeypatch):
    bundle = object()
    monkeypatch.setattr(
        legacy,
        "load_production_answer_bundle",
        lambda: pytest.fail("environment loader must not run"),
    )
    monkeypatch.setattr(
        canonical,
        "run_owner_arbitrary_query",
        lambda **kwargs: {"same_bundle": kwargs["answer_bundle"] is bundle},
    )
    assert _call(answer_bundle=bundle) == {"same_bundle": True}


def test_compatibility_loader_failure_remains_fail_closed(monkeypatch):
    def unavailable():
        raise RuntimeError("candidate bundle unavailable")

    monkeypatch.setattr(legacy, "load_production_answer_bundle", unavailable)
    monkeypatch.setattr(
        canonical,
        "run_owner_arbitrary_query",
        lambda **_kwargs: pytest.fail("canonical runtime must not run without a bundle"),
    )
    with pytest.raises(RuntimeError, match="candidate bundle unavailable"):
        _call()


def test_canonical_resolver_honors_pre_convergence_read_only_loader(monkeypatch):
    bundle = object()
    monkeypatch.setattr(legacy, "load_production_answer_bundle", lambda: bundle)
    assert canonical._resolve_production_answer_bundle(None) is bundle


def test_canonical_resolver_prefers_explicit_bundle(monkeypatch):
    explicit = object()
    monkeypatch.setattr(
        canonical,
        "load_production_answer_bundle",
        lambda: pytest.fail("canonical loader must not run"),
    )
    monkeypatch.setattr(
        legacy,
        "load_production_answer_bundle",
        lambda: pytest.fail("legacy loader must not run"),
    )
    assert canonical._resolve_production_answer_bundle(explicit) is explicit


def test_canonical_resolver_prefers_current_injected_loader(monkeypatch):
    current = object()
    historical = object()
    monkeypatch.setattr(canonical, "load_production_answer_bundle", lambda: current)
    monkeypatch.setattr(legacy, "load_production_answer_bundle", lambda: historical)
    assert canonical._resolve_production_answer_bundle(None) is current
