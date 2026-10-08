import unittest
import ast, re
from pathlib import Path
source = Path(__file__).resolve().parents[1] / "src/knowledge_engine/m27_agent_product_runtime.py"
tree = ast.parse(source.read_text())
fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_question_obligation_gap")
scope = {"re": re}
exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), scope)
_question_obligation_gap = scope["_question_obligation_gap"]

class QuestionObligationGate(unittest.TestCase):
    def test_missing_exact_metric(self):
        q = "What exact production traffic volume did this section serve on the day after accepted release 20260720T160000Z-46137c97263e?"
        self.assertEqual(_question_obligation_gap(q, "Agent planning supports runbooks."), "MISSING_EXACT_PRODUCTION_TRAFFIC_MEASURE")
    def test_metric_without_release_identity(self):
        q = "What exact production traffic volume followed accepted release 20260720T160000Z-46137c97263e?"
        self.assertEqual(_question_obligation_gap(q, "432 requests served."), "MISSING_RELEASE_ANCHOR")
    def test_both_metric_and_release(self):
        q = "What exact production traffic volume followed accepted release 20260720T160000Z-46137c97263e?"
        self.assertIsNone(_question_obligation_gap(q, "432 requests served after 20260720T160000Z-46137c97263e."))
    def test_provenance_wrong_domain(self):
        q = "Which retrieved-at/source-commit/release identities must be checked for the harness?"
        self.assertEqual(_question_obligation_gap(q, "IRAS corporate tax exemption."), "MISSING_PROVENANCE_IDENTITY_DIMENSIONS")
    def test_provenance_all_dimensions(self):
        q = "Which retrieved-at/source-commit/release identities must be checked for the harness?"
        self.assertIsNone(_question_obligation_gap(q, "Compare retrieved-at, source-commit, and release identities."))
    def test_unrelated_question_unchanged(self):
        self.assertIsNone(_question_obligation_gap("How does Kubernetes schedule inference?", "Kubernetes schedules inference jobs."))
if __name__ == "__main__":
    unittest.main()
