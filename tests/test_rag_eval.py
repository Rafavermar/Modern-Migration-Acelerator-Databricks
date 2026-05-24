from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.rag_eval import EvalCase, evaluate_case, load_eval_cases
from modern_migration_accelerator.rag_search import WorkflowOutputs


class RagEvalTests(unittest.TestCase):
    def test_evaluate_case_scores_terms_and_assets(self) -> None:
        case = EvalCase(
            case_id="orders",
            question="Which order asset moves first?",
            expected_terms=["risk", "priority"],
            expected_assets=["FactOrders"],
            min_score=0.6,
        )
        outputs = WorkflowOutputs(
            response={},
            rows=[{"asset_name": "FactOrders", "chunk_text": "Priority p1 and high risk."}],
            brief="FactOrders has high risk and priority p1.",
            results_path=Path("out/latest_search.json"),
            brief_path=Path("out/latest_answer.md"),
            trace_path=Path("out/latest_trace.json"),
        )

        result = evaluate_case(case, outputs)

        self.assertTrue(result.passed)
        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.missing_terms, [])
        self.assertEqual(result.missing_assets, [])

    def test_load_eval_cases_supports_schema_object(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cases.json"
            path.write_text(
                """
                {
                  "schema": "test",
                  "cases": [
                    {
                      "id": "case_1",
                      "question": "Question?",
                      "expected_terms": ["alpha"],
                      "expected_assets": ["asset"],
                      "min_score": 0.5
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            cases = load_eval_cases(path)

        self.assertEqual(len(cases), 1)
        self.assertEqual(cases[0].case_id, "case_1")
        self.assertEqual(cases[0].expected_terms, ["alpha"])


if __name__ == "__main__":
    unittest.main()
