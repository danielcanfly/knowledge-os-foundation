from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .m27_memory_contracts import (
    MEMORY_SCHEMA_VERSION,
    STAGE10_MEMORY_POLICY,
    MemoryActivation,
    MemoryCandidate,
    MemoryCandidateId,
    MemoryClass,
    MemoryContractError,
    MemoryOriginKind,
    MemoryProvenance,
    MemoryReviewDecision,
    MemoryReviewReceipt,
)

_CANDIDATE_DIR = "candidates"
_REVIEW_DIR = "reviews"
_RECORD_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_REVIEW_FILENAME_RE = re.compile(r"^(?P<sequence>[0-9]{6})\.json$")


class MemoryRuntimeError(RuntimeError):
    """Base error for Stage 10 governed-memory runtime failures."""


class MemoryRuntimeDisabledError(MemoryRuntimeError):
    """Raised when a default-off Stage 10 runtime is asked to read or write."""


class MemoryCandidateNotFoundError(MemoryRuntimeError):
    """Raised when a candidate does not exist in the isolated memory store."""


class MemoryIntegrityError(MemoryRuntimeError):
    """Raised when persisted candidate-memory material fails integrity checks."""


class UnsafeMemoryStorePathError(MemoryRuntimeError):
    """Raised when a symlink or non-contained path is encountered."""


