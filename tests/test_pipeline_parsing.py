from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.discovery import TextDocument
from modern_migration_accelerator.pipelines.run_accelerator import parse_documents


class PipelineParsingTests(unittest.TestCase):
    def test_parses_synapse_serverless_inventory_dependencies(self) -> None:
        document = TextDocument(
            path="inventory.csv",
            extension=".csv",
            content=(
                "source_system,database,schema,table,object_name,object_type,row_count,owner,"
                "criticality,engine,location,format,depends_on\n"
                "azure_synapse,legacy_lake,,,,serverless_database,,owner,high,"
                "Serverless SQL Pool,,,\n"
                "azure_synapse,legacy_lake,ext,ExternalOrders,,external_table,,owner,high,"
                "Serverless SQL Pool,abfss://legacy/orders,parquet,legacy_lake.ext.RawOrders\n"
            ),
        )

        _, assets, dependencies = parse_documents([document], "test_run")
        asset_types = {asset["asset_type"] for asset in assets}

        self.assertIn("synapse_serverless_database", asset_types)
        self.assertIn("synapse_external_table", asset_types)
        self.assertEqual(len(dependencies), 1)
        self.assertEqual(dependencies[0]["dependency_type"], "depends_on")

    def test_parses_synapse_notebook_sql_references(self) -> None:
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "source": [
                        "spark.sql(\"\"\"\n",
                        "SELECT * FROM legacy_lake.ext.ExternalCustomers\n",
                        "\"\"\")\n",
                    ],
                }
            ],
            "metadata": {"language_info": {"name": "python"}},
        }
        document = TextDocument(
            path="nb_customer_features.ipynb",
            extension=".ipynb",
            content=json.dumps(notebook),
        )

        _, assets, dependencies = parse_documents([document], "test_run")
        asset_names = {asset["asset_name"] for asset in assets}

        self.assertIn("nb_customer_features.ipynb", asset_names)
        self.assertIn("legacy_lake.ext.externalcustomers", asset_names)
        self.assertEqual(len(dependencies), 1)

    def test_parses_adf_dataset_linked_service_and_redacts_secret_metadata(self) -> None:
        dataset = TextDocument(
            path="ds_orders.json",
            extension=".json",
            content=json.dumps(
                {
                    "name": "ds_orders",
                    "type": "Microsoft.DataFactory/factories/datasets",
                    "properties": {
                        "type": "AzureSqlDWTable",
                        "linkedServiceName": {"referenceName": "ls_synapse"},
                        "typeProperties": {"schema": "dbo", "table": "CustomerOrders"},
                    },
                }
            ),
        )
        linked_service = TextDocument(
            path="ls_synapse.json",
            extension=".json",
            content=json.dumps(
                {
                    "name": "ls_synapse",
                    "type": "Microsoft.DataFactory/factories/linkedservices",
                    "properties": {
                        "type": "AzureSqlDW",
                        "typeProperties": {
                            "connectionString": "Server=x;User ID=y;Password=plain-text;"
                        },
                    },
                }
            ),
        )

        _, assets, dependencies = parse_documents([dataset, linked_service], "test_run")
        asset_types = {asset["asset_type"] for asset in assets}
        dependency_types = {dependency["dependency_type"] for dependency in dependencies}
        linked_service_asset = next(asset for asset in assets if asset["asset_type"] == "adf_linked_service")

        self.assertIn("adf_dataset", asset_types)
        self.assertIn("adf_linked_service", asset_types)
        self.assertIn("adf_data_object", asset_types)
        self.assertIn("uses_connection", dependency_types)
        self.assertIn("points_to", dependency_types)
        self.assertNotIn("plain-text", linked_service_asset["metadata_json"])
        self.assertIn("***REDACTED***", linked_service_asset["metadata_json"])

    def test_parses_adf_trigger_pipeline_relationship(self) -> None:
        trigger = TextDocument(
            path="trigger.json",
            extension=".json",
            content=json.dumps(
                {
                    "name": "tr_daily",
                    "type": "Microsoft.DataFactory/factories/triggers",
                    "properties": {
                        "type": "ScheduleTrigger",
                        "runtimeState": "Started",
                        "pipelines": [
                            {
                                "pipelineReference": {
                                    "referenceName": "pl_ingest_customer_orders",
                                    "type": "PipelineReference",
                                }
                            }
                        ],
                    },
                }
            ),
        )

        _, assets, dependencies = parse_documents([trigger], "test_run")

        self.assertIn("adf_trigger", {asset["asset_type"] for asset in assets})
        self.assertEqual(dependencies[0]["dependency_type"], "triggers")


if __name__ == "__main__":
    unittest.main()
