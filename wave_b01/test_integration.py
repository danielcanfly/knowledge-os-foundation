from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from a08_nonprod.experiment import CANDIDATE, load_workload, run_case
from knowledge_engine.m26_aq_semantic_contract import runtime_contract_identity
from knowledge_engine.m27_a09_abi_conformance import Denied as A09Denied
from wave_b01.components.a05.adapter.a05_retrieval import SourceError
from wave_b01.components.a07.a07_memory import Denied as MemoryDenied, MemoryStore
from wave_b01.integration import (
    A04_CONTRACT,
    ABI,
    admit_task_contract,
    attestations_and_eval_gates,
    candidate_manifest,
    retrieve_context,
    validate_a04_stream,
)


def task_contract(**overrides):
    value = {
        "run_id": "a06-b01-integration",
        "tenant": "tenant-a",
        "actor": "owner-researcher",
        "goal": "Verify the isolated B01 integration boundary",
        "deadline": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "budget": {"max_source_reads": 3, "max_action_attempts": 1},
        "sources": ["CHARTER", "DELIVERY", "I37_ACCEPTANCE"],
        "rights": ["read-firstparty", "write-own-observation"],
        "outcome": "verified-research-and-reversible-observation",
        "version": "a06-v1",
    }
    value.update(overrides)
    return value


class WaveB01IntegrationTests(unittest.TestCase):
    def test_task_and_provider_lanes_are_bounded_and_separate(self):
        admitted = admit_task_contract(task_contract())
        self.assertEqual(admitted["abi"], ABI)
        self.assertEqual(admitted["task_lane"]["budget"]["max_action_attempts"], 1)
        self.assertLessEqual(admitted["provider_lane"]["max_provider_calls"], 3)
        self.assertEqual(admitted["provider_lane"]["max_tool_calls"], 0)
        self.assertIs(admitted["production_authority"], False)

    def test_task_scope_escalation_is_denied(self):
        with self.assertRaisesRegex(PermissionError, "SCOPES_DENIED"):
            admit_task_contract(task_contract(
                rights=["read-firstparty", "write-production"]))

    def test_a01_runtime_contract_identity_remains_canonical(self):
        identity = runtime_contract_identity()
        self.assertTrue(identity["entrypoint"].endswith("run_owner_arbitrary_query"))
        self.assertEqual(len(identity["runtime_contract_fingerprint"]), 64)

    def test_a05_source_context_positive_and_memory_excluded(self):
        result = retrieve_context("Task Contract")
        self.assertEqual(result["status"], "source_passages")
        self.assertTrue(result["results"])
        self.assertEqual(result["memory_candidates_included"], 0)
        self.assertTrue(all(row["citation"]["document_sha256"]
                            for row in result["results"]))

    def test_a05_unsupported_and_stale_sources_fail_closed(self):
        unsupported = retrieve_context("zxqv nonexistent ultramarine token")
        self.assertEqual(unsupported["status"], "abstained")
        with self.assertRaisesRegex(SourceError, "source_stale"):
            retrieve_context("Task Contract",
                             now=datetime.now(timezone.utc) + timedelta(days=500))

    def test_a04_stream_maps_to_a09_x09_and_rejects_tamper(self):
        contract = json.loads(A04_CONTRACT.read_text())
        self.assertIs(contract["native_q34_integrated"], False)
        events = [
            {"event": "claim.verified", "text": "Bounded verified claim",
             "source_id": "atlas-A", "source_sha256": "a" * 64, "span": [0, 8]},
            {"event": "run.terminal", "status": "succeeded"},
        ]
        validate_a04_stream(events)
        events[0]["source_sha256"] = None
        with self.assertRaisesRegex(A09Denied, "X09_UNGROUNDED_GENERATED_TEXT"):
            validate_a04_stream(events)

    def test_a07_memory_is_candidate_only_and_revocation_invalidates(self):
        with tempfile.TemporaryDirectory() as folder:
            store = MemoryStore(Path(folder) / "memory")
            expiry = int(time.time()) + 3600
            store.grant_source(tenant="tenant-a", principal="owner", source="src1",
                               purpose="project", payload=b"candidate-only",
                               expires=expiry, consent=True)
            store.write_memory(tenant="tenant-a", principal="owner", memid="mem1",
                               summary="candidate summary", sources=("src1",),
                               expires=expiry)
            candidate = store.candidate(
                tenant="tenant-a", principal="owner", memid="mem1")
            self.assertIs(candidate["knowledge_authority"], False)
            self.assertIs(candidate["citation_eligible"], False)
            with self.assertRaisesRegex(MemoryDenied, "MEMORY_NOT_EVIDENCE_OR_CITATION"):
                store.to_evidence(candidate)
            store.revoke_source(tenant="tenant-a", principal="owner", source="src1")
            with self.assertRaises(MemoryDenied):
                store.candidate(tenant="tenant-a", principal="owner", memid="mem1")

    def test_a08_unknown_effect_is_terminal_without_retry(self):
        case = load_workload()[0]
        result = run_case(case, CANDIDATE, fault="UNKNOWN_EFFECT")
        self.assertEqual(result["status"], "UNKNOWN_EFFECT_RECONCILE_REQUIRED")
        self.assertEqual(result["provider_attempts"], 1)
        self.assertEqual([event["state"] for event in result["events"]],
                         ["POSSIBLY_SENT_UNRESOLVED"])

    def test_a02_and_a10_do_not_gain_authority(self):
        gates = attestations_and_eval_gates()
        self.assertIs(gates["a02_formal_release_authority"], False)
        self.assertIs(gates["sealed_content_read"], False)
        self.assertEqual(gates["official_original523"], "NOT_RUN_0_OF_523")
        self.assertEqual(gates["official_product_blind200"], "NOT_RUN_0_OF_200")

    def test_candidate_manifest_keeps_frozen_boundaries(self):
        manifest = candidate_manifest()
        self.assertEqual(manifest["scope"], "NONPROD_ONLY")
        boundaries = manifest["boundaries"]
        self.assertIs(boundaries["q34_unchanged"], True)
        self.assertIs(boundaries["production_unchanged"], True)
        self.assertIs(boundaries["sealed_evaluation_not_read"], True)
        self.assertIs(boundaries["historical_failures_preserved"], True)
        self.assertIs(boundaries["release_authority"], False)
        self.assertTrue(all(len(value) == 64 for value in manifest["inputs"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
