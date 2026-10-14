"""A09: Nonprod-only, fail-closed X01-X09 technical conformance adapter.

This is a consumer-side oracle, not an issuer, IdP, effect executor, legal controller,
official grader, or external signature verifier. D28 remains feature-default-OFF.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from knowledge_engine import m27_d28_dual_envelope_v1_experimental as d28


class Denied(ValueError):
    pass


def demand(ok: bool, code: str) -> None:
    if not ok:
        raise Denied(code)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


@dataclass(frozen=True)
class IdentityScope:
    tenant_id: str
    subject: str
    audience: str
    scope: str
    consent_generation: int
    issuer: str


def x01_reader(wire: bytes, raw_legacy: bytes, sidecars: Mapping[str, bytes],
               supported: Mapping[str, set[str]], *, old_reader: bool = False) -> dict:
    """Never directly feed wire to the legacy native reader."""
    envelope = d28.negotiate_reader(
        wire, supported=supported, understood_sidecars=set(sidecars),
        raw_legacy=raw_legacy, old_native_reader=old_reader
    )
    demand(envelope["record_type"] == "legacy-bound", "X01_NOT_LEGACY")
    for claim in envelope["required_sidecars"]:
        data = sidecars.get(claim["namespace"])
        demand(type(data) is bytes and sha(data) == claim["body_sha256"],
               "X01_SIDECAR_BODY_MISMATCH")
    return envelope


def x02_authority(sidecar: bytes, verify: Callable[[bytes], IdentityScope | None],
                  *, tenant: str, subject: str, audience: str, scope: str,
                  minimum_generation: int, revoked_generation: int) -> IdentityScope:
    """Verifier must be injected from an independently controlled trust boundary.

    Self-attested sidecar booleans, test keys and 'valid' flags are not accepted.
    """
    demand(callable(verify), "X02_NO_EXTERNAL_VERIFIER")
    identity = verify(sidecar)
    demand(isinstance(identity, IdentityScope), "X02_UNVERIFIED_IDENTITY")
    demand(bool(identity.issuer) and identity.issuer != "self-test",
           "X02_UNQUALIFIED_ISSUER")
    demand((identity.tenant_id, identity.subject, identity.audience, identity.scope)
           == (tenant, subject, audience, scope), "X02_SCOPE_MISMATCH")
    demand(type(identity.consent_generation) is int
           and identity.consent_generation >= minimum_generation
           and identity.consent_generation > revoked_generation, "X02_REVOKED_CONSENT")
    return identity


def x03_permit(permit: dict, action: bytes, identity: IdentityScope, now: int) -> str:
    demand(type(permit) is dict and set(permit) == {
        "permit_id", "action_sha256", "tenant_id", "subject", "scope", "expires_at",
        "human_approval"}, "X03_PERMIT_FIELDS")
    demand(type(permit["permit_id"]) is str and bool(permit["permit_id"]),
           "X03_PERMIT_ID")
    demand(permit["human_approval"] is True, "X03_HUMAN_DENIED")
    demand(permit["action_sha256"] == sha(action), "X03_ACTION_MISMATCH")
    demand((permit["tenant_id"], permit["subject"], permit["scope"])
           == (identity.tenant_id, identity.subject, identity.scope),
           "X03_PERMIT_SCOPE")
    demand(type(permit["expires_at"]) is int and now < permit["expires_at"],
           "X03_EXPIRED")
    return permit["permit_id"]


class NonprodCAS:
    """SQLite durable local outbox: exactly-once *reservation*, not exactly-once external effect."""
    def __init__(self, path: str):
        self.db = sqlite3.connect(path, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox("
                        "permit_id TEXT PRIMARY KEY, action_hash TEXT UNIQUE NOT NULL,"
                        " status TEXT NOT NULL CHECK(status IN ('RESERVED','UNKNOWN','DONE')))")
    def reserve(self, permit_id: str, action: bytes) -> None:
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("INSERT INTO outbox VALUES (?,?,'RESERVED')",
                            (permit_id, sha(action)))
            self.db.execute("COMMIT")
        except sqlite3.IntegrityError as exc:
            self.db.execute("ROLLBACK")
            raise Denied("X04_CAS_DUPLICATE_OR_UNKNOWN") from exc
        except Exception:
            self.db.execute("ROLLBACK")
            raise
    def mark(self, permit_id: str, result: str) -> None:
        demand(result in ("UNKNOWN", "DONE"), "X04_BAD_OUTCOME")
        cur = self.db.execute("UPDATE outbox SET status=? "
                              "WHERE permit_id=? AND status='RESERVED'",
                              (result, permit_id))
        demand(cur.rowcount == 1, "X04_STATUS_NOT_RESERVABLE")
    def close(self):
        self.db.close()


def x05_notice(notice_wire: bytes, *, immutable_terminal_hash: str,
               expected_prev_hash: str, expected_seq: int,
               authenticated_client_cursor: int) -> dict:
    notice = d28.validate_wire(notice_wire)
    demand(notice["new_record_kind"] == "postterminal", "X05_NOT_NOTICE")
    body = notice["body"]
    demand(body["original_terminal_head_hash"] == immutable_terminal_hash,
           "X05_TERMINAL_REWRITTEN")
    demand(body["notice_prev_hash"] == expected_prev_hash
           and body["notice_seq"] == expected_seq, "X05_CHAIN_BROKEN")
    demand(body["client_cursor"] == authenticated_client_cursor,
           "X05_UNACKED_CLIENT_CURSOR")
    return notice


def x06_revocation(wire: bytes, *, previous_generation: int, rights_epoch: int,
                   restore_quarantined: bool, acknowledged_controllers: set[str],
                   required_controllers: set[str]) -> int:
    rev = d28.validate_wire(wire)
    demand(rev["new_record_kind"] == "revocation", "X06_NOT_REVOCATION")
    g = rev["body"]["exclusion_generation"]
    demand(g > previous_generation and g > rights_epoch, "X06_NONMONOTONIC")
    demand(restore_quarantined, "X06_UNQUARANTINED_RESTORE")
    demand(required_controllers and required_controllers.issubset(acknowledged_controllers),
           "X06_MISSING_DELETE_ACK")
    return g


def x07_billing(wire: bytes, *, ledger_usage: int, invoice: dict | None,
                owner_aggregate: int) -> dict:
    bill = d28.validate_wire(wire)
    demand(bill["new_record_kind"] == "billing", "X07_NOT_BILLING")
    demand(type(ledger_usage) is int and ledger_usage >= 0
           and type(owner_aggregate) is int and owner_aggregate >= ledger_usage,
           "X07_LEDGER_INVALID")
    status = bill["body"]["billing_status"]
    if invoice is None:
        demand(status == "UNKNOWN", "X07_MISSING_INVOICE_NOT_UNKNOWN")
        return {"ledger_usage": ledger_usage, "invoice_amount": None,
                "invoice_verified": False, "owner_aggregate": owner_aggregate}
    demand(status == "FINAL" and invoice.get("source") == "trusted_finance_controller"
           and type(invoice.get("amount")) is int and invoice["amount"] >= 0,
           "X07_UNTRUSTED_INVOICE")
    return {"ledger_usage": ledger_usage, "invoice_amount": invoice["amount"],
            "invoice_verified": True, "owner_aggregate": owner_aggregate}


def x08_independent_verification(proof: dict, *, executor_id: str,
                                 required_sources: set[str]) -> None:
    demand(type(proof) is dict and set(proof) == {
        "verifier_id", "algorithm", "accepted", "source_ids"}, "X08_PROOF_FIELDS")
    demand(proof["verifier_id"] != executor_id
           and type(proof["verifier_id"]) is str and proof["verifier_id"],
           "X08_SELF_VERIFICATION")
    demand(proof["algorithm"] == "sha256-cited-spans-v1",
           "X08_UNSUPPORTED_VERIFIER")
    demand(proof["accepted"] is True and type(proof["source_ids"]) is list
           and required_sources and required_sources.issubset(set(proof["source_ids"])),
           "X08_UNSUPPORTED_CLAIM")


def x09_evidence(events: list[dict], *, source_manifest: Mapping[str, str]) -> None:
    demand(type(events) is list and len(events) >= 2, "X09_NO_NATIVE_GENERATION")
    seen_generated = False
    reached_terminal = False
    for event in events:
        demand(set(event) == {"type", "text", "source_id", "source_sha256", "span"},
               "X09_EVENT_FIELDS")
        kind = event["type"]
        demand(kind in ("generated", "terminal", "progress"), "X09_UNKNOWN_EVENT")
        demand(not reached_terminal, "X09_POSTTERMINAL_MUTATION")
        if kind == "generated":
            sid = event["source_id"]
            demand(type(event["text"]) is str and event["text"].strip()
                   and sid in source_manifest and source_manifest[sid] == event["source_sha256"]
                   and type(event["span"]) is list and len(event["span"]) == 2
                   and all(type(n) is int and n >= 0 for n in event["span"])
                   and event["span"][1] > event["span"][0],
                   "X09_UNGROUNDED_GENERATED_TEXT")
            seen_generated = True
        elif kind == "terminal":
            demand(seen_generated, "X09_ONLY_PROGRESS_BEFORE_TERMINAL")
            reached_terminal = True
    demand(reached_terminal, "X09_NO_TERMINAL")
