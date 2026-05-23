from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Neo4jGraphPayload:
    run: dict[str, Any]
    assets: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    source_systems: list[dict[str, Any]]
    target_patterns: list[dict[str, Any]]


def relationship_id(run_id: str, from_asset_id: str, to_asset_id: str, dependency_type: str) -> str:
    raw = "|".join([run_id, from_asset_id, to_asset_id, dependency_type])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def build_neo4j_payload(
    *,
    run_id: str,
    source_roots: list[str],
    assets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    risk_register: list[dict[str, Any]],
    blueprint: list[dict[str, Any]],
    data_quality_plan: list[dict[str, Any]],
    asset_priority_matrix: list[dict[str, Any]],
) -> Neo4jGraphPayload:
    risk_by_asset = {row["asset_id"]: row for row in risk_register}
    blueprint_by_asset = {row["asset_id"]: row for row in blueprint}
    priority_by_asset = {row["asset_id"]: row for row in asset_priority_matrix}
    dq_counts = Counter(row["asset_id"] for row in data_quality_plan)
    dependency_counts = Counter()
    for dependency in dependencies:
        dependency_counts[dependency["from_asset_id"]] += 1
        dependency_counts[dependency["to_asset_id"]] += 1

    graph_assets: list[dict[str, Any]] = []
    for asset in assets:
        asset_id = asset["asset_id"]
        risk = risk_by_asset.get(asset_id, {})
        target = blueprint_by_asset.get(asset_id, {})
        priority = priority_by_asset.get(asset_id, {})
        graph_assets.append(
            {
                "asset_id": asset_id,
                "run_id": run_id,
                "asset_name": asset.get("asset_name"),
                "asset_type": asset.get("asset_type"),
                "source_system": asset.get("source_system"),
                "platform": asset.get("platform"),
                "technology": asset.get("technology"),
                "raw_path": asset.get("raw_path"),
                "owner": asset.get("owner"),
                "criticality": asset.get("criticality"),
                "row_count": asset.get("row_count"),
                "risk_score": risk.get("risk_score"),
                "risk_level": risk.get("risk_level"),
                "risk_factors": risk.get("risk_factors", []),
                "recommended_action": risk.get("recommended_action"),
                "target_pattern": target.get("target_pattern"),
                "target_catalog": target.get("target_catalog"),
                "target_schema": target.get("target_schema"),
                "target_object": target.get("target_object"),
                "migration_notes": target.get("migration_notes", []),
                "review_priority": priority.get("review_priority"),
                "dependency_count": dependency_counts[asset_id],
                "dq_check_count": dq_counts[asset_id],
                "discovered_at": asset.get("discovered_at"),
            }
        )

    graph_relationships = [
        {
            "relationship_id": relationship_id(
                run_id,
                dependency["from_asset_id"],
                dependency["to_asset_id"],
                dependency["dependency_type"],
            ),
            "run_id": run_id,
            "from_asset_id": dependency["from_asset_id"],
            "to_asset_id": dependency["to_asset_id"],
            "dependency_type": dependency["dependency_type"],
            "evidence": dependency.get("evidence"),
            "confidence": dependency.get("confidence"),
            "discovered_at": dependency.get("discovered_at"),
        }
        for dependency in dependencies
    ]

    source_systems = sorted(
        {
            asset.get("source_system")
            for asset in assets
            if asset.get("source_system")
        }
    )
    target_patterns = sorted(
        {
            row.get("target_pattern")
            for row in blueprint
            if row.get("target_pattern")
        }
    )

    return Neo4jGraphPayload(
        run={
            "run_id": run_id,
            "source_roots": source_roots,
            "asset_count": len(graph_assets),
            "dependency_count": len(graph_relationships),
            "source_system_count": len(source_systems),
            "target_pattern_count": len(target_patterns),
        },
        assets=graph_assets,
        relationships=graph_relationships,
        source_systems=[{"name": name} for name in source_systems],
        target_patterns=[{"name": name} for name in target_patterns],
    )


def publish_neo4j_payload(
    *,
    uri: str,
    username: str,
    password: str,
    database: str,
    payload: Neo4jGraphPayload,
    replace_run: bool = True,
) -> dict[str, int]:
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            session.execute_write(_ensure_constraints)
            if replace_run:
                session.execute_write(_clear_run, payload.run["run_id"])
            session.execute_write(_merge_run, payload.run)
            session.execute_write(_merge_source_systems, payload.source_systems)
            session.execute_write(_merge_target_patterns, payload.target_patterns)
            session.execute_write(_merge_assets, payload.assets)
            session.execute_write(_merge_relationships, payload.relationships)
            return session.execute_read(_graph_counts, payload.run["run_id"])
    finally:
        driver.close()


