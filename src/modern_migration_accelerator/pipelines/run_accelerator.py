from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from modern_migration_accelerator.discovery import TextDocument, load_text_documents
from modern_migration_accelerator.parsers.sql import extract_sql_references


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: object) -> str:
    raw = "|".join(str(part).strip().lower() for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("Databricks identifiers cannot be empty.")
    return f"`{identifier.replace('`', '``')}`"


def table_name(catalog: str, schema: str, table: str) -> str:
    return ".".join(quote_identifier(part) for part in (catalog, schema, table))


def default_source_root() -> str:
    return str(Path(__file__).resolve().parents[3] / "samples" / "legacy_metadata")


def safe_object_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", value.lower()).strip("_")
    return cleaned[:120] or "legacy_asset"


def normalize_asset_type(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "asset"


def as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).replace(",", "").strip())
    except ValueError:
        return None


def add_asset(assets: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    existing = assets.get(row["asset_id"])
    if existing is None:
        assets[row["asset_id"]] = row
        return

    for key in ("owner", "criticality", "row_count", "metadata_json"):
        if existing.get(key) in (None, "", "{}") and row.get(key) not in (None, "", "{}"):
            existing[key] = row[key]


def add_dependency(
    dependencies: list[dict[str, Any]],
    seen: set[tuple[str, str, str]],
    row: dict[str, Any],
) -> None:
    key = (row["from_asset_id"], row["to_asset_id"], row["dependency_type"])
    if key in seen:
        return
    seen.add(key)
    dependencies.append(row)


def parse_adf_document(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    payload = json.loads(document.content)
    pipelines = payload if isinstance(payload, list) else [payload]

    for pipeline in pipelines:
        if not isinstance(pipeline, dict):
            continue
        properties = pipeline.get("properties", {})
        activities = properties.get("activities", [])
        pipeline_name = pipeline.get("name") or Path(document.path).stem
        pipeline_id = stable_id("azure_data_factory", "pipeline", pipeline_name)

        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": pipeline_id,
                "source_system": "azure_data_factory",
                "asset_type": "adf_pipeline",
                "asset_name": pipeline_name,
                "platform": "Azure",
                "technology": "Azure Data Factory",
                "raw_path": document.path,
                "owner": properties.get("folder", {}).get("name"),
                "criticality": properties.get("annotations", [None])[0]
                if properties.get("annotations")
                else None,
                "row_count": None,
                "metadata_json": json.dumps(
                    {"activity_count": len(activities), "parameters": properties.get("parameters", {})},
                    sort_keys=True,
                ),
                "discovered_at": discovered_at,
            },
        )

        for activity in activities:
            activity_name = activity.get("name", "unnamed_activity")
            activity_id = stable_id("azure_data_factory", "activity", pipeline_name, activity_name)
            add_asset(
                assets,
                {
                    "run_id": run_id,
                    "asset_id": activity_id,
                    "source_system": "azure_data_factory",
                    "asset_type": "adf_activity",
                    "asset_name": f"{pipeline_name}.{activity_name}",
                    "platform": "Azure",
                    "technology": f"ADF {activity.get('type', 'Activity')}",
                    "raw_path": document.path,
                    "owner": None,
                    "criticality": None,
                    "row_count": None,
                    "metadata_json": json.dumps(activity, sort_keys=True),
                    "discovered_at": discovered_at,
                },
            )
            add_dependency(
                dependencies,
                dependency_keys,
                {
                    "run_id": run_id,
                    "from_asset_id": pipeline_id,
                    "to_asset_id": activity_id,
                    "dependency_type": "orchestrates",
                    "evidence": f"ADF pipeline activity: {activity_name}",
                    "confidence": 1.0,
                    "discovered_at": discovered_at,
                },
            )

            for direction, dependency_type in (("inputs", "reads"), ("outputs", "writes")):
                for ref in activity.get(direction, []) or []:
                    ref_name = ref.get("referenceName") if isinstance(ref, dict) else None
                    if not ref_name:
                        continue
                    dataset_id = stable_id("azure_data_factory", "dataset", ref_name)
                    add_asset(
                        assets,
                        {
                            "run_id": run_id,
                            "asset_id": dataset_id,
                            "source_system": "azure_data_factory",
                            "asset_type": "adf_dataset",
                            "asset_name": ref_name,
                            "platform": "Azure",
                            "technology": "ADF Dataset",
                            "raw_path": document.path,
                            "owner": None,
                            "criticality": None,
                            "row_count": None,
                            "metadata_json": json.dumps(ref, sort_keys=True),
                            "discovered_at": discovered_at,
                        },
                    )
                    add_dependency(
                        dependencies,
                        dependency_keys,
                        {
                            "run_id": run_id,
                            "from_asset_id": activity_id,
                            "to_asset_id": dataset_id,
                            "dependency_type": dependency_type,
                            "evidence": f"ADF {direction} reference: {ref_name}",
                            "confidence": 0.9,
                            "discovered_at": discovered_at,
                        },
                    )


