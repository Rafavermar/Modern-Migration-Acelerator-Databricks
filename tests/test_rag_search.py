from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.rag_search import (
    build_retrieval_brief,
    configure_console_encoding,
    default_mlflow_tracking_uri,
    parse_vector_search_rows,
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


if __name__ == "__main__":
    unittest.main()
