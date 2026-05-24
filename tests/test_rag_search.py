from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.rag_search import (
    build_retrieval_brief,
    build_llm_messages,
    configure_console_encoding,
    default_mlflow_tracking_uri,
    extract_chat_content,
    parse_vector_search_rows,
    resolve_databricks_executable,
)


class RagSearchTests(unittest.TestCase):
    def test_parse_vector_search_rows_uses_manifest_columns(self) -> None:
        response = {
            "manifest": {
                "columns": [
                    {"name": "chunk_id"},
                    {"name": "asset_name"},
                    {"name": "risk_level"},
                ]
            },
            "result": {
                "data_array": [
                    ["chunk_1", "FactOrders", "high"],
                    ["chunk_2", "DimCustomer", "medium"],
                ]
            },
        }

        rows = parse_vector_search_rows(response)

        self.assertEqual(rows[0]["chunk_id"], "chunk_1")
        self.assertEqual(rows[0]["asset_name"], "FactOrders")
        self.assertEqual(rows[1]["risk_level"], "medium")

    def test_build_retrieval_brief_is_grounded_in_returned_rows(self) -> None:
        rows = [
            {
                "chunk_id": "chunk_1",
                "document_type": "risk_register",
                "asset_name": "FactOrders",
                "risk_level": "high",
                "review_priority": "p1",
                "target_pattern": "Delta fact table",
                "source_path": "gold.risk_register",
                "chunk_text": "FactOrders has cross-system dependencies and should be reviewed first.",
            }
        ]

        brief = build_retrieval_brief("What should move first?", rows)

        self.assertIn("FactOrders", brief)
        self.assertIn("gold.risk_register", brief)
        self.assertIn("grounded search brief", brief)

    def test_default_mlflow_tracking_uri_uses_databricks_profile(self) -> None:
        self.assertEqual(default_mlflow_tracking_uri("mma-fulltrial"), "databricks://mma-fulltrial")

    def test_configure_console_encoding_is_safe(self) -> None:
        configure_console_encoding()

    def test_build_llm_messages_ground_prompt_in_evidence(self) -> None:
        rows = [
            {
                "asset_name": "FactOrders",
                "document_type": "asset_priority",
                "risk_level": "high",
                "review_priority": "p1",
                "target_pattern": "Unity Catalog Delta table",
                "source_path": "gold.asset_priority_matrix",
                "chunk_text": "Priority: p1. Risk level: high.",
            }
        ]

        messages = build_llm_messages("What moves first?", rows)

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Use only the evidence", messages[0]["content"])
        self.assertIn("Never recommend a p3", messages[0]["content"])
        self.assertIn("FactOrders", messages[1]["content"])

    def test_extract_chat_content_from_openai_style_response(self) -> None:
        response = {"choices": [{"message": {"content": "Grounded answer."}}]}

        self.assertEqual(extract_chat_content(response), "Grounded answer.")

    def test_resolve_databricks_executable_prefers_env_override(self) -> None:
        with patch.dict("os.environ", {"DATABRICKS_CLI": "C:/tools/databricks.exe"}):
            self.assertEqual(resolve_databricks_executable(), "C:/tools/databricks.exe")


if __name__ == "__main__":
    unittest.main()
