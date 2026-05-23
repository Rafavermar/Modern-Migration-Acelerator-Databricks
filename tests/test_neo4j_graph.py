from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.neo4j_graph import build_neo4j_payload


class Neo4jGraphTests(unittest.TestCase):
    def test_builds_graph_payload_with_enriched_asset_properties(self) -> None:
        assets = [
            {
                "asset_id": "a1",
                "asset_name": "orders",
                "asset_type": "sqlserver_table",
                "source_system": "sql_server_docker",
                "platform": "SQL Server",
                "technology": "SQL Server 2022",
                "raw_path": "inventory.csv",
                "owner": "owner",
                "criticality": "high",
                "row_count": 10,
                "discovered_at": "2026-05-23T00:00:00+00:00",
            },
            {
                "asset_id": "a2",
                "asset_name": "fact_orders",
                "asset_type": "sqlserver_view",
                "source_system": "sql_server_docker",
                "platform": "SQL Server",
                "technology": "SQL Server 2022",
                "raw_path": "inventory.csv",
                "owner": "owner",
                "criticality": "high",
                "row_count": None,
                "discovered_at": "2026-05-23T00:00:00+00:00",
            },
        ]
        dependencies = [
            {
                "from_asset_id": "a2",
                "to_asset_id": "a1",
                "dependency_type": "depends_on",
                "evidence": "Inventory dependency: orders",
                "confidence": 0.8,
                "discovered_at": "2026-05-23T00:00:00+00:00",
            }
        ]
        risks = [
            {
                "asset_id": "a1",
                "risk_score": 60.0,
                "risk_level": "medium",
                "risk_factors": ["multiple dependencies"],
                "recommended_action": "Review.",
            }
        ]
        blueprint = [
            {
                "asset_id": "a1",
                "target_pattern": "Unity Catalog Delta table",
                "target_catalog": "migration_accelerator_dev",
                "target_schema": "silver",
                "target_object": "orders",
                "migration_notes": ["Load to Delta."],
            }
        ]

        payload = build_neo4j_payload(
            run_id="test_run",
            source_roots=["samples/legacy_metadata"],
            assets=assets,
            dependencies=dependencies,
            risk_register=risks,
            blueprint=blueprint,
            data_quality_plan=[{"asset_id": "a1"}, {"asset_id": "a1"}],
            asset_priority_matrix=[{"asset_id": "a1", "review_priority": "p1"}],
        )

        self.assertEqual(payload.run["asset_count"], 2)
        self.assertEqual(payload.run["dependency_count"], 1)
        self.assertEqual(payload.assets[0]["risk_level"], "medium")
        self.assertEqual(payload.assets[0]["dq_check_count"], 2)
        self.assertEqual(payload.relationships[0]["dependency_type"], "depends_on")
        self.assertEqual(payload.source_systems, [{"name": "sql_server_docker"}])
        self.assertEqual(payload.target_patterns, [{"name": "Unity Catalog Delta table"}])


if __name__ == "__main__":
    unittest.main()