def _ensure_constraints(tx) -> None:
    constraints = [
        "CREATE CONSTRAINT mma_run_id IF NOT EXISTS FOR (r:MigrationRun) REQUIRE r.run_id IS UNIQUE",
        "CREATE CONSTRAINT mma_asset_id IF NOT EXISTS FOR (a:MigrationAsset) REQUIRE a.asset_id IS UNIQUE",
        "CREATE CONSTRAINT mma_source_system IF NOT EXISTS FOR (s:SourceSystem) REQUIRE s.name IS UNIQUE",
        "CREATE CONSTRAINT mma_target_pattern IF NOT EXISTS FOR (p:TargetPattern) REQUIRE p.name IS UNIQUE",
    ]
    for statement in constraints:
        tx.run(statement).consume()


def _clear_run(tx, run_id: str) -> None:
    tx.run(
        """
        MATCH (:MigrationRun {run_id: $run_id})-[r:INCLUDES_ASSET]->()
        DELETE r
        """,
        run_id=run_id,
    ).consume()
    tx.run(
        """
        MATCH ()-[r:MIGRATION_DEPENDENCY {run_id: $run_id}]->()
        DELETE r
        """,
        run_id=run_id,
    ).consume()
    tx.run(
        """
        MATCH (r:MigrationRun {run_id: $run_id})
        DELETE r
        """,
        run_id=run_id,
    ).consume()


def _merge_run(tx, run: dict[str, Any]) -> None:
    tx.run(
        """
        MERGE (r:MigrationRun {run_id: $run.run_id})
        SET r += $run
        """,
        run=run,
    ).consume()


def _merge_source_systems(tx, source_systems: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (s:SourceSystem {name: row.name})
        SET s.last_seen_at = datetime()
        """,
        rows=source_systems,
    ).consume()


def _merge_target_patterns(tx, target_patterns: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (p:TargetPattern {name: row.name})
        SET p.last_seen_at = datetime()
        """,
        rows=target_patterns,
    ).consume()


def _merge_assets(tx, assets: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MERGE (a:MigrationAsset {asset_id: row.asset_id})
        SET a += row
        WITH a, row
        MATCH (r:MigrationRun {run_id: row.run_id})
        MERGE (r)-[:INCLUDES_ASSET]->(a)
        WITH a, row
        MATCH (s:SourceSystem {name: row.source_system})
        MERGE (a)-[:FROM_SOURCE_SYSTEM]->(s)
        """,
        rows=assets,
    ).consume()
    tx.run(
        """
        UNWIND [row IN $rows WHERE row.target_pattern IS NOT NULL] AS row
        MATCH (a:MigrationAsset {asset_id: row.asset_id})
        MATCH (p:TargetPattern {name: row.target_pattern})
        MERGE (a)-[:HAS_TARGET_PATTERN]->(p)
        """,
        rows=assets,
    ).consume()


def _merge_relationships(tx, relationships: list[dict[str, Any]]) -> None:
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (from:MigrationAsset {asset_id: row.from_asset_id})
        MATCH (to:MigrationAsset {asset_id: row.to_asset_id})
        MERGE (from)-[r:MIGRATION_DEPENDENCY {relationship_id: row.relationship_id}]->(to)
        SET r += row
        """,
        rows=relationships,
    ).consume()


def _graph_counts(tx, run_id: str) -> dict[str, int]:
    record = tx.run(
        """
        MATCH (r:MigrationRun {run_id: $run_id})
        OPTIONAL MATCH (r)-[:INCLUDES_ASSET]->(a:MigrationAsset)
        WITH r, count(DISTINCT a) AS assets
        OPTIONAL MATCH ()-[d:MIGRATION_DEPENDENCY {run_id: $run_id}]->()
        WITH r, assets, count(DISTINCT d) AS dependencies
        OPTIONAL MATCH (s:SourceSystem)
        WITH r, assets, dependencies, count(DISTINCT s) AS source_systems
        OPTIONAL MATCH (p:TargetPattern)
        RETURN assets, dependencies, source_systems, count(DISTINCT p) AS target_patterns
        """,
        run_id=run_id,
    ).single()
    if record is None:
        return {"assets": 0, "dependencies": 0, "source_systems": 0, "target_patterns": 0}
    return {
        "assets": int(record["assets"]),
        "dependencies": int(record["dependencies"]),
        "source_systems": int(record["source_systems"]),
        "target_patterns": int(record["target_patterns"]),
    }
