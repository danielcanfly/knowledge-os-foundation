"""G01 independent nonprod QA: real owner-source bytes, fail-closed publication.

This is NOT wired to Product/Q34, does not claim signed source rights, and has no
live Gateway/MiniMax transport. A separate testing harness may supply FAKE
frames; those receipts MUST be labelled synthetic. No provider self-attestation
or synthetic model delta can create a live admission.
"""
from __future__ import annotations
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time

import m27_task_contracts_v1 as tc

ABI = "m27.g01.qa-independent/v1"
OWNER_SOURCE_SHA = "137009ea0618710222bef118c3ca258dfe98b5f8911e8dc588ac154dd4d17fb9"
SPANS = {
    "cache_initial_mode": (6582, 6635, "Initial semantic answer cache remains OFF in Nonprod."),
    "macbook_first_tool": (5145, 5212, "All new engineering uses Remote Desktop Commander first on MacBook."),
}
OBLIGATIONS = tuple(SPANS)
RETRYABLE = frozenset(("TIMEOUT", "UNAVAILABLE", "UPSTREAM_5XX", "QUOTA", "CIRCUIT_OPEN"))
HARD_DENY = frozenset(("AUTH", "ACL", "REVOKED", "RIGHTS", "VERIFIER",
                       "OBLIGATION", "PRIVACY", "CANCELLED", "UNKNOWN"))
SOURCE_SUFFIX = "01_DISPATCH/REPLAN_B0_20261017/B0-00_SHARED_RULES_20261017.md"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class SafeStop(ValueError):
    pass


def check(ok: bool, code: str) -> None:
    if not ok:
        raise SafeStop(code)


def task_contract(*, tenant: str = "owner-nonprod", principal: str = "owner-qa",
                  when: dt.datetime | None = None) -> dict:
    now = when or dt.datetime.now(dt.timezone.utc)
    ts = lambda v: v.isoformat(timespec="seconds").replace("+00:00", "Z")
    return tc.task_contract({
        "schema_version": tc.VERSION, "task_id": "g01-owner-rules-qa", "task_version": 1,
        "tenant_id": tenant,
        "actor": {"principal_id": principal, "principal_type": "human",
                  "delegated_by": None, "auth_context_ref": "G01-OWNER-LOCAL-NONPROD-ONLY",
                  "auth_expires_at": ts(now + dt.timedelta(minutes=15))},
        "authority": {"policy_ref": "g01/owner-nonprod",
                      "policy_version": OWNER_SOURCE_SHA,
                      "allowed_capability_ids": ["qa:read-only"],
                      "max_side_effect": "read", "approval_policy_ref": "owner-local-not-product"},
        "workload_kind": "qa",
        "goal": {"text": "What is the initial Nonprod cache mode, and which Mac tool is first?",
                 "language": "en"},
        "constraints": ["Two distinct material claims", "Exact citations", "No cache replay",
                        "No action", "Source revoke aborts", "Preterminal independent ACK"],
        "deadline_at": ts(now + dt.timedelta(minutes=2)),
        "context_scopes": [{"provider_kind": "workspace", "scope_id": "B0-owner-rules",
                            "access": "read"}],
        "output_specs": [{"outcome_id": "answer", "kind": "answer",
                          "artifact_media_type": "text/plain",
                          "expected_uri_scope": "nonprod/g01/qa",
                          "validator_refs": ["g01-independent-os-verifier"],
                          "required": True}],
        "definition_of_done": {"predicate_refs": list(OBLIGATIONS),
                               "mode": "all", "independent_verification_required": True},
        "budget": {"max_tokens": 320, "max_wall_ms": 120000,
                   "max_cost_microunits": 100000, "currency": "USD",
                   "max_tool_calls": 0, "max_attempts": 2},
        "privacy": {"classification": "internal", "residency": None,
                    "retention_ttl_seconds": 86400, "allow_memory_promotion": False,
                    "consent_ref": None},
        "created_at": ts(now),
        "metadata": {"g01:acl_epoch": "local-owner-policy-20261017",
                     "g01:source_id": "B0-OWNER-RULES"},
    }, now=now)


