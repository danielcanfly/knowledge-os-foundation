"""Auditable F02 -> G01/A05 Native ABI bridge; first-party nonprod fixtures ONLY.

No Provider, Product identity, signer, Cache I/O or official benchmark access.
The producer's raw *provider wire* SHA and G01 canonical *event.data* SHA
are distinct fields; this adapter never treats either as proof of a live model.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Callable

from knowledge_engine import m27_f02_current_native_model_events as f02
from knowledge_engine import m27_g01_current_native_consumer as g01


BRIDGE_ABI = "m27.nonprod.h02-f02-g01.fixture-join/v1"
COMMON = ("task_id", "request_id", "question_sha256", "task_contract_sha256",
          "tenant", "principal", "source_release_sha256",
          "source_manifest_sha256", "source_rights_epoch",
          "source_acl_sha256", "answer_obligation_ids",
          "model_route_policy_version", "cache_mode")


class JoinDenied(ValueError):
    """No new authority or successful terminal is asserted."""


def require(value, reason):
    if not value:
        raise JoinDenied(reason)


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class NativeFixtureJoin:
    """Maps independently validated F02 normalized metadata into G01's own verifier.

    The G01 TaskContract is frozen BEFORE creating producer pins. G01 max_tokens=0
    means *no remote model may be called by G01*. F02 max_tokens>0 is a
    separately bounded synthetic wire normalization budget, NOT permission for
    real inference. Both budgets and their different meanings are committed to
    the bridge preflight instead of silently rewriting either contract.
    """

    def __init__(self, start: dict, producer: f02.NativeEventProducer,
                 deliver_event: Callable[[dict], dict], *, cancel=None):
        require(type(start) is dict and
                start.get("status") == "TASK_FROZEN_SOURCE_VERIFIED" and
                start.get("abi") == g01.ABI and
                start.get("scope") == g01.SCOPE and
                start.get("model_origin_class") == f02.SYNTHETIC and
                start.get("source_byte_verified") is True and
                start.get("product_pass") is False and
                start.get("provider_called") is False and
                start.get("semantic_issuer_qualified") is False,
                "G01_ADMISSION_OR_AUTHORITY_INVALID")
        require(type(producer) is f02.NativeEventProducer and
                producer.origin_class == f02.SYNTHETIC and
                not producer.events and not producer.started and
                not producer.done, "PRODUCER_ORIGIN_OR_REPLAY_DENIED")
        p = producer.pins
        p.validate()
        frozen = start.get("pins")
        require(type(frozen) is dict and
                set(frozen) == set(COMMON) | {"max_tokens", "deadline"} and
                frozen["max_tokens"] == 0 and
                frozen["model_route_policy_version"] == "NO_ROUTE_LOCAL_FIXTURE" and
                p.model_route_policy_version == "NO_ROUTE_LOCAL_FIXTURE" and
                p.cache_mode == frozen["cache_mode"] == "OFF" and
                p.deadline_monotonic_ns == frozen["deadline"] and
                0 < p.max_tokens <= 128,
                "EXPLICIT_DUAL_TOKEN_BUDGET_OR_DEADLINE_DENIED")
        for field in COMMON:
            a = getattr(p, field)
            actual = frozen[field]
            if field == "answer_obligation_ids":
                actual = tuple(actual)
            require(a == actual, "FROZEN_TASK_OR_SOURCE_PIN_MISMATCH:" + field)
        require(tuple(p.answer_obligation_ids) == tuple(x[0] for x in g01.OBLIGATIONS)
                and len(p.answer_obligation_ids) == 2 and
                frozen["question_sha256"] == digest(g01.QUESTION.encode()) and
                frozen["source_manifest_sha256"] == g01.h02.f03.A05_SOURCE_PIN,
                "SOURCE_OR_QUESTION_NOT_ADMITTED")
        citations = start.get("citations")
        require(type(citations) is dict and set(citations) == set(p.answer_obligation_ids),
                "MISSING_G01_A05_CITATIONS")
        require(all(type(c) is dict for c in citations.values()) and
                len({c["document_sha256"] for c in citations.values()}) == 2,
                "MATERIAL_SOURCES_NOT_DISTINCT")
        require(callable(deliver_event), "MISSING_ACTUAL_CONSUMER")
        self.start, self.producer, self.deliver = start, producer, deliver_event
        self.cancel = cancel
        self.citations = citations
        self.sid = start["session_id"]
        self.seq = 0
        self.clock = 0
        self.seen_f02 = set()
        self.raw_delta_ids = set()
        self.raw_history = []
        self.bindings = []
        self.pending_done = None
        self.proposal_index = 0
        self.finalized = False
        self.terminal_called = False
        self.aborted = False
        self.preflight_sha256 = digest(g01.canonical({
            "abi": BRIDGE_ABI, "g01_frozen_pins": frozen,
            "f02_pins": {**vars(p), "answer_obligation_ids": list(p.answer_obligation_ids)},
            "dual_token_budget_semantics": {
                "g01_max_tokens": 0, "g01_usage": "NO_PROVIDER_CALL",
                "f02_max_tokens": p.max_tokens,
                "f02_usage": "SYNTHETIC_WIRE_BOUND_NOT_LIVE_MODEL"},
            "a05_citations": citations,
        }))

    def _check_f02(self, event, raw):
        p = self.producer.pins
        require(event["abi"] == f02.ABI and
                event["model_origin_class"] == f02.SYNTHETIC and
                event["task_id"] == p.task_id and
                event["request_id"] == p.request_id and
                event["cache_mode"] == "OFF" and
                event["event_id"] not in self.seen_f02,
                "F02_EVENT_IDENTITY_OR_REPLAY")
        self.seen_f02.add(event["event_id"])
        if event["event_kind"] in {"provider_start", "model_identity_observed",
                                   "provider_delta", "provider_done"}:
            require(event["raw_event_sha256"] == digest(raw),
                    "F02_RAW_PROVIDER_SHA_MISMATCH")
        require(event["monotonic_ns"] > 0, "INVALID_PRODUCER_CLOCK")
        self.raw_history.append({
            "f02_event_id": event["event_id"], "f02_kind": event["event_kind"],
            "f02_normalized_sha256": digest(f02.canonical(event)),
            "original_provider_raw_sha256": digest(raw),
            "mapped": event["event_kind"] not in {"model_identity_observed", "stream_end"},
        })

    def _emit(self, event, data):
        require(not self.aborted and not self.finalized, "JOIN_CLOSED")
        require(type(data) is dict, "INVALID_G01_DATA")
        self.seq += 1
        self.clock = max(time.monotonic_ns(), self.clock + 1,
                         event["monotonic_ns"])
        converted = {
            "event_id": "h02-join-" + event["event_id"],
            "task_id": self.producer.pins.task_id,
            "request_id": self.producer.pins.request_id,
            "seq": self.seq, "monotonic_ns": self.clock,
            "event_kind": event["event_kind"],
            "model_origin_class": f02.SYNTHETIC,
            # Explicitly a *different* hash domain from F02 raw provider bytes.
            "raw_event_sha256": digest(g01.canonical(data)),
            "data": data,
        }
        receipt = self.deliver(converted)
        require(type(receipt) is dict and receipt.get("status") == "EVENT_ACCEPTED"
                and receipt.get("model_origin_class") == f02.SYNTHETIC
                and receipt.get("product_pass") is False
                and receipt.get("fresh_generated_provenance") is False
                and receipt.get("seq") == self.seq,
                "G01_A05_VERIFIER_REJECTED")
        self.bindings.append({
            "upstream_f02_event_id": event["event_id"],
            "upstream_f02_normalized_sha256": digest(f02.canonical(event)),
            "upstream_raw_provider_wire_sha256": next(
                row["original_provider_raw_sha256"] for row in self.raw_history
                if row["f02_event_id"] == event["event_id"]),
            "downstream_g01_event_id": converted["event_id"],
            "downstream_g01_data_sha256": converted["raw_event_sha256"],
            "downstream_g01_envelope_sha256": digest(g01.canonical(converted)),
            "event_kind": converted["event_kind"], "origin": f02.SYNTHETIC,
        })
        return receipt

    def ingest(self, raw: bytes):
        require(not self.finalized and not self.aborted and
                type(raw) is bytes and raw and len(raw) <= f02.MAX_RAW_EVENT,
                "JOIN_CLOSED_OR_INVALID_WIRE")
        try:
            wire = json.loads(raw)
            require(type(wire) is dict and wire.get("event") != "stream_end",
                    "USE_FINALIZE_FOR_END")
            out = self.producer.ingest(raw)
            for ev in out:
                self._check_f02(ev, raw)
                kind = ev["event_kind"]
                if kind == "provider_start":
                    self._emit(ev, {"provider": f02.SYNTHETIC})
                elif kind == "model_identity_observed":
                    # Provenance observation, not a G01-generated event or live caller.
                    require(type(ev.get("provider")) is str and
                            type(ev.get("model")) is str,
                            "UNOBSERVED_IDENTITY")
                elif kind == "provider_delta":
                    chunk = wire.get("text")
                    require(type(chunk) is str and
                            ev["delta_text_sha256"] == digest(chunk.encode()) and
                            ev["accumulated_text_sha256"] == digest(
                                self.producer.full_text.encode()),
                            "DELTA_RAW_AND_CUMULATIVE_HASH_MISMATCH")
                    self.raw_delta_ids.add(ev["event_id"])
                    self._emit(ev, {"text": chunk})
                elif kind == "claim_proposed":
                    require(self.proposal_index < len(self.producer.proposals),
                            "CLAIM_INDEX_OVERFLOW")
                    proposal = self.producer.proposals[self.proposal_index]
                    oid = ev["obligation_id"]
                    require(proposal["wire"] is ev and
                            oid == self.producer.pins.answer_obligation_ids[
                                self.proposal_index] and
                            ev["verification_status"] == "UNVERIFIED_NEVER_PUBLISH" and
                            ev["text_sha256"] == digest(proposal["text"].encode()) and
                            bool(ev["raw_delta_event_ids"]) and
                            set(ev["raw_delta_event_ids"]) <= self.raw_delta_ids and
                            all(ev[key] == getattr(self.producer.pins, key)
                                for key in ("source_release_sha256",
                                            "source_manifest_sha256",
                                            "source_acl_sha256", "source_rights_epoch")),
                            "CLAIM_OR_SOURCE_CAUSAL_PROOF_MISMATCH")
                    self._emit(ev, {"obligation_id": oid,
                                    "text": proposal["text"],
                                    "citation": self.citations[oid]})
                    self.proposal_index += 1
                elif kind == "provider_done":
                    require(self.pending_done is None and self.producer.done,
                            "DONE_REPLAY")
                    self.pending_done = ev
                else:
                    raise JoinDenied("UNSUPPORTED_F02_KIND")
            return len(out)
        except Exception:
            self.abort()
            raise

    def finalize(self, raw_end: bytes):
        require(not self.aborted and not self.finalized and self.pending_done is not None,
                "PROVIDER_DONE_REQUIRED")
        try:
            done = self.producer.finish(raw_end)
            require(done["event_kind"] == "stream_end" and
                    done["model_origin_class"] == f02.SYNTHETIC and
                    done["raw_event_sha256"] == digest(raw_end) and
                    done["publishable_answer"] is False and
                    len(self.producer.proposals) == 2 and
                    len(self.bindings) >= 5,
                    "INCOMPLETE_F02_SOURCE_END")
            self._check_f02(done, raw_end)
            require(len(f02.verify_record_chain(self.producer.journal.path)) ==
                    len(self.producer.events), "F02_JOURNAL_TAMPER")
            receipt = self._emit(self.pending_done, {"done": True})
            self.finalized = True
            return {"status": "F02_SYNTHETIC_STREAM_END_G01_DONE",
                    "model_origin_class": f02.SYNTHETIC,
                    "provider_called": False, "product_pass": False,
                    "stream_end_sha256": digest(raw_end),
                    "bridge_preflight_sha256": self.preflight_sha256,
                    "f02_event_count": len(self.raw_history),
                    "g01_delivered_count": len(self.bindings),
                    "g01_receipt": receipt}
        except Exception:
            self.abort()
            raise

    def terminal(self, terminal_callback):
        require(self.finalized and not self.aborted and not self.terminal_called,
                "UNVERIFIED_STREAM_END_OR_TERMINAL_REPLAY")
        self.terminal_called = True
        out = terminal_callback()
        require(type(out) is dict and out.get("status") == "LOCAL_FIXTURE_ANSWERED" and
                out.get("model_origin_class") == f02.SYNTHETIC and
                out.get("actual_client_ack") is True and
                out.get("source_byte_verified") is True and
                out.get("fresh_generated_provenance") is False and
                out.get("product_pass") is False,
                "G01_TERMINAL_OR_SOURCE_RECHECK_DENIED")
        return out

    def abort(self):
        if not self.aborted and not self.finalized:
            self.aborted = True
            if self.cancel is not None:
                try:
                    self.cancel()
                except Exception:
                    pass
        return {"status": "SAFE_ABSTENTION", "origin": f02.SYNTHETIC,
                "product_pass": False, "provider_called": False}
