from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from knowledge_engine.m27_memory_contracts import (
    STAGE10_MEMORY_POLICY,
    MemoryActivation,
    MemoryClass,
    MemoryContractError,
    MemoryOriginKind,
    MemoryProvenance,
    MemoryReviewDecision,
)
from knowledge_engine.m27_memory_runtime import (
    GovernedMemoryRuntime,
    MemoryIntegrityError,
    MemoryRuntimeDisabledError,
    UnsafeMemoryStorePathError,
)


def _activation() -> MemoryActivation:
    return MemoryActivation(enabled=True, isolated_runtime=True)


def _provenance(ref: str = "task:stage10:fixture") -> MemoryProvenance:
    return MemoryProvenance(
        origin_kind=MemoryOriginKind.TASK_SUMMARY,
        origin_ref=ref,
        source_sha256=hashlib.sha256(ref.encode()).hexdigest(),
    )


def _runtime(tmp_path: Path) -> GovernedMemoryRuntime:
    return GovernedMemoryRuntime(
        root=tmp_path / "memory-root",
        activation=_activation(),
    )


def _candidate(runtime: GovernedMemoryRuntime):
    return runtime.propose_candidate(
        memory_class=MemoryClass.PROJECT,
        scope_token="project:alpha",
        summary="Project uses bounded retrieval diagnostics for gap analysis.",
        provenance=_provenance(),
        tags=("retrieval", "stage10"),
    )


def test_runtime_is_default_off_and_does_not_create_store(tmp_path: Path) -> None:
    root = tmp_path / "disabled-memory"
    runtime = GovernedMemoryRuntime(root=root)

    assert runtime.activation.enabled is False
    assert not root.exists()

    with pytest.raises(MemoryRuntimeDisabledError):
        runtime.list_candidates()
    assert not root.exists()


def test_enabled_runtime_requires_isolated_activation() -> None:
    with pytest.raises(MemoryContractError):
        MemoryActivation(enabled=True, isolated_runtime=False)


def test_enabled_runtime_uses_injected_root_only(tmp_path: Path) -> None:
    root = tmp_path / "custom-memory-root"
    runtime = GovernedMemoryRuntime(root=root, activation=_activation())

    assert runtime.root == root.resolve()
    assert (runtime.root / "candidates").is_dir()
    assert (runtime.root / "reviews").is_dir()


def test_candidate_roundtrip_and_deterministic_idempotent_write(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    first = _candidate(runtime)
    second = _candidate(runtime)

    assert first == second
    assert runtime.read_candidate(first.memory_id) == first
    assert runtime.list_candidates() == (first,)

    path = runtime.root / "candidates" / f"{first.memory_id.value}.json"
    assert path.is_file()
    assert path.stat().st_mode & 0o777 == 0o600


def test_candidate_filters_are_scope_and_class_bounded(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    alpha = _candidate(runtime)
    beta = runtime.propose_candidate(
        memory_class=MemoryClass.EPISODIC,
        scope_token="project:beta",
        summary="A sanitized task outcome is proposed for later memory review.",
        provenance=_provenance("task:stage10:beta"),
        tags=("episodic",),
    )

    assert runtime.list_candidates(scope_token="project:alpha") == (alpha,)
    assert runtime.list_candidates(scope_token="project:beta") == (beta,)
    assert runtime.list_candidates(memory_class=MemoryClass.PROJECT) == (alpha,)
    assert runtime.list_candidates(memory_class=MemoryClass.EPISODIC) == (beta,)


def test_review_receipts_are_append_only_and_candidate_only(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)

    first = runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SANITIZED_CONTENT",),
    )
    second = runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.REJECT_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SUPERSEDED_CANDIDATE",),
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert runtime.list_reviews(candidate.memory_id) == (first, second)
    assert runtime.latest_review(candidate.memory_id) == second

    review_dir = runtime.root / "reviews" / candidate.memory_id.value
    assert (review_dir / "000001.json").is_file()
    assert (review_dir / "000002.json").is_file()


def test_retained_candidates_follow_latest_review_without_becoming_truth(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)

    runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SANITIZED_CONTENT",),
    )
    retained = runtime.list_retained_candidates(scope_token="project:alpha")

    assert retained == (candidate,)
    assert retained[0].governance_policy == STAGE10_MEMORY_POLICY
    assert retained[0].governance_policy.knowledge_authority is False
    assert retained[0].governance_policy.citation_eligible is False
    assert retained[0].governance_policy.answer_context_enabled is False
    assert retained[0].governance_policy.can_override_cited_knowledge is False

    runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.REJECT_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SUPERSEDED_CANDIDATE",),
    )
    assert runtime.list_retained_candidates(scope_token="project:alpha") == ()


def test_root_symlink_is_rejected(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(UnsafeMemoryStorePathError):
        GovernedMemoryRuntime(root=link, activation=_activation())


def test_candidate_directory_symlink_replacement_is_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate_dir = runtime.root / "candidates"
    outside = tmp_path / "outside"
    outside.mkdir()
    candidate_dir.rmdir()
    candidate_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafeMemoryStorePathError):
        runtime.list_candidates()


