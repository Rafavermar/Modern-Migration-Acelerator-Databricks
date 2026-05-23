from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.pipelines.run_semantic_index_prep import (
    TextDocument,
    build_source_document_chunks,
    sanitize_document_content,
    split_text_chunks,
)


class SemanticIndexPrepTests(unittest.TestCase):
    def test_sanitizes_json_secrets_before_chunking(self) -> None:
        document = TextDocument(
            path="adf_linked_service.json",
            extension=".json",
            content=json.dumps(
                {
                    "name": "ls_sales",
                    "properties": {
                        "typeProperties": {
                            "connection" + "String": "placeholder_connection_value",
                            "account" + "Key": "placeholder_key_value",
                        }
                    },
                }
            ),
        )

        sanitized = sanitize_document_content(document)

        self.assertIn("***REDACTED***", sanitized)
        self.assertNotIn("placeholder_connection_value", sanitized)
        self.assertNotIn("placeholder_key_value", sanitized)

    def test_extracts_notebook_cells_as_searchable_text(self) -> None:
        document = TextDocument(
            path="synapse/notebooks/features.ipynb",
            extension=".ipynb",
            content=json.dumps(
                {
                    "cells": [
                        {
                            "cell_type": "code",
                            "source": ["spark.sql('SELECT * FROM legacy_lake.ext.ExternalOrders')"],
                        }
                    ]
                }
            ),
        )

        sanitized = sanitize_document_content(document)

        self.assertIn("Notebook cell 1", sanitized)
        self.assertIn("ExternalOrders", sanitized)

    def test_builds_contextual_source_chunks(self) -> None:
        document = TextDocument(
            path="/Volumes/catalog/landing/legacy_metadata/adf/pl_orders.json",
            extension=".json",
            content=json.dumps({"name": "pl_orders", "type": "pipeline"}),
        )
        context = {
            document.path: {
                "asset_id": "asset_1",
                "asset_name": "pl_orders",
                "asset_type": "adf_pipeline",
                "source_system": "adf",
            }
        }

        rows = build_source_document_chunks([document], context, "run_1", "2026-05-23T00:00:00+00:00")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_id"], "asset_1")
        self.assertEqual(rows[0]["document_type"], "legacy_artifact")
        self.assertEqual(rows[0]["source_format"], "json")
        self.assertTrue(rows[0]["chunk_text"])

    def test_splits_large_text_with_overlap(self) -> None:
        chunks = split_text_chunks("word " * 2000, max_chars=500, overlap_chars=50)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 500 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
