from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from knowledge_engine.m27_learning_contracts import (
    LearningPolicyArea,
    LearningProposalKind,
    LearningProposalStatus,
    LearningRiskClass,
    LearningSignal,
    LearningSignalKind,
    LearningSignalSource,
)
from knowledge_engine.m27_learning_runtime import (
    InvalidLearningTransitionError,
    LearningProposalStore,
    LearningRuntime,
    LearningRuntimeError,
    UnknownLearningSignalError,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src" / "knowledge_engine"


def _signal(
    *,
    source_ref: str = "failure:unsupported-claim",
    classification: str = "UNSUPPORTED_CLAIM",
) -> LearningSignal:
    return LearningSignal.create(
        kind=LearningSignalKind.FAILURE_CLASS_SUMMARY,
        source=LearningSignalSource.FAILURE_CLASS_SUMMARY,
        source_ref=source_ref,
        policy_area=LearningPolicyArea.GUARDRAIL,
        classification=classification,
        count=3,
        reason_codes=("CLAIM_SUPPORT_GAP",),
        artifact_ids=("artifact:eval-001",),
    )


def _proposal(runtime: LearningRuntime):
    signal = runtime.observe_signal(_signal())
    return runtime.propose_from_signals(
        signal_ids=(signal.signal_id,),
        kind=LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE,
        observed_issue_class="UNSUPPORTED_CLAIM_CLUSTER",
        candidate_change_summary=(
            "Tighten claim-support guard thresholds for an offline candidate evaluation."
        ),
        expected_benefit_class="LOWER_UNSUPPORTED_CLAIM_RATE",
        risk_class=LearningRiskClass.HIGH,
        required_gate="offline.guardrail.v1",
    )


def test_observe_signal_accepts_only_sanitized_learning_signal() -> None:
    runtime = LearningRuntime()
    signal = _signal()
    assert runtime.observe_signal(signal) == signal
    assert runtime.observe_signal(signal) == signal
    with pytest.raises(LearningRuntimeError):
        runtime.observe_signal("raw query")  # type: ignore[arg-type]


def test_proposal_requires_observed_signals() -> None:
    runtime = LearningRuntime()
    signal = _signal()
    with pytest.raises(UnknownLearningSignalError):
        runtime.propose_from_signals(
            signal_ids=(signal.signal_id,),
            kind=LearningProposalKind.GUARDRAIL_HARDENING_CANDIDATE,
            observed_issue_class="UNSUPPORTED_CLAIM_CLUSTER",
            candidate_change_summary="Raise offline verification strictness for the candidate.",
            expected_benefit_class="LOWER_UNSUPPORTED_CLAIM_RATE",
            risk_class=LearningRiskClass.HIGH,
            required_gate="offline.guardrail.v1",
        )


def test_proposed_to_ready_for_review_lifecycle() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    assert proposal.status is LearningProposalStatus.PROPOSED
    ready = runtime.mark_proposal_ready_for_review(proposal.proposal_id)
    assert ready.status is LearningProposalStatus.READY_FOR_REVIEW
    assert ready.active is True
    assert ready.proposal_id == proposal.proposal_id


def test_rejected_proposal_cannot_become_ready_for_review() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    rejected = runtime.mark_proposal_rejected(proposal.proposal_id)
    assert rejected.status is LearningProposalStatus.REJECTED
    assert rejected.active is False
    with pytest.raises(InvalidLearningTransitionError):
        runtime.mark_proposal_ready_for_review(proposal.proposal_id)


def test_superseded_proposal_is_inactive_and_terminal() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    superseded = runtime.mark_proposal_superseded(proposal.proposal_id)
    assert superseded.status is LearningProposalStatus.SUPERSEDED
    assert superseded.active is False
    with pytest.raises(InvalidLearningTransitionError):
        runtime.mark_proposal_rejected(proposal.proposal_id)


def test_ready_for_review_can_be_rejected_by_human_governance_path() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    runtime.mark_proposal_ready_for_review(proposal.proposal_id)
    rejected = runtime.mark_proposal_rejected(proposal.proposal_id)
    assert rejected.status is LearningProposalStatus.REJECTED
    assert rejected.active is False


def test_propose_from_signals_is_deterministic_and_idempotent() -> None:
    runtime = LearningRuntime()
    first = _proposal(runtime)
    second = _proposal(runtime)
    assert first == second
    assert len(runtime.list_proposals()) == 1


def test_list_proposals_is_sorted_and_filterable() -> None:
    runtime = LearningRuntime()
    first = _proposal(runtime)
    second_signal = runtime.observe_signal(
        _signal(source_ref="failure:citation-gap", classification="CITATION_GAP")
    )
    second = runtime.propose_from_signals(
        signal_ids=(second_signal.signal_id,),
        kind=LearningProposalKind.EVAL_GATE_CANDIDATE,
        observed_issue_class="CITATION_GATE_CLUSTER",
        candidate_change_summary="Add an offline citation-binding evaluation candidate.",
        expected_benefit_class="HIGHER_GATE_SENSITIVITY",
        risk_class=LearningRiskClass.MEDIUM,
        required_gate="offline.eval-gate.v1",
    )
    listed = runtime.list_proposals()
    assert tuple(item.proposal_id for item in listed) == tuple(
        sorted((first.proposal_id, second.proposal_id))
    )
    runtime.mark_proposal_rejected(first.proposal_id)
    active = runtime.list_proposals(active_only=True)
    assert active == (runtime.inspect_proposal(second.proposal_id),)
    rejected = runtime.list_proposals(status=LearningProposalStatus.REJECTED)
    assert rejected == (runtime.inspect_proposal(first.proposal_id),)


def test_render_proposal_report_contains_no_signal_payloads() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    report = runtime.render_proposal_report(proposal.proposal_id)
    encoded = json.dumps(report, sort_keys=True)
    assert "failure:unsupported-claim" not in encoded
    assert "CLAIM_SUPPORT_GAP" not in encoded
    assert "artifact:eval-001" not in encoded
    assert proposal.proposal_id in encoded
    assert proposal.evidence_binding.signal_ids[0] in encoded
    assert report["governance"] == {
        "proposal_only": True,
        "requires_human_review": True,
        "requires_offline_gate": True,
        "auto_apply": False,
        "production_write": False,
        "runtime_behavior_change": False,
    }


@pytest.mark.parametrize(
    "name",
    (
        "apply_proposal",
        "auto_apply",
        "promote_proposal",
        "activate_policy",
        "write_runtime_config",
        "patch_code",
        "write_to_qdrant",
        "write_to_r2",
        "write_to_production_sqlite",
        "execute_skill",
        "invoke_mcp",
        "write_workspace",
        "start_agent_loop",
        "run_meta_harness",
    ),
)
def test_forbidden_runtime_method_names_do_not_exist(name: str) -> None:
    assert not hasattr(LearningRuntime, name)
    assert not hasattr(LearningProposalStore, name)


def _imports_for(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def test_learning_modules_have_no_stage7_stage8_stage9_stage10_runtime_dependency() -> None:
    imports = _imports_for(SRC_ROOT / "m27_learning_contracts.py")
    imports |= _imports_for(SRC_ROOT / "m27_learning_runtime.py")
    forbidden_fragments = (
        "m27_skill",
        "m27_workspace",
        "m27_mcp",
        "m27_memory",
    )
    assert all(
        not any(fragment in imported for fragment in forbidden_fragments)
        for imported in imports
    )


def test_learning_modules_have_no_provider_or_backend_dependencies() -> None:
    imports = _imports_for(SRC_ROOT / "m27_learning_contracts.py")
    imports |= _imports_for(SRC_ROOT / "m27_learning_runtime.py")
    forbidden_fragments = (
        "openai",
        "anthropic",
        "google",
        "qdrant",
        "boto",
        "sqlite",
        "psycopg",
        "requests",
        "httpx",
    )
    assert all(
        not any(fragment in imported.casefold() for fragment in forbidden_fragments)
        for imported in imports
    )


def test_stage11_is_not_wired_into_existing_m27_runtime_modules() -> None:
    offenders: list[str] = []
    for path in sorted(SRC_ROOT.glob("m27_*.py")):
        if path.name in {"m27_learning_contracts.py", "m27_learning_runtime.py"}:
            continue
        if "m27_learning" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == []


def test_stage11_does_not_modify_stage7_stage8_stage9_stage10_surfaces() -> None:
    protected = (
        "m27_skill_contracts.py",
        "m27_workspace_contracts.py",
        "m27_workspace_store.py",
        "m27_mcp_contracts.py",
        "m27_mcp_exposure.py",
        "m27_memory_contracts.py",
        "m27_memory_runtime.py",
    )
    for name in protected:
        text = (SRC_ROOT / name).read_text(encoding="utf-8")
        assert "m27_learning" not in text


def test_store_is_pure_in_memory_and_has_no_root_or_backend_surface() -> None:
    store = LearningProposalStore()
    assert not hasattr(store, "root")
    assert not hasattr(store, "path")
    assert not hasattr(store, "backend")
    assert not hasattr(store, "provider")


def test_no_policy_activation_authority_is_exposed() -> None:
    runtime = LearningRuntime()
    proposal = _proposal(runtime)
    payload = proposal.as_dict()
    assert payload["authority"] == "PROPOSAL_ONLY"
    assert payload["auto_apply"] is False
    assert payload["production_write"] is False
    assert "activation" not in payload
    assert "authoritative" not in payload