class GovernedMemoryRuntime:
    """Isolated, candidate-only episodic/project memory runtime.

    The runtime persists only sanitized memory candidates and immutable review
    receipts under an injected root. It has no answer-path, citation, knowledge
    promotion, MCP, workspace, skill, network, release, or production backend
    authority.
    """

    def __init__(
        self,
        *,
        root: Path,
        activation: MemoryActivation | None = None,
    ) -> None:
        if not isinstance(root, Path):
            raise MemoryRuntimeError("memory root must be pathlib.Path")
        if activation is None:
            activation = MemoryActivation()
        if not isinstance(activation, MemoryActivation):
            raise MemoryRuntimeError("activation must be MemoryActivation")
        if root.exists() and root.is_symlink():
            raise UnsafeMemoryStorePathError("memory root cannot be a symlink")

        self._root = root.resolve(strict=False)
        self._activation = activation

        if activation.enabled:
            self._initialize_store()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def activation(self) -> MemoryActivation:
        return self._activation

    def propose_candidate(
        self,
        *,
        memory_class: MemoryClass | str,
        scope_token: str,
        summary: str,
        provenance: MemoryProvenance,
        tags: tuple[str, ...] = (),
    ) -> MemoryCandidate:
        self._require_enabled()
        candidate = MemoryCandidate.create(
            memory_class=memory_class,
            scope_token=scope_token,
            summary=summary,
            provenance=provenance,
            tags=tags,
        )
        path = self._candidate_path(candidate.memory_id)
        if path.exists() or path.is_symlink():
            existing = self.read_candidate(candidate.memory_id)
            if existing != candidate:
                raise MemoryIntegrityError(
                    "existing candidate id does not match canonical candidate content"
                )
            return existing

        self._write_record_exclusive(path, candidate.as_dict())
        return candidate

    def read_candidate(self, memory_id: MemoryCandidateId) -> MemoryCandidate:
        self._require_enabled()
        self._require_memory_id(memory_id)
        path = self._candidate_path(memory_id)
        payload = self._read_record(path)
        return self._candidate_from_dict(payload, expected_memory_id=memory_id)

    def list_candidates(
        self,
        *,
        scope_token: str | None = None,
        memory_class: MemoryClass | None = None,
    ) -> tuple[MemoryCandidate, ...]:
        self._require_enabled()
        if scope_token is not None:
            from .m27_memory_contracts import validate_safe_token

            validate_safe_token("scope_token", scope_token)
        if memory_class is not None and not isinstance(memory_class, MemoryClass):
            raise MemoryContractError("memory_class filter must be MemoryClass")

        candidates = tuple(
            self.read_candidate(memory_id)
            for memory_id in self._candidate_ids()
        )
        return tuple(
            candidate
            for candidate in candidates
            if (scope_token is None or candidate.scope_token == scope_token)
            and (memory_class is None or candidate.memory_class is memory_class)
        )

    def record_review(
        self,
        *,
        memory_id: MemoryCandidateId,
        decision: MemoryReviewDecision,
        reviewer_token: str,
        reason_codes: tuple[str, ...],
    ) -> MemoryReviewReceipt:
        self._require_enabled()
        self.read_candidate(memory_id)
        if not isinstance(decision, MemoryReviewDecision):
            raise MemoryContractError("decision must be MemoryReviewDecision")

        existing = self.list_reviews(memory_id)
        receipt = MemoryReviewReceipt(
            memory_id=memory_id,
            sequence=len(existing) + 1,
            decision=decision,
            reviewer_token=reviewer_token,
            reason_codes=reason_codes,
        )
        review_dir = self._review_dir(memory_id, create=True)
        path = review_dir / f"{receipt.sequence:06d}.json"
        self._assert_contained(path)
        self._write_record_exclusive(path, receipt.as_dict())
        return receipt

    def list_reviews(
        self,
        memory_id: MemoryCandidateId,
    ) -> tuple[MemoryReviewReceipt, ...]:
        self._require_enabled()
        self._require_memory_id(memory_id)
        self.read_candidate(memory_id)

        review_dir = self._review_dir(memory_id, create=False)
        if not review_dir.exists():
            return ()
        if review_dir.is_symlink() or not review_dir.is_dir():
            raise UnsafeMemoryStorePathError("memory review directory is unsafe")

        receipts: list[MemoryReviewReceipt] = []
        for entry in sorted(review_dir.iterdir(), key=lambda item: item.name):
            if entry.is_symlink():
                raise UnsafeMemoryStorePathError("memory review entry cannot be a symlink")
            if not entry.is_file():
                raise MemoryIntegrityError("unexpected non-file in memory review directory")
            match = _REVIEW_FILENAME_RE.fullmatch(entry.name)
            if match is None:
                raise MemoryIntegrityError("unexpected memory review filename")
            sequence = int(match.group("sequence"))
            expected_sequence = len(receipts) + 1
            if sequence != expected_sequence:
                raise MemoryIntegrityError("memory review sequence is not contiguous")
            payload = self._read_record(entry)
            receipt = self._review_from_dict(
                payload,
                expected_memory_id=memory_id,
                expected_sequence=sequence,
            )
            receipts.append(receipt)
        return tuple(receipts)

    def latest_review(
        self,
        memory_id: MemoryCandidateId,
    ) -> MemoryReviewReceipt | None:
        reviews = self.list_reviews(memory_id)
        return reviews[-1] if reviews else None

    def list_retained_candidates(
        self,
        *,
        scope_token: str | None = None,
        memory_class: MemoryClass | None = None,
    ) -> tuple[MemoryCandidate, ...]:
        """Return reviewed candidates without granting knowledge/evidence authority."""

        candidates = self.list_candidates(
            scope_token=scope_token,
            memory_class=memory_class,
        )
        retained: list[MemoryCandidate] = []
        for candidate in candidates:
            review = self.latest_review(candidate.memory_id)
            if (
                review is not None
                and review.decision is MemoryReviewDecision.RETAIN_CANDIDATE
            ):
                retained.append(candidate)
        return tuple(retained)

    def _initialize_store(self) -> None:
        if self._root.exists() and self._root.is_symlink():
            raise UnsafeMemoryStorePathError("memory root cannot be a symlink")
        self._root.mkdir(parents=True, exist_ok=True)
        if not self._root.is_dir():
            raise MemoryRuntimeError("memory root must be a directory")
        self._assert_contained(self._root)

        for dirname in (_CANDIDATE_DIR, _REVIEW_DIR):
            path = self._root / dirname
            if path.exists() and path.is_symlink():
                raise UnsafeMemoryStorePathError(
                    f"memory {dirname} directory cannot be a symlink"
                )
            path.mkdir(mode=0o700, exist_ok=True)
            if not path.is_dir():
                raise MemoryRuntimeError(f"memory {dirname} path must be a directory")
            self._assert_contained(path)

    def _candidate_ids(self) -> tuple[MemoryCandidateId, ...]:
        candidate_dir = self._root / _CANDIDATE_DIR
        self._require_internal_dir(candidate_dir, label="candidate")
        ids: list[MemoryCandidateId] = []
        for entry in sorted(candidate_dir.iterdir(), key=lambda item: item.name):
            if entry.is_symlink():
                raise UnsafeMemoryStorePathError("memory candidate entry cannot be a symlink")
            if not entry.is_file() or entry.suffix != ".json":
                raise MemoryIntegrityError("unexpected memory candidate store entry")
            try:
                memory_id = MemoryCandidateId(entry.stem)
            except MemoryContractError as exc:
                raise MemoryIntegrityError("unexpected memory candidate filename") from exc
            ids.append(memory_id)
        return tuple(ids)

    def _candidate_path(self, memory_id: MemoryCandidateId) -> Path:
        self._require_memory_id(memory_id)
        candidate_dir = self._root / _CANDIDATE_DIR
        self._require_internal_dir(candidate_dir, label="candidate")
        path = candidate_dir / f"{memory_id.value}.json"
        self._assert_contained(path)
        if path.is_symlink():
            raise UnsafeMemoryStorePathError("memory candidate file cannot be a symlink")
        return path

    def _review_dir(
        self,
        memory_id: MemoryCandidateId,
        *,
        create: bool,
    ) -> Path:
        self._require_memory_id(memory_id)
        parent = self._root / _REVIEW_DIR
        self._require_internal_dir(parent, label="review")
        path = parent / memory_id.value
        self._assert_contained(path)
        if path.exists() and path.is_symlink():
            raise UnsafeMemoryStorePathError("memory review directory cannot be a symlink")
        if create:
            path.mkdir(mode=0o700, exist_ok=True)
        return path

    def _require_internal_dir(self, path: Path, *, label: str) -> None:
        self._assert_contained(path)
        if path.is_symlink():
            raise UnsafeMemoryStorePathError(
                f"memory {label} directory cannot be a symlink"
            )
        if not path.exists() or not path.is_dir():
            raise MemoryIntegrityError(f"memory {label} directory is missing")

    def _write_record_exclusive(self, path: Path, payload: dict[str, object]) -> None:
        self._assert_contained(path)
        if path.is_symlink():
            raise UnsafeMemoryStorePathError("memory record cannot be a symlink")

        canonical_payload = self._canonical_json(payload)
        envelope = {
            "record_sha256": hashlib.sha256(canonical_payload).hexdigest(),
            "payload": payload,
        }
        encoded = self._canonical_json(envelope)

        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(path, flags, 0o600)
        except FileExistsError as exc:
            raise MemoryIntegrityError("immutable memory record already exists") from exc
        except OSError as exc:
            raise MemoryRuntimeError("memory record write failed") from exc

        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())

    def _read_record(self, path: Path) -> dict[str, object]:
        self._assert_contained(path)
        if path.is_symlink():
            raise UnsafeMemoryStorePathError("memory record cannot be a symlink")
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise MemoryCandidateNotFoundError("memory candidate record not found") from exc
        except OSError as exc:
            raise MemoryIntegrityError("memory record is unreadable") from exc

        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MemoryIntegrityError("memory record is not valid UTF-8 JSON") from exc

        if not isinstance(envelope, dict) or set(envelope) != {
            "record_sha256",
            "payload",
        }:
            raise MemoryIntegrityError("memory record envelope shape mismatch")
        record_sha256 = envelope["record_sha256"]
        payload = envelope["payload"]
        if (
            not isinstance(record_sha256, str)
            or not _RECORD_SHA256_RE.fullmatch(record_sha256)
            or not isinstance(payload, dict)
        ):
            raise MemoryIntegrityError("memory record envelope is invalid")

        actual = hashlib.sha256(self._canonical_json(payload)).hexdigest()
        if actual != record_sha256:
            raise MemoryIntegrityError("memory record checksum mismatch")
        return payload

    @staticmethod
    def _canonical_json(payload: object) -> bytes:
        try:
            return json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise MemoryRuntimeError("memory record is not canonical JSON") from exc

    @staticmethod
    def _candidate_from_dict(
        payload: dict[str, object],
        *,
        expected_memory_id: MemoryCandidateId,
    ) -> MemoryCandidate:
        expected_keys = {
            "schema_version",
            "memory_id",
            "memory_class",
            "scope_token",
            "summary",
            "tags",
            "provenance",
            "governance_policy",
            "authority",
        }
        if set(payload) != expected_keys:
            raise MemoryIntegrityError("memory candidate record shape mismatch")
        if payload.get("schema_version") != MEMORY_SCHEMA_VERSION:
            raise MemoryIntegrityError("memory candidate schema version mismatch")
        if payload.get("governance_policy") != STAGE10_MEMORY_POLICY.as_dict():
            raise MemoryIntegrityError("memory candidate governance policy mismatch")
        if payload.get("authority") != {
            "status": "UNVERIFIED_MEMORY_CANDIDATE",
            "knowledge_authority": False,
            "citation_eligible": False,
            "answer_context_enabled": False,
            "can_override_cited_knowledge": False,
        }:
            raise MemoryIntegrityError("memory candidate authority boundary mismatch")

        provenance_payload = payload.get("provenance")
        tags_payload = payload.get("tags")
        if not isinstance(provenance_payload, dict) or not isinstance(tags_payload, list):
            raise MemoryIntegrityError("memory candidate nested payload is invalid")

        try:
            provenance = MemoryProvenance(
                origin_kind=MemoryOriginKind(str(provenance_payload["origin_kind"])),
                origin_ref=str(provenance_payload["origin_ref"]),
                source_sha256=provenance_payload.get("source_sha256"),
            )
            candidate = MemoryCandidate(
                memory_id=MemoryCandidateId(str(payload["memory_id"])),
                memory_class=MemoryClass(str(payload["memory_class"])),
                scope_token=str(payload["scope_token"]),
                summary=str(payload["summary"]),
                provenance=provenance,
                tags=tuple(str(tag) for tag in tags_payload),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            MemoryContractError,
        ) as exc:
            raise MemoryIntegrityError("memory candidate record failed validation") from exc

        if candidate.memory_id != expected_memory_id:
            raise MemoryIntegrityError("memory candidate id does not match requested record")
        return candidate

    @staticmethod
    def _review_from_dict(
        payload: dict[str, object],
        *,
        expected_memory_id: MemoryCandidateId,
        expected_sequence: int,
    ) -> MemoryReviewReceipt:
        if set(payload) != {
            "schema_version",
            "memory_id",
            "sequence",
            "decision",
            "reviewer_token",
            "reason_codes",
            "authority",
        }:
            raise MemoryIntegrityError("memory review record shape mismatch")
        if payload.get("schema_version") != MEMORY_SCHEMA_VERSION:
            raise MemoryIntegrityError("memory review schema version mismatch")
        if payload.get("authority") != {
            "candidate_only": True,
            "knowledge_authority": False,
            "citation_eligible": False,
            "can_promote_to_knowledge": False,
        }:
            raise MemoryIntegrityError("memory review authority boundary mismatch")

        reason_codes = payload.get("reason_codes")
        if not isinstance(reason_codes, list):
            raise MemoryIntegrityError("memory review reason_codes must be a list")

        try:
            receipt = MemoryReviewReceipt(
                memory_id=MemoryCandidateId(str(payload["memory_id"])),
                sequence=int(payload["sequence"]),
                decision=MemoryReviewDecision(str(payload["decision"])),
                reviewer_token=str(payload["reviewer_token"]),
                reason_codes=tuple(str(code) for code in reason_codes),
            )
        except (
            KeyError,
            TypeError,
            ValueError,
            MemoryContractError,
        ) as exc:
            raise MemoryIntegrityError("memory review record failed validation") from exc

        if receipt.memory_id != expected_memory_id:
            raise MemoryIntegrityError("memory review id does not match candidate")
        if receipt.sequence != expected_sequence:
            raise MemoryIntegrityError("memory review sequence mismatch")
        return receipt

    def _assert_contained(self, path: Path) -> None:
        try:
            path.resolve(strict=False).relative_to(self._root)
        except ValueError as exc:
            raise UnsafeMemoryStorePathError(
                "path escapes isolated Stage 10 memory root"
            ) from exc

    def _require_enabled(self) -> None:
        if not self._activation.enabled:
            raise MemoryRuntimeDisabledError(
                "Stage 10 governed memory is default-off and not enabled"
            )
        if not self._activation.isolated_runtime:
            raise MemoryRuntimeDisabledError(
                "Stage 10 governed memory requires an isolated runtime"
            )

    @staticmethod
    def _require_memory_id(memory_id: MemoryCandidateId) -> None:
        if not isinstance(memory_id, MemoryCandidateId):
            raise MemoryContractError("memory_id must be MemoryCandidateId")