def parse_synapse_csv(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    reader = csv.DictReader(io.StringIO(document.content))
    for row in reader:
        normalized = {
            str(key).strip().lower(): str(value).strip() if value is not None else None
            for key, value in row.items()
            if key
        }
        database = normalized.get("database") or normalized.get("db") or "legacy"
        schema = normalized.get("schema") or normalized.get("schema_name") or "dbo"
        object_type = normalize_asset_type(normalized.get("object_type") or "table")
        object_value = (
            normalized.get("table")
            or normalized.get("object_name")
            or normalized.get("notebook_name")
            or normalized.get("pipeline_name")
        )

        if object_type in {"database", "serverless_database"}:
            object_name = database
        elif object_value:
            object_name = f"{database}.{schema}.{object_value}"
        else:
            continue

        source_system = normalized.get("source_system") or "azure_synapse"
        technology = normalized.get("engine") or normalized.get("technology") or "Azure Synapse Analytics"
        asset_id = stable_id(source_system, object_type, object_name)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "source_system": source_system,
                "asset_type": f"synapse_{object_type}",
                "asset_name": object_name,
                "platform": "Azure",
                "technology": technology,
                "raw_path": document.path,
                "owner": normalized.get("owner"),
                "criticality": normalized.get("criticality"),
                "row_count": as_int(normalized.get("row_count")),
                "metadata_json": json.dumps(normalized, sort_keys=True),
                "discovered_at": discovered_at,
            },
        )

        for raw_dependency in re.split(r"[|;]", normalized.get("depends_on") or ""):
            dependency_name = raw_dependency.strip()
            if not dependency_name:
                continue
            dependency_id = stable_id(source_system, "dependency_reference", dependency_name)
            add_asset(
                assets,
                {
                    "run_id": run_id,
                    "asset_id": dependency_id,
                    "source_system": source_system,
                    "asset_type": "synapse_dependency_reference",
                    "asset_name": dependency_name,
                    "platform": "Azure",
                    "technology": "Dependency reference",
                    "raw_path": document.path,
                    "owner": None,
                    "criticality": None,
                    "row_count": None,
                    "metadata_json": json.dumps({"referenced_by": object_name}, sort_keys=True),
                    "discovered_at": discovered_at,
                },
            )
            add_dependency(
                dependencies,
                dependency_keys,
                {
                    "run_id": run_id,
                    "from_asset_id": asset_id,
                    "to_asset_id": dependency_id,
                    "dependency_type": "depends_on",
                    "evidence": f"Inventory dependency: {dependency_name}",
                    "confidence": 0.8,
                    "discovered_at": discovered_at,
                },
            )


def parse_sql_document(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    script_name = Path(document.path).name
    script_id = stable_id("legacy_sql", "script", script_name)
    add_asset(
        assets,
        {
            "run_id": run_id,
            "asset_id": script_id,
            "source_system": "legacy_sql",
            "asset_type": "sql_script",
            "asset_name": script_name,
            "platform": "Legacy SQL",
            "technology": "T-SQL",
            "raw_path": document.path,
            "owner": None,
            "criticality": None,
            "row_count": None,
            "metadata_json": json.dumps({"reference_count": 0}, sort_keys=True),
            "discovered_at": discovered_at,
        },
    )

    references = extract_sql_references(document.content)
    assets[script_id]["metadata_json"] = json.dumps(
        {"reference_count": len(references), "references": references},
        sort_keys=True,
    )

    for reference in references:
        referenced_id = stable_id("legacy_sql", "referenced_object", reference)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": referenced_id,
                "source_system": "legacy_sql",
                "asset_type": "sql_referenced_object",
                "asset_name": reference,
                "platform": "Legacy SQL",
                "technology": "SQL object reference",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": json.dumps({"referenced_by": script_name}, sort_keys=True),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": script_id,
                "to_asset_id": referenced_id,
                "dependency_type": "references",
                "evidence": f"SQL object reference: {reference}",
                "confidence": 0.75,
                "discovered_at": discovered_at,
            },
        )