class OwnerSource:
    """Real bytes/sha/citation verification; NOT an IdP, signer, or Product rights grant."""
    def __init__(self, path: str, *, tenant: str = "owner-nonprod", principal: str = "owner-qa"):
        self.path, self.tenant, self.principal = Path(path), tenant, principal
        self.revoked = False
        self.version = OWNER_SOURCE_SHA
        self.acl_epoch = "local-owner-policy-20261017"

    def check(self, task: dict) -> bytes:
        check(not self.revoked, "SOURCE_REVOKED")
        check(task["tenant_id"] == self.tenant
              and task["actor"]["principal_id"] == self.principal, "CROSS_TENANT_OR_PRINCIPAL")
        check(task["authority"]["policy_version"] == self.version, "SOURCE_VERSION_MISMATCH")
        check(task.get("metadata", {}).get("g01:acl_epoch") == self.acl_epoch and
              task.get("metadata", {}).get("g01:source_id") == "B0-OWNER-RULES",
              "ACL_EPOCH_OR_SOURCE_ID_DENIED")
        check(self.path.is_file(), "SOURCE_NOT_FOUND")
        raw = self.path.read_bytes()
        check(sha(raw) == OWNER_SOURCE_SHA, "SOURCE_SHA_MISMATCH")
        for start, end, expected in SPANS.values():
            check(raw[start:end] == expected.encode("utf-8"), "CITATION_SPAN_MISMATCH")
        return raw


class Journal:
    """Crash-safe append-only provenance. Recovery never silently republishes."""
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def append(self, event: dict):
        with self.lock, self.path.open("ab") as fp:
            fp.write(json.dumps(event, sort_keys=True, ensure_ascii=True).encode() + b"\n")
            fp.flush()
            os.fsync(fp.fileno())

    def recover(self):
        if not self.path.exists():
            return "EMPTY"
        try:
            rows = [json.loads(line) for line in self.path.read_bytes().splitlines()]
        except (json.JSONDecodeError, UnicodeDecodeError):
            # A torn append following OS SIGKILL must never authorize replay.
            return "INCOMPLETE_TORN_JOURNAL_NO_REPLAY"
        if not rows:
            return "EMPTY"
        if rows[-1]["kind"] == "terminal":
            return rows[-1]["status"]
        # No completed terminal/fully acknowledged outcome: no publish on restart.
        self.append({"kind": "recovery", "status": "INCOMPLETE_NO_REPLAY",
                     "timestamp_ns": time.monotonic_ns()})
        return "INCOMPLETE_NO_REPLAY"


def decide_provider(*, primary_provenance: bool, first_failure: str | None,
                    fallback_consent: bool, published_claims: int) -> str:
    # Do not equate direct Workers AI with Owner's custom Cloudflare Worker Gateway.
    if not primary_provenance:
        return "PRIMARY_LIVE_HOLD"
    if first_failure is None:
        return "cloudflare_custom_worker_gateway"
    if (first_failure in RETRYABLE and fallback_consent and published_claims == 0):
        return "minimax"
    return "NO_FALLBACK"


class IndependentVerifier:
    """OS process isolation of narrowly grounded semantic entailment. No signed issuer."""
    def __init__(self, executable: str, script: str):
        self.executable = executable
        self.script = script

    def verify(self, *, source: OwnerSource, task: dict, obligation: str,
               answer: str, citation: dict) -> dict:
        req = {"source_path": str(source.path), "source_sha256": source.version,
               "tenant": task["tenant_id"], "principal": task["actor"]["principal_id"],
               "obligation": obligation, "answer": answer, "citation": citation}
        run = subprocess.run([self.executable, self.script], input=json.dumps(req),
                             capture_output=True, text=True, timeout=5, check=False)
        check(run.returncode == 0, "VERIFIER_PROCESS_DENIED")
        response = json.loads(run.stdout)
        check(response.get("accepted") is True, "UNSUPPORTED_CLAIM")
        check(response.get("source_sha256") == OWNER_SOURCE_SHA,
              "VERIFIER_SOURCE_MISMATCH")
        return response