def test_candidate_file_symlink_is_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    path = runtime.root / "candidates" / f"{candidate.memory_id.value}.json"
    outside = tmp_path / "outside.json"
    outside.write_text(path.read_text())
    path.unlink()
    path.symlink_to(outside)

    with pytest.raises(UnsafeMemoryStorePathError):
        runtime.read_candidate(candidate.memory_id)


def test_record_checksum_tamper_is_rejected(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    path = runtime.root / "candidates" / f"{candidate.memory_id.value}.json"
    envelope = json.loads(path.read_text())
    envelope["record_sha256"] = "0" * 64
    path.write_text(json.dumps(envelope))

    with pytest.raises(MemoryIntegrityError, match="checksum"):
        runtime.read_candidate(candidate.memory_id)


def test_payload_tamper_with_recomputed_checksum_still_fails_canonical_id(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    path = runtime.root / "candidates" / f"{candidate.memory_id.value}.json"
    envelope = json.loads(path.read_text())
    payload = envelope["payload"]
    payload["summary"] = "Tampered but still sanitized candidate summary."
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    envelope["record_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(
            envelope,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    with pytest.raises(MemoryIntegrityError):
        runtime.read_candidate(candidate.memory_id)


def test_authority_tamper_is_rejected_even_with_recomputed_checksum(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    path = runtime.root / "candidates" / f"{candidate.memory_id.value}.json"
    envelope = json.loads(path.read_text())
    payload = envelope["payload"]
    payload["authority"]["knowledge_authority"] = True
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    envelope["record_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(
            envelope,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    with pytest.raises(MemoryIntegrityError, match="authority"):
        runtime.read_candidate(candidate.memory_id)


def test_unexpected_candidate_store_entry_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    (runtime.root / "candidates" / "unexpected.txt").write_text("x")

    with pytest.raises(MemoryIntegrityError, match="unexpected"):
        runtime.list_candidates()


def test_review_sequence_gap_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    receipt = runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SANITIZED_CONTENT",),
    )
    review_dir = runtime.root / "reviews" / candidate.memory_id.value
    first = review_dir / "000001.json"
    second = review_dir / "000002.json"
    first.rename(second)

    with pytest.raises(MemoryIntegrityError, match="contiguous"):
        runtime.list_reviews(candidate.memory_id)

    assert receipt.sequence == 1


def test_review_authority_tamper_fails_closed(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    candidate = _candidate(runtime)
    runtime.record_review(
        memory_id=candidate.memory_id,
        decision=MemoryReviewDecision.RETAIN_CANDIDATE,
        reviewer_token="reviewer:stage10",
        reason_codes=("SANITIZED_CONTENT",),
    )
    path = runtime.root / "reviews" / candidate.memory_id.value / "000001.json"
    envelope = json.loads(path.read_text())
    payload = envelope["payload"]
    payload["authority"]["can_promote_to_knowledge"] = True
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    envelope["record_sha256"] = hashlib.sha256(canonical).hexdigest()
    path.write_text(
        json.dumps(
            envelope,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )

    with pytest.raises(MemoryIntegrityError, match="authority"):
        runtime.list_reviews(candidate.memory_id)


def test_runtime_surface_has_no_promotion_evidence_context_or_execution_authority(
    tmp_path: Path,
) -> None:
    runtime = _runtime(tmp_path)

    for name in (
        "promote",
        "promote_to_knowledge",
        "publish",
        "to_evidence",
        "bind_citation",
        "compile_context",
        "inject_context",
        "execute",
        "invoke",
        "run_skill",
        "start_server",
        "write_r2",
        "write_qdrant",
        "write_sqlite",
        "release",
        "rollback",
    ):
        assert not hasattr(runtime, name)


def test_memory_modules_have_no_workspace_mcp_skill_or_backend_import_dependency() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
    files = (
        root / "m27_memory_contracts.py",
        root / "m27_memory_runtime.py",
    )

    imported_modules: set[str] = set()
    for file in files:
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_modules.add(node.module)

    forbidden_fragments = (
        "m27_workspace",
        "m27_mcp",
        "m27_skill",
        "m27_context_evidence",
        "m27_context_runtime",
        "qdrant",
        "r2",
        "sqlite",
        "production_promotion",
    )
    assert all(
        fragment not in module
        for module in imported_modules
        for fragment in forbidden_fragments
    )


def test_memory_runtime_is_not_wired_into_existing_m27_modules() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "knowledge_engine"
    allowed_memory_modules = {
        "m27_memory_activation.py",
        "m27_memory_contracts.py",
        "m27_memory_runtime.py",
    }
    existing = tuple(
        path
        for path in root.glob("m27_*.py")
        if path.name not in allowed_memory_modules
    )

    for path in existing:
        text = path.read_text(encoding="utf-8")
        assert "m27_memory_contracts" not in text
        assert "m27_memory_runtime" not in text
