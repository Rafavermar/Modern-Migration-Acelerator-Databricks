from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from modern_migration_accelerator.discovery import load_text_documents
from modern_migration_accelerator.neo4j_graph import build_neo4j_payload, publish_neo4j_payload
from modern_migration_accelerator.pipelines.run_accelerator import (
    build_asset_priority_matrix,
    build_blueprint,
    build_data_quality_plan,
    build_graph_edges,
    build_risk_register,
    parse_documents,
)


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


def default_source_roots() -> list[str]:
    roots = ["samples/legacy_metadata"]
    local_outputs = Path("local_outputs/legacy_metadata")
    if local_outputs.exists():
        roots.append(str(local_outputs))
    return roots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish the migration dependency graph to Neo4j.")
    parser.add_argument(
        "--source-root",
        action="append",
        default=[],
        help="Metadata root to parse. Can be provided multiple times. Defaults to samples plus local SQL Server outputs when present.",
    )
    parser.add_argument("--catalog", default=os.environ.get("DATABRICKS_CATALOG", "migration_accelerator_dev"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-replace-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    os.chdir(ROOT)
    load_env_file(Path(".env"))
    args = parse_args()
    run_id = args.run_id or f"neo4j_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    source_roots = args.source_root or default_source_roots()

    documents = []
    for source_root in source_roots:
        documents.extend(load_text_documents(source_root))
    if not documents:
        raise ValueError(f"No supported metadata files found in: {source_roots}")

    raw_rows, assets, dependencies = parse_documents(documents, run_id)
    risk_register = build_risk_register(assets, dependencies, run_id)
    blueprint = build_blueprint(assets, run_id, args.catalog)
    data_quality_plan = build_data_quality_plan(assets, run_id, args.catalog)
    graph_edges = build_graph_edges(assets, dependencies, run_id)
    asset_priority_matrix = build_asset_priority_matrix(
        assets,
        dependencies,
        risk_register,
        blueprint,
        data_quality_plan,
        run_id,
    )

    payload = build_neo4j_payload(
        run_id=run_id,
        source_roots=source_roots,
        assets=assets,
        dependencies=dependencies,
        risk_register=risk_register,
        blueprint=blueprint,
        data_quality_plan=data_quality_plan,
        asset_priority_matrix=asset_priority_matrix,
    )

    print(
        {
            "run_id": run_id,
            "documents": len(raw_rows),
            "assets": len(payload.assets),
            "dependencies": len(payload.relationships),
            "graph_edges": len(graph_edges),
            "source_roots": source_roots,
        }
    )
    if args.dry_run:
        return 0

    uri = require_env("NEO4J_URI")
    username = require_env("NEO4J_USERNAME")
    password = require_env("NEO4J_PASSWORD")
    database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    counts = publish_neo4j_payload(
        uri=uri,
        username=username,
        password=password,
        database=database,
        payload=payload,
        replace_run=not args.no_replace_run,
    )
    print({"neo4j_database": database, "published": counts})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