class Session:
    """One bounded request. Only synthetic tests can use synthetic=True.

    A real Product admission requires an external licensed source/rights issuer,
    actual provider delta attestation and actual independent Client auth. None
    can be supplied by setting a client-side boolean here.
    """
    def __init__(self, *, task: dict, source: OwnerSource, journal: Journal,
                 verifier: IndependentVerifier, synthetic: bool = False,
                 external_signed_grant: object | None = None):
        tc.task_contract(task)
        # An unauthenticated local dict is not a valid independent signing issuer.
        # Reject rather than silently treating caller-supplied 'grant' as authority.
        check(external_signed_grant is None, "UNVERIFIABLE_EXTERNAL_SIGNED_GRANT")
        self.task, self.source, self.journal, self.verifier = (
            copy.deepcopy(task), source, journal, verifier)
        self.synthetic = synthetic
        self.external_signed_grant = None
        self.nonce = secrets.token_hex(24)
        self.challenge = sha((self.nonce + tc.sha256(task)).encode())
        self.claims = {}
        self.acks = set()
        self.closed = False
        self.cancelled = False
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.cv = threading.Condition(self.lock)
        self.journal.append({"kind": "started", "task_sha256": tc.sha256(task),
                             "source_sha256": OWNER_SOURCE_SHA,
                             "synthetic": self.synthetic, "timestamp_ns": time.monotonic_ns()})

    def preflight(self):
        self.source.check(self.task)
        check(not self.cancelled and not self.closed, "CANCELLED")
        check(time.monotonic() - self.started < 120
              and dt.datetime.now(dt.timezone.utc) < tc.timestamp(self.task["deadline_at"]),
              "DEADLINE")
        check(self.synthetic, "NO_ATTESTED_CUSTOM_GATEWAY_AND_SIGNED_PRODUCT_SOURCE")
        # Only tests can pass synthetic=True. Never call this real provider evidence.
        return "SYNTHETIC_FIXTURE_ONLY"

    def emit(self, obligation: str, text: str, citation: dict, *, provider: str = "fixture"):
        self.preflight()
        check(provider == "fixture" and self.synthetic, "PROVIDER_NOT_ATTESTED")
        check(obligation in OBLIGATIONS and obligation not in self.claims,
              "UNKNOWN_OR_DUPLICATE_OBLIGATION")
        check(isinstance(text, str) and 0 < len(text) <= 512, "NO_SUBSTANTIVE_TEXT")
        proof = self.verifier.verify(source=self.source, task=self.task, obligation=obligation,
                                     answer=text, citation=citation)
        self.preflight()  # changed/withdrawn source between verification and publication
        with self.cv:
            # Cancellation and rights can change between verifier return and lock entry.
            self.preflight()
            check(obligation not in self.claims, "UNKNOWN_OR_DUPLICATE_OBLIGATION")
            text_sha256 = sha(text.encode())
            proof_sha256 = sha(json.dumps(proof, sort_keys=True).encode())
            claim_nonce = secrets.token_hex(24)
            claim_challenge = sha((self.challenge + ":" + obligation + ":" +
                                   text_sha256 + ":" + claim_nonce).encode())
            self.claims[obligation] = {
                "text_sha256": text_sha256, "proof_sha256": proof_sha256,
                "citation": copy.deepcopy(citation), "challenge": claim_challenge,
            }
            self.journal.append({"kind": "claim_sent_fixture", "obligation": obligation,
                                 "text_sha256": text_sha256,
                                 "timestamp_ns": time.monotonic_ns()})
            return {"kind": "answer_text", "synthetic": True, "obligation": obligation,
                    "text": text, "text_sha256": text_sha256,
                    "citation": copy.deepcopy(citation), "challenge": claim_challenge}

    def ack(self, *, obligation: str, challenge: str, text_sha256: str) -> bool:
        with self.cv:
            valid = (not self.closed and not self.cancelled and
                     obligation in self.claims and obligation not in self.acks
                     and type(challenge) is str and type(text_sha256) is str
                     and secrets.compare_digest(self.claims[obligation]["challenge"],
                                                challenge)
                     and secrets.compare_digest(self.claims[obligation]["text_sha256"],
                                                text_sha256))
            if not valid:
                return False
            try:
                self.source.check(self.task)
            except (SafeStop, OSError):
                return False
            self.acks.add(obligation)
            self.journal.append({"kind": "ack_fixture", "obligation": obligation,
                                 "timestamp_ns": time.monotonic_ns()})
            self.cv.notify_all()
            return True

    def await_ack(self, obligation: str, timeout: float = 1):
        with self.cv:
            return self.cv.wait_for(lambda: obligation in self.acks or
                                    self.cancelled or self.closed, timeout=timeout) and (
                                    obligation in self.acks)

    def terminal(self, *, done: bool, reason: str = "") -> dict:
        with self.cv:
            check(not self.closed, "DUPLICATE_TERMINAL")
            try:
                self.source.check(self.task)
                source_current = True
            except (SafeStop, OSError) as exc:
                source_current = False
                reason = str(exc) if isinstance(exc, SafeStop) else "SOURCE_IO_FAILURE"
            full = (set(self.claims) == set(OBLIGATIONS) and
                    self.acks == set(OBLIGATIONS))
            answered = done and full and source_current and not self.cancelled
            status = ("SYNTHETIC_COMPLETE_NOT_PRODUCT" if answered else
                      ("PARTIAL_TERMINATED" if self.claims else "SAFE_ABSTENTION"))
            self.closed = True
            self.journal.append({"kind": "terminal", "status": status,
                                 "reason": reason or ("" if answered else "OBLIGATIONS_INCOMPLETE"),
                                 "claims": list(self.claims), "acks": list(self.acks),
                                 "timestamp_ns": time.monotonic_ns()})
            self.cv.notify_all()
            return {"kind": "terminal", "status": status,
                    "synthetic": True, "reason": reason,
                    "answered_product": False, "obligations_verified": bool(full and source_current)}

    def cancel(self):
        with self.cv:
            self.cancelled = True
            self.cv.notify_all()
