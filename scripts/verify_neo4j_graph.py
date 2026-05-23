from __future__ import annotations

import os
import sys
from pathlib import Path


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def main() -> int:
    load_env_file(Path(".env"))
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("Neo4j Python driver is not installed. Run setup with graph deps.", file=sys.stderr)
        return 2

    uri = require_env("NEO4J_URI")
    username = require_env("NEO4J_USERNAME")
    password = require_env("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        with driver.session(database=database) as session:
            record = session.run(
                """
                MATCH (r:MigrationRun)
                WITH r
                ORDER BY r.run_id DESC
                LIMIT 1
                OPTIONAL MATCH (r)-[:INCLUDES_ASSET]->(a:MigrationAsset)
                WITH r, count(DISTINCT a) AS assets
                OPTIONAL MATCH ()-[d:MIGRATION_DEPENDENCY {run_id: r.run_id}]->()
                WITH r, assets, count(DISTINCT d) AS dependencies
                OPTIONAL MATCH (s:SourceSystem)
                WITH r, assets, dependencies, count(DISTINCT s) AS source_systems
                OPTIONAL MATCH (p:TargetPattern)
                RETURN
                    r.run_id AS run_id,
                    assets,
                    dependencies,
                    source_systems,
                    count(DISTINCT p) AS target_patterns
                """
            ).single()
    finally:
        driver.close()

    if record is None:
        print("No MigrationRun nodes found.")
        return 1
    print(dict(record))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
