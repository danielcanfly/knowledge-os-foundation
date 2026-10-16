from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import shutil
import tempfile
from pathlib import Path
import unittest

from wave_b01.components.a05.adapter.a05_retrieval import SourceError
from wave_b02.joined_core import (
    A05_SOURCE,
    TARGET_PASSAGE,
    a06_projection,
    admit_joined_contract,
    contract_hash,
    retrieve_a05,
    verify_generated_claim,
)


def contract(run_id: str = "a06-b02-joined-unit") -> dict:
    return {
        "version": "m27.b02.joined-task/v1",
        "run_id": run_id,
        "tenant": "tenant-a",
        "context_grant": {
            "tenant": "owner-internal", "roles": ["internal"],
            "release_id": "a05context-7835ec95cee63972",
            "source_revision": "89f1d7be1623cd6926a69e38871544eefe39e584",
            "expires_at": "2027-01-11T21:36:23.210892+00:00",
        },
        "actor": "owner-researcher",
        "goal": "Produce one grounded policy claim and a reversible local observation",
        "deadline": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        "budget": {"max_source_reads": 3, "max_action_attempts": 1,
                   "max_context_reads": 1, "max_model_calls": 1},
        "rights": ["read-firstparty", "write-own-observation"],
        "a06_sources": ["CHARTER", "DELIVERY", "I37_ACCEPTANCE"],
        "outcome": "verified-research-and-reversible-observation",
    }


class JoinedContractTests(unittest.TestCase):
    def test_admission_binds_a06_projection_and_a05_grant(self):
        value = contract()
        admitted = admit_joined_contract(value)
        self.assertEqual(admitted["run_id"], value["run_id"])
        self.assertEqual(admitted["joined_contract_sha256"], contract_hash(value))
        self.assertEqual(admitted["a06_admission"]["task_lane"]["run_id"], value["run_id"])
        self.assertIs(admitted["production_authority"], False)

    def test_unauthorized_action_is_denied(self):
        value = contract()
        value["rights"] = ["read-firstparty", "write-production"]
        with self.assertRaisesRegex(PermissionError, "SCOPES_DENIED"):
            admit_joined_contract(value)

    def test_exhausted_action_budget_is_denied(self):
        value = contract()
        value["budget"]["max_action_attempts"] = 0
        with self.assertRaisesRegex(ValueError, "BUDGET_DENIED"):
            admit_joined_contract(value)

    def test_wrong_a05_acl_is_denied(self):
        value = contract()
        value["context_grant"]["tenant"] = "other-tenant"
        admit_joined_contract(value)
        with self.assertRaisesRegex(SourceError, "access_denied"):
            retrieve_a05(value)

    def test_a05_exact_passage_and_no_memory(self):
        result = retrieve_a05(contract())
        self.assertEqual(result["results"][0]["passage_id"], TARGET_PASSAGE)
        self.assertEqual(result["memory_candidates_included"], 0)
        self.assertEqual(result["results"][0]["citation"]["byte_start"], 1215)

    def test_stale_source_is_denied(self):
        with self.assertRaisesRegex(SourceError, "source_stale"):
            retrieve_a05(contract(), now=datetime.now(timezone.utc) + timedelta(days=500))

    def test_source_byte_tamper_is_denied(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "source"
            shutil.copytree(A05_SOURCE, root)
            with (root / "01_contracts.md").open("ab") as handle:
                handle.write(b"\nTAMPER\n")
            with self.assertRaisesRegex(SourceError, "source_integrity_failed"):
                retrieve_a05(contract(), root=root)

    def test_bounded_verifier_accepts_grounded_paraphrase(self):
        context = retrieve_a05(contract())
        claim = verify_generated_claim(
            context,
            "The Agent may request deterministic enforcement, but PolicyEngine decides.",
        )
        self.assertEqual(claim["passage_id"], TARGET_PASSAGE)
        self.assertIs(claim["memory_citation_authority"], False)

    def test_bounded_verifier_rejects_span_and_text_tamper(self):
        context = retrieve_a05(contract())
        tampered = copy.deepcopy(context)
        tampered["results"][0]["citation"]["byte_end"] -= 1
        with self.assertRaisesRegex(ValueError, "CITATION_OR_EXCERPT_TAMPERED"):
            verify_generated_claim(
                tampered,
                "The Agent may request deterministic enforcement, but PolicyEngine decides.",
            )
        with self.assertRaisesRegex(ValueError, "BOUNDED_SEMANTIC_UNSUPPORTED"):
            verify_generated_claim(context, "This unrelated claim has no support.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