def parse_notebook_document(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    notebook_name = Path(document.path).name
    notebook_id = stable_id("azure_synapse", "notebook", notebook_name)
    language = "unknown"
    source_text = document.content

    try:
        payload = json.loads(document.content)
        language = payload.get("metadata", {}).get("language_info", {}).get("name", "unknown")
        cell_sources = []
        for cell in payload.get("cells", []):
            source = cell.get("source", [])
            if isinstance(source, list):
                cell_sources.append("".join(source))
            elif isinstance(source, str):
                cell_sources.append(source)
        source_text = "\n".join(cell_sources)
    except json.JSONDecodeError:
        payload = {"parse_warning": "notebook_json_decode_failed"}

    references = extract_sql_references(source_text)
    add_asset(
        assets,
        {
            "run_id": run_id,
            "asset_id": notebook_id,
            "source_system": "azure_synapse",
            "asset_type": "synapse_notebook",
            "asset_name": notebook_name,
            "platform": "Azure",
            "technology": f"Synapse Notebook ({language})",
            "raw_path": document.path,
            "owner": None,
            "criticality": None,
            "row_count": None,
            "metadata_json": json.dumps(
                {
                    "reference_count": len(references),
                    "references": references,
                    "notebook_metadata": payload.get("metadata", {}),
                },
                sort_keys=True,
            ),
            "discovered_at": discovered_at,
        },
    )

    for reference in references:
        referenced_id = stable_id("azure_synapse", "notebook_reference", reference)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": referenced_id,
                "source_system": "azure_synapse",
                "asset_type": "synapse_notebook_reference",
                "asset_name": reference,
                "platform": "Azure",
                "technology": "Notebook SQL reference",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": json.dumps({"referenced_by": notebook_name}, sort_keys=True),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": notebook_id,
                "to_asset_id": referenced_id,
                "dependency_type": "references",
                "evidence": f"Notebook SQL reference: {reference}",
                "confidence": 0.7,
                "discovered_at": discovered_at,
            },
        )


