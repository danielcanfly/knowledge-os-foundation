"""End-to-end cited-segment parity security tests in a dependency-isolated unit.

Using the genuine checked-out source file with only the unrelated package import
isolated. No model calls, protected 523, production, or Product ABI promotion.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
import unittest

BASE = Path(__file__).resolve().parents[1]
NS = "_m27_stream_parity_scoped_test"
package = types.ModuleType(NS)
package.__path__ = [str(BASE / "src/knowledge_engine")]
sys.modules.setdefault(NS, package)
streaming = types.ModuleType(NS + ".m27_isolated_streaming")
streaming.M27_ISOLATED_STREAM_SCHEMA = "m27-isolated-first-answer-stream/v1"
sys.modules[streaming.__name__] = streaming
src = BASE / "src/knowledge_engine/m27_release_hard_gates.py"
spec = importlib.util.spec_from_file_location(NS + ".m27_release_hard_gates", src)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)
SCHEMA = streaming.M27_ISOLATED_STREAM_SCHEMA


def event(name, **args):
    return {"schema_version": SCHEMA, "event": name, **args}


def cited(text):
    return event("cited_segment_ready", text=text, citations=[{"citation_id": "a05-true-citation"}])


class GenuineStreamParity(unittest.TestCase):
    def apply(self, items, text):
        return mod.evaluate_streaming_hard_gate(items, final_answer_text=text)

    def test_single_segment_original_contract_remains_pass(self):
        r = self.apply([event("request_started"), cited("one"), event("final_answer_done")], "one")
        self.assertTrue(r["passed"], r["reason_codes"])

    def test_two_real_segments_must_match_concatenated_final(self):
        r = self.apply([event("request_started"), cited("Hello "), cited("world"),
                        event("final_answer_done")], "Hello world")
        self.assertTrue(r["passed"], r["reason_codes"])

    def test_last_chunk_only_cannot_silently_ignore_prior_wrong_text(self):
        r = self.apply([event("request_started"), cited("UNVERIFIED INJECTION "), cited("world"),
                        event("final_answer_done")], "world")
        self.assertFalse(r["passed"])
        self.assertIn("FINAL_ANSWER_PARITY_MISMATCH", r["reason_codes"])

    def test_material_published_after_final_terminal_is_refused(self):
        r = self.apply([event("request_started"), cited("safe"),
                        event("final_answer_done"), cited("unsafe")], "safeunsafe")
        self.assertFalse(r["passed"])
        self.assertIn("MATERIAL_TEXT_AFTER_FINAL_COMPLETION", r["reason_codes"])

    def test_duplicate_final_terminal_is_refused(self):
        r = self.apply([event("request_started"), cited("answer"), event("final_answer_done"),
                        event("final_answer_done")], "answer")
        self.assertFalse(r["passed"])
        self.assertIn("DUPLICATE_FINAL_ANSWER_DONE", r["reason_codes"])

    def test_empty_cited_segment_is_not_a_substantive_answer(self):
        r = self.apply([event("request_started"), cited(""), event("final_answer_done")], "")
        self.assertFalse(r["passed"])
        self.assertIn("EMPTY_CITED_SEGMENT_TEXT", r["reason_codes"])

    def test_wrong_citation_on_second_segment_denied(self):
        missing = event("cited_segment_ready", text="second", citations=[])
        r = self.apply([event("request_started"), cited("first"), missing,
                        event("final_answer_done")], "firstsecond")
        self.assertFalse(r["passed"])
        self.assertIn("MATERIAL_TEXT_WITHOUT_CITATIONS", r["reason_codes"])

    def test_final_answer_parity_mandatory_for_admission(self):
        r = mod.evaluate_streaming_hard_gate([event("request_started"), cited("answer"),
                                              event("final_answer_done")])
        self.assertFalse(r["passed"])
        self.assertIn("FINAL_ANSWER_PARITY_UNPROVEN", r["reason_codes"])

    def test_safeterminal_still_refuses_cited_text(self):
        r = self.apply([event("request_started"), cited("leak"), event("safe_abstention_done"),
                        event("final_answer_done")], "leak")
        self.assertFalse(r["passed"])
        self.assertIn("SAFE_TERMINAL_EMITTED_MATERIAL_TEXT", r["reason_codes"])

    def test_non_string_segment_rejected_not_str_converted(self):
        r = self.apply([event("request_started"),
                        event("cited_segment_ready", text=5, citations=[{"citation_id":"x"}]),
                        event("final_answer_done")], "5")
        self.assertFalse(r["passed"])
        self.assertIn("INVALID_CITED_SEGMENT_TEXT", r["reason_codes"])


if __name__ == "__main__":
    unittest.main()
