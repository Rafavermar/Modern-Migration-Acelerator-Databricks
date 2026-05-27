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
from modern_migration_accelerator.pipelines.run_accelerator import (
    build_asset_priority_matrix,
    build_assessment_summary,
    build_blueprint,
    build_data_quality_plan,
    build_graph_edges,
    build_risk_register,
    parse_documents,
)


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

    def test_parses_sqlserver_inventory_with_sqlserver_asset_types(self) -> None:
        document = TextDocument(
            path="sqlserver_inventory.csv",
            extension=".csv",
            content=(
                "source_system,database,schema,table,object_name,object_type,row_count,owner,"
                "criticality,engine,location,format,depends_on\n"
                "sql_server_prod,LegacySales,dbo,CustomerOrders,CustomerOrders,table,4,owner,high,"
                "SQL Server 2022,,,\n"
                "sql_server_prod,LegacySales,mart,,FactOrders,view,,owner,high,"
                "SQL Server 2022,,,LegacySales.dbo.CustomerOrders\n"
                "sql_server_prod,LegacySales,dbo,,usp_build_fact_orders,stored_procedure,,owner,high,"
                "SQL Server 2022,,,LegacySales.dbo.CustomerOrders\n"
            ),
        )

        _, assets, dependencies = parse_documents([document], "test_run")
        asset_types = {asset["asset_type"] for asset in assets}

        self.assertIn("sqlserver_table", asset_types)
        self.assertIn("sqlserver_view", asset_types)
        self.assertIn("sqlserver_stored_procedure", asset_types)
        self.assertIn("sqlserver_dependency_reference", asset_types)
        self.assertEqual(len(dependencies), 2)

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
                            "server": "example.sql.azuresynapse.net",
                            "database": "sales",
                            "pass" + "word": "mask_me",
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
        self.assertNotIn("mask_me", linked_service_asset["metadata_json"])
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

    def test_parses_lakebridge_analyzer_report(self) -> None:
        document = TextDocument(
            path="synapse/lakebridge/lakebridge-analyzer-results.xlsx",
            extension=".xlsx",
            content=(
                "## Sheet: SQL Programs\n"
                "Program Name\tSource File\tIncluded\tLine Count\tComplexity\tStatement Count\t"
                "Procedure And Function Counts\tScript Category\tCategorization Metrics\n"
                "clean.sql\t/repo/clean.sql\tYES\t81\tHIGH\t71\t0\tCREATE_VIEW\tmetrics\n"
                "\n"
                "## Sheet: RAW_PROGRAM_OBJECT_XREF\n"
                "Program\tObject\tOperation\tCount\n"
                "/repo/clean.sql\t[dbo].[Customer]\tREAD\t2\n"
                "/repo/clean.sql\t[dbo].[FactSales]\tWRITE\t1\n"
            ),
        )

        _, assets, dependencies = parse_documents([document], "test_run")
        risks = build_risk_register(assets, dependencies, "test_run")
        blueprint = build_blueprint(assets, "test_run", "migration_accelerator_dev")
        asset_types = {asset["asset_type"] for asset in assets}
        dependency_types = {dependency["dependency_type"] for dependency in dependencies}
        program_risk = next(risk for risk in risks if risk["asset_type"] == "lakebridge_sql_program")
        program_blueprint = next(
            row for row in blueprint if row["legacy_asset_type"] == "lakebridge_sql_program"
        )

        self.assertIn("lakebridge_sql_program", asset_types)
        self.assertIn("lakebridge_referenced_object", asset_types)
        self.assertEqual(dependency_types, {"reads", "writes"})
        self.assertEqual(program_risk["risk_level"], "high")
        self.assertEqual(program_blueprint["target_pattern"], "Databricks SQL or PySpark transformation")

    def test_builds_human_readable_consumption_outputs(self) -> None:
        document = TextDocument(
            path="inventory.csv",
            extension=".csv",
            content=(
                "source_system,database,schema,table,object_name,object_type,row_count,owner,"
                "criticality,engine,location,format,depends_on\n"
                "azure_synapse,sales,dbo,CustomerOrders,,table,25000000,owner,critical,"
                "Dedicated SQL Pool,,,sales.dbo.Customers\n"
            ),
        )

        _, assets, dependencies = parse_documents([document], "test_run")
        risks = build_risk_register(assets, dependencies, "test_run")
        blueprint = build_blueprint(assets, "test_run", "migration_accelerator_dev")
        dq_plan = build_data_quality_plan(assets, "test_run", "migration_accelerator_dev")
        graph_edges = build_graph_edges(assets, dependencies, "test_run")
        priority_matrix = build_asset_priority_matrix(
            assets,
            dependencies,
            risks,
            blueprint,
            dq_plan,
            "test_run",
        )
        summary = build_assessment_summary(
            assets,
            dependencies,
            risks,
            blueprint,
            dq_plan,
            "test_run",
        )

        self.assertEqual(len(graph_edges), len(dependencies))
        self.assertEqual(len(priority_matrix), len(assets))
        self.assertEqual(summary[0]["summary_name"], "executive_summary")
        self.assertGreaterEqual(summary[0]["asset_count"], 1)
        self.assertIn(priority_matrix[0]["review_priority"], {"p1", "p2", "p3"})


if __name__ == "__main__":
    unittest.main()