def parse_documents(
    documents: list[TextDocument],
    run_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    discovered_at = utc_now()
    raw_rows: list[dict[str, Any]] = []
    assets: dict[str, dict[str, Any]] = {}
    dependencies: list[dict[str, Any]] = []
    dependency_keys: set[tuple[str, str, str]] = set()

    for document in documents:
        raw_rows.append(
            {
                "run_id": run_id,
                "source_path": document.path,
                "source_format": document.extension.lstrip("."),
                "source_system": infer_source_system(document),
                "ingested_at": discovered_at,
                "content_hash": content_hash(document.content),
                "raw_content": document.content,
            }
        )

        if document.extension == ".json":
            parse_adf_document(document, run_id, discovered_at, assets, dependencies, dependency_keys)
        elif document.extension == ".csv":
            parse_synapse_csv(document, run_id, discovered_at, assets, dependencies, dependency_keys)
        elif document.extension == ".ipynb":
            parse_notebook_document(
                document,
                run_id,
                discovered_at,
                assets,
                dependencies,
                dependency_keys,
            )
        elif document.extension == ".sql":
            parse_sql_document(document, run_id, discovered_at, assets, dependencies, dependency_keys)

    return raw_rows, list(assets.values()), dependencies


def infer_source_system(document: TextDocument) -> str:
    if document.extension == ".json":
        return "azure_data_factory"
    if document.extension == ".csv":
        return "azure_synapse"
    if document.extension == ".ipynb":
        return "azure_synapse"
    if document.extension == ".sql":
        return "legacy_sql"
    return "legacy"


def risk_level(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def build_risk_register(
    assets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    dependency_counts = Counter()
    for dependency in dependencies:
        dependency_counts[dependency["from_asset_id"]] += 1
        dependency_counts[dependency["to_asset_id"]] += 1

    rows = []
    for asset in assets:
        score = 20.0
        factors = []
        criticality = (asset.get("criticality") or "").lower()
        dependency_count = dependency_counts[asset["asset_id"]]
        row_count = asset.get("row_count") or 0

        if criticality in {"critical", "high", "tier1", "p1"}:
            score += 30
            factors.append("business critical")
        elif criticality in {"medium", "tier2", "p2"}:
            score += 15
            factors.append("medium criticality")

        if dependency_count > 5:
            score += 20
            factors.append("many dependencies")
        elif dependency_count > 2:
            score += 10
            factors.append("multiple dependencies")

        if row_count > 1_000_000_000:
            score += 20
            factors.append("very large data volume")
        elif row_count > 10_000_000:
            score += 10
            factors.append("large data volume")

        if asset["asset_type"] in {"adf_pipeline", "sql_script", "synapse_notebook"}:
            score += 10
            factors.append("requires orchestration or code migration")
        if asset["asset_type"] in {"synapse_external_table", "synapse_serverless_database"}:
            score += 10
            factors.append("external storage and security mapping required")

        score = min(score, 100.0)
        level = risk_level(score)
        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset["asset_id"],
                "asset_name": asset["asset_name"],
                "asset_type": asset["asset_type"],
                "risk_score": score,
                "risk_level": level,
                "risk_factors": factors or ["baseline migration assessment"],
                "recommended_action": recommendation_for(level),
                "generated_at": generated_at,
            }
        )
    return rows


def recommendation_for(level: str) -> str:
    if level == "high":
        return "Prioritize detailed assessment, dependency validation and cutover rehearsal."
    if level == "medium":
        return "Plan targeted refactoring and data quality validation before migration."
    return "Candidate for standard migration pattern with automated validation."


def build_blueprint(
    assets: list[dict[str, Any]],
    run_id: str,
    catalog: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    rows = []
    for asset in assets:
        asset_type = asset["asset_type"]
        if asset_type in {
            "synapse_external_table",
            "synapse_notebook_reference",
            "synapse_table",
            "synapse_view",
            "sql_referenced_object",
        }:
            target_pattern = "Unity Catalog Delta table"
            target_schema = "silver"
            notes = [
                "Profile schema and row counts before load.",
                "Land raw extracts in bronze before curated Delta publication.",
            ]
        elif asset_type == "synapse_serverless_database":
            target_pattern = "Unity Catalog catalog/schema assessment"
            target_schema = "control"
            notes = [
                "Inventory serverless database schemas, external locations and security boundaries.",
                "Map database ownership to Unity Catalog catalog and schema conventions.",
            ]
        elif asset_type == "synapse_notebook":
            target_pattern = "Databricks notebook or Lakeflow task"
            target_schema = "workflows"
            notes = [
                "Port Spark and SQL cells to Databricks notebooks.",
                "Replace Synapse-specific utilities and linked service references.",
            ]
        elif asset_type == "adf_pipeline":
            target_pattern = "Databricks Lakeflow Job"
            target_schema = "workflows"
            notes = [
                "Convert pipeline orchestration to Databricks job tasks.",
                "Keep task parameters explicit and environment driven.",
            ]
        elif asset_type == "adf_activity":
            target_pattern = "Databricks job task or notebook task"
            target_schema = "workflows"
            notes = ["Map activity type to an equivalent Databricks task implementation."]
        elif asset_type == "sql_script":
            target_pattern = "Databricks SQL or PySpark transformation"
            target_schema = "workflows"
            notes = [
                "Refactor platform-specific T-SQL functions.",
                "Validate dependencies against Unity Catalog objects.",
            ]
        else:
            target_pattern = "Migration support asset"
            target_schema = "bronze"
            notes = ["Keep as supporting metadata until target ownership is confirmed."]

        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset["asset_id"],
                "asset_name": asset["asset_name"],
                "legacy_asset_type": asset_type,
                "target_pattern": target_pattern,
                "target_catalog": catalog,
                "target_schema": target_schema,
                "target_object": safe_object_name(asset["asset_name"]),
                "migration_notes": notes,
                "generated_at": generated_at,
            }
        )
    return rows


def build_data_quality_plan(
    assets: list[dict[str, Any]],
    run_id: str,
    catalog: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    rows = []
    for asset in assets:
        target_table = f"{catalog}.silver.{safe_object_name(asset['asset_name'])}"
        if asset["asset_type"] in {
            "synapse_external_table",
            "synapse_notebook_reference",
            "synapse_table",
            "synapse_view",
            "sql_referenced_object",
        }:
            checks = [
                ("row_count_reconciliation", "completeness", "error", "Compare source and Delta row counts."),
                ("schema_compatibility", "schema", "error", "Validate column names and compatible data types."),
                ("nullability_profile", "quality", "warning", "Profile null rates for business columns."),
            ]
        elif asset["asset_type"] == "synapse_serverless_database":
            checks = [
                (
                    "external_location_access",
                    "security",
                    "error",
                    "Confirm storage credentials and external locations are mapped to Unity Catalog.",
                ),
                (
                    "object_inventory_completeness",
                    "metadata",
                    "error",
                    "Confirm serverless views and external tables are fully inventoried.",
                ),
            ]
        else:
            checks = [
                (
                    "dependency_resolution",
                    "lineage",
                    "error",
                    "Confirm all upstream and downstream dependencies are mapped.",
                )
            ]

        for check_name, check_type, severity, rule_description in checks:
            rows.append(
                {
                    "run_id": run_id,
                    "asset_id": asset["asset_id"],
                    "asset_name": asset["asset_name"],
                    "check_name": check_name,
                    "check_type": check_type,
                    "severity": severity,
                    "rule_description": rule_description,
                    "target_table": target_table,
                    "generated_at": generated_at,
                }
            )
    return rows


def schemas():
    from pyspark.sql.types import (
        ArrayType,
        DoubleType,
        LongType,
        StringType,
        StructField,
        StructType,
    )

    return {
        "raw_metadata": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("source_path", StringType(), False),
                StructField("source_format", StringType(), False),
                StructField("source_system", StringType(), False),
                StructField("ingested_at", StringType(), False),
                StructField("content_hash", StringType(), False),
                StructField("raw_content", StringType(), True),
            ]
        ),
        "assets": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("source_system", StringType(), False),
                StructField("asset_type", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("platform", StringType(), True),
                StructField("technology", StringType(), True),
                StructField("raw_path", StringType(), True),
                StructField("owner", StringType(), True),
                StructField("criticality", StringType(), True),
                StructField("row_count", LongType(), True),
                StructField("metadata_json", StringType(), True),
                StructField("discovered_at", StringType(), False),
            ]
        ),
        "dependencies": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("from_asset_id", StringType(), False),
                StructField("to_asset_id", StringType(), False),
                StructField("dependency_type", StringType(), False),
                StructField("evidence", StringType(), True),
                StructField("confidence", DoubleType(), False),
                StructField("discovered_at", StringType(), False),
            ]
        ),
        "risk_register": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("asset_type", StringType(), False),
                StructField("risk_score", DoubleType(), False),
                StructField("risk_level", StringType(), False),
                StructField("risk_factors", ArrayType(StringType()), False),
                StructField("recommended_action", StringType(), False),
                StructField("generated_at", StringType(), False),
            ]
        ),
        "target_databricks_blueprint": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("legacy_asset_type", StringType(), False),
                StructField("target_pattern", StringType(), False),
                StructField("target_catalog", StringType(), False),
                StructField("target_schema", StringType(), False),
                StructField("target_object", StringType(), False),
                StructField("migration_notes", ArrayType(StringType()), False),
                StructField("generated_at", StringType(), False),
            ]
        ),
        "data_quality_plan": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("check_name", StringType(), False),
                StructField("check_type", StringType(), False),
                StructField("severity", StringType(), False),
                StructField("rule_description", StringType(), False),
                StructField("target_table", StringType(), False),
                StructField("generated_at", StringType(), False),
            ]
        ),
        "metadata_snapshots": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("snapshot_ts", StringType(), False),
                StructField("source_root", StringType(), False),
                StructField("asset_count", LongType(), False),
                StructField("dependency_count", LongType(), False),
                StructField("high_risk_count", LongType(), False),
                StructField("blueprint_count", LongType(), False),
            ]
        ),
        "run_log": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("status", StringType(), False),
                StructField("started_at", StringType(), False),
                StructField("ended_at", StringType(), False),
                StructField("duration_seconds", DoubleType(), False),
                StructField("source_root", StringType(), False),
                StructField("target_catalog", StringType(), False),
                StructField("error_message", StringType(), True),
                StructField("metrics_json", StringType(), False),
            ]
        ),
    }


def ensure_database_objects(spark, catalog: str, schema_names: list[str]) -> None:
    if catalog.lower() != "hive_metastore":
        spark.sql(f"CREATE CATALOG IF NOT EXISTS {quote_identifier(catalog)}")
    for schema_name in schema_names:
        spark.sql(
            f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(catalog)}.{quote_identifier(schema_name)}"
        )


def write_table(spark, rows: list[dict[str, Any]], schema, full_table_name: str, mode: str) -> None:
    dataframe = spark.createDataFrame(rows, schema=schema)
    writer = dataframe.write.format("delta").mode(mode)
    if mode == "overwrite":
        writer = writer.option("overwriteSchema", "true")
    else:
        writer = writer.option("mergeSchema", "true")
    writer.saveAsTable(full_table_name)


def get_spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.appName("modern-migration-accelerator").getOrCreate()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Databricks migration accelerator MVP.")
    parser.add_argument("--catalog", default="migration_accelerator_dev")
    parser.add_argument("--source-root", default=default_source_root())
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--bronze-schema", default="bronze")
    parser.add_argument("--silver-schema", default="silver")
    parser.add_argument("--gold-schema", default="gold")
    parser.add_argument("--control-schema", default="control")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    started_at = utc_now()
    start = datetime.now(timezone.utc)
    run_id = args.run_id or f"run_{start.strftime('%Y%m%d_%H%M%S')}"
    spark = get_spark()
    table_schemas = schemas()

    ensure_database_objects(
        spark,
        args.catalog,
        [args.bronze_schema, args.silver_schema, args.gold_schema, args.control_schema],
    )

    try:
        documents = load_text_documents(args.source_root, spark=spark)
        if not documents:
            raise ValueError(f"No supported metadata files found in {args.source_root}")

        raw_rows, assets, dependencies = parse_documents(documents, run_id)
        risk_register = build_risk_register(assets, dependencies, run_id)
        blueprint = build_blueprint(assets, run_id, args.catalog)
        dq_plan = build_data_quality_plan(assets, run_id, args.catalog)
        high_risk_count = sum(1 for row in risk_register if row["risk_level"] == "high")
        snapshot = [
            {
                "run_id": run_id,
                "snapshot_ts": utc_now(),
                "source_root": args.source_root,
                "asset_count": len(assets),
                "dependency_count": len(dependencies),
                "high_risk_count": high_risk_count,
                "blueprint_count": len(blueprint),
            }
        ]

        write_table(
            spark,
            raw_rows,
            table_schemas["raw_metadata"],
            table_name(args.catalog, args.bronze_schema, "raw_metadata"),
            "overwrite",
        )
        write_table(
            spark,
            assets,
            table_schemas["assets"],
            table_name(args.catalog, args.silver_schema, "assets"),
            "overwrite",
        )
        write_table(
            spark,
            dependencies,
            table_schemas["dependencies"],
            table_name(args.catalog, args.silver_schema, "dependencies"),
            "overwrite",
        )
        write_table(
            spark,
            risk_register,
            table_schemas["risk_register"],
            table_name(args.catalog, args.gold_schema, "risk_register"),
            "overwrite",
        )
        write_table(
            spark,
            blueprint,
            table_schemas["target_databricks_blueprint"],
            table_name(args.catalog, args.gold_schema, "target_databricks_blueprint"),
            "overwrite",
        )
        write_table(
            spark,
            dq_plan,
            table_schemas["data_quality_plan"],
            table_name(args.catalog, args.gold_schema, "data_quality_plan"),
            "overwrite",
        )
        write_table(
            spark,
            snapshot,
            table_schemas["metadata_snapshots"],
            table_name(args.catalog, args.control_schema, "metadata_snapshots"),
            "append",
        )

        metrics = {
            "raw_documents": len(raw_rows),
            "assets": len(assets),
            "dependencies": len(dependencies),
            "risk_register_rows": len(risk_register),
            "blueprint_rows": len(blueprint),
            "data_quality_plan_rows": len(dq_plan),
            "high_risk_count": high_risk_count,
        }
        status = "SUCCESS"
        error_message = None
    except Exception as exc:
        metrics = {}
        status = "FAILED"
        error_message = str(exc)
        raise
    finally:
        ended_at = utc_now()
        duration = (datetime.now(timezone.utc) - start).total_seconds()
        write_table(
            spark,
            [
                {
                    "run_id": run_id,
                    "status": status,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "duration_seconds": duration,
                    "source_root": args.source_root,
                    "target_catalog": args.catalog,
                    "error_message": error_message,
                    "metrics_json": json.dumps(metrics, sort_keys=True),
                }
            ],
            table_schemas["run_log"],
            table_name(args.catalog, args.control_schema, "run_log"),
            "append",
        )


if __name__ == "__main__":
    main()
