from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modern_migration_accelerator.xlsx import parse_xlsx_text_sheets, rows_as_dicts, xlsx_bytes_to_text

SCRIPT_PATH = globals().get("__file__") or globals().get("filename") or sys.argv[0]
SUPPORTED_EXTENSIONS = {".csv", ".ipynb", ".json", ".sql", ".xlsx"}
SPARK_FILE_PREFIXES = ("dbfs:/", "/Volumes/", "abfss://", "wasbs://", "s3://", "gs://")
REFERENCE_PATTERN = re.compile(
    r"""
    \b(
        from
        |join
        |into
        |update
        |merge\s+into
        |delete\s+from
        |truncate\s+table
    )\s+
    (?P<identifier>[`"\[\]A-Za-z0-9_.-]+)
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass(frozen=True)
class TextDocument:
    path: str
    content: str
    extension: str


def load_text_documents(source_root: str, spark=None) -> list[TextDocument]:
    normalized_root = source_root.rstrip("/")

    if normalized_root.startswith("/Workspace/"):
        raise ValueError(
            "Workspace Files are for bundle code, not metadata input. "
            "Upload metadata to /Volumes/<catalog>/landing/legacy_metadata/demo for dev "
            "or another Unity Catalog volume path for customer runs."
        )

    if normalized_root.startswith(SPARK_FILE_PREFIXES):
        if spark is None:
            raise ValueError(f"spark is required to read metadata source: {source_root}")
        return _load_text_documents_with_spark(normalized_root, spark)

    root = Path(source_root)
    if root.exists():
        documents: list[TextDocument] = []
        for file_path in sorted(root.rglob("*")):
            if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                extension = file_path.suffix.lower()
                if extension == ".xlsx":
                    content = xlsx_bytes_to_text(file_path.read_bytes())
                else:
                    content = file_path.read_text(encoding="utf-8")
                documents.append(
                    TextDocument(
                        path=str(file_path),
                        content=content,
                        extension=extension,
                    )
                )
        return documents

    if spark is None:
        raise FileNotFoundError(f"Metadata source root does not exist: {source_root}")

    return _load_text_documents_with_spark(source_root, spark)


def _load_text_documents_with_spark(source_root: str, spark) -> list[TextDocument]:
    dataframe = (
        spark.read.format("binaryFile")
        .option("recursiveFileLookup", "true")
        .load(source_root)
        .select("path", "content")
    )

    documents = []
    for row in dataframe.collect():
        extension = Path(row["path"]).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            continue
        content = bytes(row["content"])
        text = xlsx_bytes_to_text(content) if extension == ".xlsx" else content.decode("utf-8")
        documents.append(
            TextDocument(
                path=row["path"],
                content=text,
                extension=extension,
            )
        )
    return sorted(documents, key=lambda item: item.path)


def strip_sql_comments(sql_text: str) -> str:
    sql_text = re.sub(r"/\*.*?\*/", " ", sql_text, flags=re.DOTALL)
    return re.sub(r"--.*?$", " ", sql_text, flags=re.MULTILINE)


def normalize_sql_identifier(identifier: str) -> str:
    cleaned = identifier.strip().strip(";,.()")
    cleaned = cleaned.replace("[", "").replace("]", "")
    cleaned = cleaned.replace("`", "").replace('"', "")
    return re.sub(r"\s+", "", cleaned).lower()


def extract_sql_references(sql_text: str) -> list[str]:
    cleaned_sql = strip_sql_comments(sql_text)
    references: list[str] = []
    seen = set()

    for match in REFERENCE_PATTERN.finditer(cleaned_sql):
        reference = normalize_sql_identifier(match.group("identifier"))
        if not reference or reference.startswith(("#", "@")):
            continue
        if reference in {"select", "values", "with"}:
            continue
        if reference not in seen:
            seen.add(reference)
            references.append(reference)

    return references


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: object) -> str:
    raw = "|".join(str(part).strip().lower() for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


SENSITIVE_KEY_TERMS = ("password", "secret", "token", "key", "connectionstring", "sas")


def sanitized_json(value: Any) -> str:
    return json.dumps(redact_sensitive_values(value), sort_keys=True)


def redact_sensitive_values(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, nested_value in value.items():
            normalized_key = str(key).replace("_", "").lower()
            if any(term in normalized_key for term in SENSITIVE_KEY_TERMS):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = redact_sensitive_values(nested_value)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_values(item) for item in value]
    return value


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("Databricks identifiers cannot be empty.")
    return f"`{identifier.replace('`', '``')}`"


def table_name(catalog: str, schema: str, table: str) -> str:
    return ".".join(quote_identifier(part) for part in (catalog, schema, table))


def default_source_root() -> str:
    script_path = Path(SCRIPT_PATH).resolve()
    if len(script_path.parents) >= 4:
        return str(script_path.parents[3] / "samples" / "legacy_metadata")
    return "samples/legacy_metadata"


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


def classify_inventory_source(source_system: str, technology: str) -> tuple[str, str]:
    value = f"{source_system} {technology}".lower()
    if any(token in value for token in ("sql_server", "sqlserver", "sql server", "mssql")):
        return "sqlserver", "SQL Server"
    if "synapse" in value:
        return "synapse", "Azure"
    return normalize_asset_type(source_system) or "legacy_inventory", "Legacy"


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


def adf_resource_name(resource: dict[str, Any], fallback_path: str) -> str:
    name = resource.get("name") or Path(fallback_path).stem
    return str(name).split("/")[-1]


def adf_resource_kind(resource: dict[str, Any]) -> str:
    resource_type = str(resource.get("type") or "").lower()
    properties = resource.get("properties", {})
    if resource_type.endswith("/pipelines") or "activities" in properties:
        return "pipeline"
    if resource_type.endswith("/datasets") or "linkedServiceName" in properties:
        return "dataset"
    if resource_type.endswith("/linkedservices") or (
        "typeProperties" in properties and "connectVia" in properties
    ):
        return "linked_service"
    if resource_type.endswith("/triggers") or ("pipelines" in properties and "runtimeState" in properties):
        return "trigger"
    if "typeProperties" in properties and "type" in properties:
        return "linked_service"
    return "pipeline"


def parse_reference_name(reference: Any) -> str | None:
    if isinstance(reference, dict):
        return reference.get("referenceName") or reference.get("name")
    if isinstance(reference, str):
        return reference
    return None


def add_adf_linked_service_asset(
    name: str,
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    properties: dict[str, Any] | None = None,
) -> str:
    linked_service_id = stable_id("azure_data_factory", "linked_service", name)
    properties = properties or {}
    linked_service_type = properties.get("type") or "LinkedService"
    add_asset(
        assets,
        {
            "run_id": run_id,
            "asset_id": linked_service_id,
            "source_system": "azure_data_factory",
            "asset_type": "adf_linked_service",
            "asset_name": name,
            "platform": "Azure",
            "technology": f"ADF LinkedService {linked_service_type}",
            "raw_path": document.path,
            "owner": None,
            "criticality": None,
            "row_count": None,
            "metadata_json": sanitized_json(properties),
            "discovered_at": discovered_at,
        },
    )
    return linked_service_id


def add_adf_dataset_physical_reference(
    dataset_id: str,
    dataset_name: str,
    properties: dict[str, Any],
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    type_properties = properties.get("typeProperties", {})
    schema_name = type_properties.get("schema") or type_properties.get("schemaName")
    table_name = type_properties.get("table") or type_properties.get("tableName")
    if table_name:
        object_name = f"{schema_name}.{table_name}" if schema_name else str(table_name)
        object_id = stable_id("azure_data_factory", "data_object", object_name)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": object_id,
                "source_system": "azure_data_factory",
                "asset_type": "adf_data_object",
                "asset_name": object_name,
                "platform": "Azure",
                "technology": "ADF dataset table reference",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": sanitized_json({"dataset": dataset_name, "typeProperties": type_properties}),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": dataset_id,
                "to_asset_id": object_id,
                "dependency_type": "points_to",
                "evidence": f"ADF dataset table reference: {object_name}",
                "confidence": 0.85,
                "discovered_at": discovered_at,
            },
        )

    location = type_properties.get("location") or {}
    folder_path = location.get("folderPath") or type_properties.get("folderPath")
    file_name = location.get("fileName") or type_properties.get("fileName")
    if folder_path or file_name:
        path_name = "/".join(part.strip("/") for part in (str(folder_path or ""), str(file_name or "")) if part)
        path_id = stable_id("azure_data_factory", "storage_path", path_name)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": path_id,
                "source_system": "azure_data_factory",
                "asset_type": "adf_storage_path",
                "asset_name": path_name,
                "platform": "Azure",
                "technology": "ADF dataset storage path",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": sanitized_json({"dataset": dataset_name, "location": location}),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": dataset_id,
                "to_asset_id": path_id,
                "dependency_type": "points_to",
                "evidence": f"ADF dataset storage path: {path_name}",
                "confidence": 0.8,
                "discovered_at": discovered_at,
            },
        )


def parse_adf_dataset_resource(
    resource: dict[str, Any],
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> str:
    properties = resource.get("properties", {})
    dataset_name = adf_resource_name(resource, document.path)
    dataset_id = stable_id("azure_data_factory", "dataset", dataset_name)
    dataset_type = properties.get("type") or resource.get("type") or "Dataset"
    add_asset(
        assets,
        {
            "run_id": run_id,
            "asset_id": dataset_id,
            "source_system": "azure_data_factory",
            "asset_type": "adf_dataset",
            "asset_name": dataset_name,
            "platform": "Azure",
            "technology": f"ADF Dataset {dataset_type}",
            "raw_path": document.path,
            "owner": None,
            "criticality": None,
            "row_count": None,
            "metadata_json": sanitized_json(properties),
            "discovered_at": discovered_at,
        },
    )

    linked_service_name = parse_reference_name(properties.get("linkedServiceName"))
    if linked_service_name:
        linked_service_id = add_adf_linked_service_asset(
            linked_service_name,
            document,
            run_id,
            discovered_at,
            assets,
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": dataset_id,
                "to_asset_id": linked_service_id,
                "dependency_type": "uses_connection",
                "evidence": f"ADF dataset linked service: {linked_service_name}",
                "confidence": 0.9,
                "discovered_at": discovered_at,
            },
        )

    add_adf_dataset_physical_reference(
        dataset_id,
        dataset_name,
        properties,
        document,
        run_id,
        discovered_at,
        assets,
        dependencies,
        dependency_keys,
    )
    return dataset_id


def parse_adf_linked_service_resource(
    resource: dict[str, Any],
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
) -> str:
    return add_adf_linked_service_asset(
        adf_resource_name(resource, document.path),
        document,
        run_id,
        discovered_at,
        assets,
        resource.get("properties", {}),
    )


def parse_adf_trigger_resource(
    resource: dict[str, Any],
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> str:
    properties = resource.get("properties", {})
    trigger_name = adf_resource_name(resource, document.path)
    trigger_id = stable_id("azure_data_factory", "trigger", trigger_name)
    trigger_type = properties.get("type") or "Trigger"
    add_asset(
        assets,
        {
            "run_id": run_id,
            "asset_id": trigger_id,
            "source_system": "azure_data_factory",
            "asset_type": "adf_trigger",
            "asset_name": trigger_name,
            "platform": "Azure",
            "technology": f"ADF Trigger {trigger_type}",
            "raw_path": document.path,
            "owner": None,
            "criticality": None,
            "row_count": None,
            "metadata_json": sanitized_json(properties),
            "discovered_at": discovered_at,
        },
    )

    for pipeline_reference in properties.get("pipelines", []) or []:
        pipeline_name = parse_reference_name(pipeline_reference.get("pipelineReference"))
        if not pipeline_name:
            continue
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
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": sanitized_json({"referenced_by_trigger": trigger_name}),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": trigger_id,
                "to_asset_id": pipeline_id,
                "dependency_type": "triggers",
                "evidence": f"ADF trigger pipeline reference: {pipeline_name}",
                "confidence": 0.95,
                "discovered_at": discovered_at,
            },
        )
    return trigger_id


def parse_adf_document(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    payload = json.loads(document.content)
    if isinstance(payload, dict) and isinstance(payload.get("resources"), list):
        resources = payload["resources"]
    else:
        resources = payload if isinstance(payload, list) else [payload]

    for pipeline in resources:
        if not isinstance(pipeline, dict):
            continue
        kind = adf_resource_kind(pipeline)
        if kind == "dataset":
            parse_adf_dataset_resource(
                pipeline,
                document,
                run_id,
                discovered_at,
                assets,
                dependencies,
                dependency_keys,
            )
            continue
        if kind == "linked_service":
            parse_adf_linked_service_resource(pipeline, document, run_id, discovered_at, assets)
            continue
        if kind == "trigger":
            parse_adf_trigger_resource(
                pipeline,
                document,
                run_id,
                discovered_at,
                assets,
                dependencies,
                dependency_keys,
            )
            continue

        properties = pipeline.get("properties", {})
        activities = properties.get("activities", [])
        pipeline_name = adf_resource_name(pipeline, document.path)
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
                "metadata_json": sanitized_json(
                    {"activity_count": len(activities), "parameters": properties.get("parameters", {})},
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
                    "metadata_json": sanitized_json(activity),
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

            for upstream in activity.get("dependsOn", []) or []:
                upstream_name = upstream.get("activity") if isinstance(upstream, dict) else None
                if not upstream_name:
                    continue
                upstream_id = stable_id("azure_data_factory", "activity", pipeline_name, upstream_name)
                add_asset(
                    assets,
                    {
                        "run_id": run_id,
                        "asset_id": upstream_id,
                        "source_system": "azure_data_factory",
                        "asset_type": "adf_activity",
                        "asset_name": f"{pipeline_name}.{upstream_name}",
                        "platform": "Azure",
                        "technology": "ADF Activity",
                        "raw_path": document.path,
                        "owner": None,
                        "criticality": None,
                        "row_count": None,
                        "metadata_json": sanitized_json({"referenced_by_depends_on": activity_name}),
                        "discovered_at": discovered_at,
                    },
                )
                add_dependency(
                    dependencies,
                    dependency_keys,
                    {
                        "run_id": run_id,
                        "from_asset_id": activity_id,
                        "to_asset_id": upstream_id,
                        "dependency_type": "depends_on",
                        "evidence": f"ADF activity dependsOn: {upstream_name}",
                        "confidence": 0.95,
                        "discovered_at": discovered_at,
                    },
                )

            for direction, dependency_type in (("inputs", "reads"), ("outputs", "writes")):
                for ref in activity.get(direction, []) or []:
                    ref_name = parse_reference_name(ref)
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
                            "metadata_json": sanitized_json(ref),
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

            type_properties = activity.get("typeProperties", {})
            notebook_name = parse_reference_name(type_properties.get("notebook"))
            if notebook_name:
                notebook_id = stable_id("azure_synapse", "notebook", notebook_name)
                add_asset(
                    assets,
                    {
                        "run_id": run_id,
                        "asset_id": notebook_id,
                        "source_system": "azure_synapse",
                        "asset_type": "synapse_notebook",
                        "asset_name": notebook_name,
                        "platform": "Azure",
                        "technology": "Synapse Notebook",
                        "raw_path": document.path,
                        "owner": None,
                        "criticality": None,
                        "row_count": None,
                        "metadata_json": sanitized_json({"referenced_by_activity": activity_name}),
                        "discovered_at": discovered_at,
                    },
                )
                add_dependency(
                    dependencies,
                    dependency_keys,
                    {
                        "run_id": run_id,
                        "from_asset_id": activity_id,
                        "to_asset_id": notebook_id,
                        "dependency_type": "orchestrates",
                        "evidence": f"ADF activity notebook reference: {notebook_name}",
                        "confidence": 0.85,
                        "discovered_at": discovered_at,
                    },
                )

            stored_procedure_name = type_properties.get("storedProcedureName")
            if stored_procedure_name:
                procedure_id = stable_id("azure_data_factory", "data_object", stored_procedure_name)
                add_asset(
                    assets,
                    {
                        "run_id": run_id,
                        "asset_id": procedure_id,
                        "source_system": "azure_data_factory",
                        "asset_type": "adf_data_object",
                        "asset_name": stored_procedure_name,
                        "platform": "Azure",
                        "technology": "ADF stored procedure reference",
                        "raw_path": document.path,
                        "owner": None,
                        "criticality": None,
                        "row_count": None,
                        "metadata_json": sanitized_json({"referenced_by_activity": activity_name}),
                        "discovered_at": discovered_at,
                    },
                )
                add_dependency(
                    dependencies,
                    dependency_keys,
                    {
                        "run_id": run_id,
                        "from_asset_id": activity_id,
                        "to_asset_id": procedure_id,
                        "dependency_type": "references",
                        "evidence": f"ADF stored procedure reference: {stored_procedure_name}",
                        "confidence": 0.8,
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
        asset_prefix, platform = classify_inventory_source(source_system, technology)
        asset_id = stable_id(source_system, object_type, object_name)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": asset_id,
                "source_system": source_system,
                "asset_type": f"{asset_prefix}_{object_type}",
                "asset_name": object_name,
                "platform": platform,
                "technology": technology,
                "raw_path": document.path,
                "owner": normalized.get("owner"),
                "criticality": normalized.get("criticality"),
                "row_count": as_int(normalized.get("row_count")),
                "metadata_json": sanitized_json(normalized),
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
                    "asset_type": f"{asset_prefix}_dependency_reference",
                    "asset_name": dependency_name,
                    "platform": platform,
                    "technology": "Dependency reference",
                    "raw_path": document.path,
                    "owner": None,
                    "criticality": None,
                    "row_count": None,
                    "metadata_json": sanitized_json({"referenced_by": object_name}),
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
            "metadata_json": sanitized_json({"reference_count": 0}),
            "discovered_at": discovered_at,
        },
    )

    references = extract_sql_references(document.content)
    assets[script_id]["metadata_json"] = sanitized_json(
        {"reference_count": len(references), "references": references},
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
                "metadata_json": sanitized_json({"referenced_by": script_name}),
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
            "metadata_json": sanitized_json(
                {
                    "reference_count": len(references),
                    "references": references,
                    "notebook_metadata": payload.get("metadata", {}),
                },
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
                "metadata_json": sanitized_json({"referenced_by": notebook_name}),
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


def lakebridge_program_asset_id(program: str) -> str:
    return stable_id("lakebridge_analyzer", "sql_program", program)


def lakebridge_complexity_to_criticality(complexity: str) -> str | None:
    normalized = complexity.strip().lower()
    if normalized in {"very_high", "very high", "high"}:
        return "high"
    if normalized == "medium":
        return "medium"
    return None


def lakebridge_operation_to_dependency_type(operation: str) -> str:
    normalized = operation.strip().upper()
    if normalized == "READ":
        return "reads"
    if normalized in {"WRITE", "CREATE", "DROP", "TRUNCATE"}:
        return "writes"
    return "references"


def parse_lakebridge_analyzer_document(
    document: TextDocument,
    run_id: str,
    discovered_at: str,
    assets: dict[str, dict[str, Any]],
    dependencies: list[dict[str, Any]],
    dependency_keys: set[tuple[str, str, str]],
) -> None:
    sheets = parse_xlsx_text_sheets(document.content)
    if "SQL Programs" not in sheets and "RAW_PROGRAM_OBJECT_XREF" not in sheets:
        return

    for row in rows_as_dicts(sheets.get("SQL Programs", [])):
        program = row.get("source_file") or row.get("program_name")
        if not program:
            continue
        program_name = row.get("program_name") or Path(program).name
        complexity = row.get("complexity") or ""
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": lakebridge_program_asset_id(program),
                "source_system": "lakebridge_analyzer",
                "asset_type": "lakebridge_sql_program",
                "asset_name": program_name,
                "platform": "Databricks Labs",
                "technology": "Lakebridge Analyzer SQL Program",
                "raw_path": document.path,
                "owner": None,
                "criticality": lakebridge_complexity_to_criticality(complexity),
                "row_count": None,
                "metadata_json": sanitized_json(
                    {
                        "source_file": row.get("source_file"),
                        "included": row.get("included"),
                        "line_count": row.get("line_count"),
                        "complexity": complexity,
                        "statement_count": row.get("statement_count"),
                        "script_category": row.get("script_category"),
                        "categorization_metrics": row.get("categorization_metrics"),
                    }
                ),
                "discovered_at": discovered_at,
            },
        )

    for row in rows_as_dicts(sheets.get("RAW_PROGRAM_OBJECT_XREF", [])):
        program = row.get("program")
        object_name = row.get("object")
        operation = row.get("operation") or "REFERENCE"
        if not program or not object_name:
            continue

        program_id = lakebridge_program_asset_id(program)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": program_id,
                "source_system": "lakebridge_analyzer",
                "asset_type": "lakebridge_sql_program",
                "asset_name": Path(program).name,
                "platform": "Databricks Labs",
                "technology": "Lakebridge Analyzer SQL Program",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": sanitized_json({"source_file": program}),
                "discovered_at": discovered_at,
            },
        )

        object_id = stable_id("lakebridge_analyzer", "referenced_object", object_name)
        add_asset(
            assets,
            {
                "run_id": run_id,
                "asset_id": object_id,
                "source_system": "lakebridge_analyzer",
                "asset_type": "lakebridge_referenced_object",
                "asset_name": object_name,
                "platform": "Legacy SQL",
                "technology": "Lakebridge referenced SQL object",
                "raw_path": document.path,
                "owner": None,
                "criticality": None,
                "row_count": None,
                "metadata_json": sanitized_json({"operation": operation, "count": row.get("count")}),
                "discovered_at": discovered_at,
            },
        )
        add_dependency(
            dependencies,
            dependency_keys,
            {
                "run_id": run_id,
                "from_asset_id": program_id,
                "to_asset_id": object_id,
                "dependency_type": lakebridge_operation_to_dependency_type(operation),
                "evidence": f"Lakebridge {operation} reference: {object_name}",
                "confidence": 0.85,
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
        elif document.extension == ".xlsx":
            parse_lakebridge_analyzer_document(
                document,
                run_id,
                discovered_at,
                assets,
                dependencies,
                dependency_keys,
            )

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
    if document.extension == ".xlsx":
        return "lakebridge_analyzer"
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

        if asset["asset_type"] in {
            "adf_pipeline",
            "lakebridge_sql_program",
            "sql_script",
            "synapse_notebook",
            "sqlserver_stored_procedure",
        }:
            score += 10
            factors.append("requires orchestration or code migration")
        if asset["asset_type"] == "lakebridge_sql_program":
            try:
                metadata = json.loads(asset.get("metadata_json") or "{}")
            except json.JSONDecodeError:
                metadata = {}
            complexity = str(metadata.get("complexity") or "").strip().lower()
            if complexity in {"very_high", "very high", "high"}:
                score += 15
                factors.append("Lakebridge high complexity")
            elif complexity == "medium":
                score += 5
                factors.append("Lakebridge medium complexity")
        if asset["asset_type"] in {"adf_linked_service", "adf_dataset"}:
            score += 10
            factors.append("connection and dataset mapping required")
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
            "sqlserver_table",
            "sqlserver_view",
            "sql_referenced_object",
            "lakebridge_referenced_object",
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
        elif asset_type == "adf_trigger":
            target_pattern = "Lakeflow Job schedule"
            target_schema = "workflows"
            notes = [
                "Map trigger recurrence to Databricks job schedule.",
                "Confirm time zone, pause state and parameter behavior.",
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
        elif asset_type == "adf_dataset":
            target_pattern = "Unity Catalog table or volume mapping"
            target_schema = "control"
            notes = [
                "Resolve dataset linked service and physical table or storage path.",
                "Classify as managed Delta, external table, volume or federation source.",
            ]
        elif asset_type == "adf_linked_service":
            target_pattern = "Databricks secret-backed connection"
            target_schema = "control"
            notes = [
                "Move credentials to Databricks secrets or Unity Catalog connections.",
                "Validate network path and authentication method.",
            ]
        elif asset_type == "adf_storage_path":
            target_pattern = "Unity Catalog external volume or external location"
            target_schema = "control"
            notes = [
                "Map storage path to an external location and volume when direct file access is needed.",
                "Confirm owner system and lifecycle policy.",
            ]
        elif asset_type == "adf_data_object":
            target_pattern = "Unity Catalog object mapping"
            target_schema = "silver"
            notes = [
                "Resolve object to source inventory and target table pattern.",
                "Use as bridge between orchestration metadata and data object inventory.",
            ]
        elif asset_type == "sql_script":
            target_pattern = "Databricks SQL or PySpark transformation"
            target_schema = "workflows"
            notes = [
                "Refactor platform-specific T-SQL functions.",
                "Validate dependencies against Unity Catalog objects.",
            ]
        elif asset_type == "lakebridge_sql_program":
            target_pattern = "Databricks SQL or PySpark transformation"
            target_schema = "workflows"
            notes = [
                "Use Lakebridge complexity and object references to plan rewrite effort.",
                "Run Lakebridge transpile for candidates, then review generated Databricks SQL manually.",
            ]
        elif asset_type == "sqlserver_stored_procedure":
            target_pattern = "Databricks SQL, PySpark transformation or Lakeflow task"
            target_schema = "workflows"
            notes = [
                "Review procedural T-SQL and split orchestration from transformations.",
                "Convert reusable data logic into Databricks SQL or PySpark.",
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
            "sqlserver_table",
            "sqlserver_view",
            "sql_referenced_object",
            "lakebridge_referenced_object",
        }:
            checks = [
                ("row_count_reconciliation", "completeness", "error", "Compare source and Delta row counts."),
                ("schema_compatibility", "schema", "error", "Validate column names and compatible data types."),
                ("nullability_profile", "quality", "warning", "Profile null rates for business columns."),
            ]
        elif asset["asset_type"] == "lakebridge_sql_program":
            checks = [
                (
                    "lakebridge_complexity_review",
                    "code",
                    "error",
                    "Review Lakebridge complexity, functions and object references before conversion.",
                ),
                (
                    "transpile_output_review",
                    "code",
                    "warning",
                    "If Lakebridge transpile is used, validate generated Databricks SQL before execution.",
                ),
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
        elif asset["asset_type"] in {"adf_dataset", "adf_storage_path"}:
            checks = [
                (
                    "physical_reference_resolution",
                    "metadata",
                    "error",
                    "Confirm the dataset resolves to a table, file path, volume or external location.",
                ),
                (
                    "ownership_classification",
                    "governance",
                    "warning",
                    "Confirm whether Databricks or another platform owns the data lifecycle.",
                ),
            ]
        elif asset["asset_type"] == "adf_linked_service":
            checks = [
                (
                    "secret_redaction_review",
                    "security",
                    "error",
                    "Confirm credentials are not stored in metadata outputs and are moved to secrets.",
                ),
                (
                    "network_connectivity_review",
                    "security",
                    "warning",
                    "Confirm the future Databricks workspace can reach the referenced source.",
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


def build_graph_edges(
    assets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    asset_by_id = {asset["asset_id"]: asset for asset in assets}
    rows = []

    for dependency in dependencies:
        from_asset = asset_by_id.get(dependency["from_asset_id"], {})
        to_asset = asset_by_id.get(dependency["to_asset_id"], {})
        rows.append(
            {
                "run_id": run_id,
                "from_asset_id": dependency["from_asset_id"],
                "from_asset_name": from_asset.get("asset_name", dependency["from_asset_id"]),
                "from_asset_type": from_asset.get("asset_type", "unknown"),
                "dependency_type": dependency["dependency_type"],
                "to_asset_id": dependency["to_asset_id"],
                "to_asset_name": to_asset.get("asset_name", dependency["to_asset_id"]),
                "to_asset_type": to_asset.get("asset_type", "unknown"),
                "evidence": dependency.get("evidence"),
                "confidence": dependency["confidence"],
                "generated_at": generated_at,
            }
        )
    return rows


def build_asset_priority_matrix(
    assets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    risk_register: list[dict[str, Any]],
    blueprint: list[dict[str, Any]],
    dq_plan: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    dependency_counts = Counter()
    for dependency in dependencies:
        dependency_counts[dependency["from_asset_id"]] += 1
        dependency_counts[dependency["to_asset_id"]] += 1

    risk_by_id = {risk["asset_id"]: risk for risk in risk_register}
    blueprint_by_id = {item["asset_id"]: item for item in blueprint}
    dq_counts = Counter(item["asset_id"] for item in dq_plan)
    rows = []

    for asset in assets:
        risk = risk_by_id.get(asset["asset_id"], {})
        blueprint_item = blueprint_by_id.get(asset["asset_id"], {})
        risk_score = float(risk.get("risk_score") or 0)
        dependency_count = dependency_counts[asset["asset_id"]]

        if risk_score >= 70 or dependency_count >= 5:
            review_priority = "p1"
        elif risk_score >= 40 or dependency_count >= 2:
            review_priority = "p2"
        else:
            review_priority = "p3"

        rows.append(
            {
                "run_id": run_id,
                "asset_id": asset["asset_id"],
                "asset_name": asset["asset_name"],
                "asset_type": asset["asset_type"],
                "source_system": asset["source_system"],
                "risk_level": risk.get("risk_level", "unknown"),
                "risk_score": risk_score,
                "dependency_count": dependency_count,
                "dq_check_count": dq_counts[asset["asset_id"]],
                "target_pattern": blueprint_item.get("target_pattern", "unknown"),
                "target_schema": blueprint_item.get("target_schema", "unknown"),
                "review_priority": review_priority,
                "next_action": risk.get("recommended_action", "Review asset metadata and target mapping."),
                "generated_at": generated_at,
            }
        )

    return sorted(
        rows,
        key=lambda item: (
            {"p1": 0, "p2": 1, "p3": 2}.get(item["review_priority"], 9),
            -item["risk_score"],
            -item["dependency_count"],
            item["asset_name"],
        ),
    )


def build_assessment_summary(
    assets: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    risk_register: list[dict[str, Any]],
    blueprint: list[dict[str, Any]],
    dq_plan: list[dict[str, Any]],
    run_id: str,
) -> list[dict[str, Any]]:
    generated_at = utc_now()
    risk_counts = Counter(row["risk_level"] for row in risk_register)
    source_counts = Counter(asset["source_system"] for asset in assets)
    pattern_counts = Counter(row["target_pattern"] for row in blueprint)
    dq_severity_counts = Counter(row["severity"] for row in dq_plan)
    priority_candidates = sum(
        1
        for row in risk_register
        if row["risk_level"] == "high"
    )

    return [
        {
            "run_id": run_id,
            "summary_name": "executive_summary",
            "asset_count": len(assets),
            "dependency_count": len(dependencies),
            "high_risk_count": risk_counts["high"],
            "medium_risk_count": risk_counts["medium"],
            "low_risk_count": risk_counts["low"],
            "dq_error_count": dq_severity_counts["error"],
            "dq_warning_count": dq_severity_counts["warning"],
            "primary_source_systems": sorted(source_counts),
            "target_patterns": sorted(pattern_counts),
            "recommended_focus": recommended_focus(
                risk_counts["high"],
                priority_candidates,
                len(dependencies),
            ),
            "generated_at": generated_at,
        }
    ]


def recommended_focus(high_risk_count: int, priority_candidates: int, dependency_count: int) -> str:
    if high_risk_count > 0:
        return "Review high-risk assets and validate critical dependencies first."
    if dependency_count > 0:
        return "Validate dependency coverage and target patterns with source owners."
    if priority_candidates > 0:
        return "Review priority candidates and confirm business criticality."
    return "Confirm inventory completeness before planning migration waves."


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
        "graph_edges": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("from_asset_id", StringType(), False),
                StructField("from_asset_name", StringType(), False),
                StructField("from_asset_type", StringType(), False),
                StructField("dependency_type", StringType(), False),
                StructField("to_asset_id", StringType(), False),
                StructField("to_asset_name", StringType(), False),
                StructField("to_asset_type", StringType(), False),
                StructField("evidence", StringType(), True),
                StructField("confidence", DoubleType(), False),
                StructField("generated_at", StringType(), False),
            ]
        ),
        "asset_priority_matrix": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("asset_type", StringType(), False),
                StructField("source_system", StringType(), False),
                StructField("risk_level", StringType(), False),
                StructField("risk_score", DoubleType(), False),
                StructField("dependency_count", LongType(), False),
                StructField("dq_check_count", LongType(), False),
                StructField("target_pattern", StringType(), False),
                StructField("target_schema", StringType(), False),
                StructField("review_priority", StringType(), False),
                StructField("next_action", StringType(), False),
                StructField("generated_at", StringType(), False),
            ]
        ),
        "assessment_summary": StructType(
            [
                StructField("run_id", StringType(), False),
                StructField("summary_name", StringType(), False),
                StructField("asset_count", LongType(), False),
                StructField("dependency_count", LongType(), False),
                StructField("high_risk_count", LongType(), False),
                StructField("medium_risk_count", LongType(), False),
                StructField("low_risk_count", LongType(), False),
                StructField("dq_error_count", LongType(), False),
                StructField("dq_warning_count", LongType(), False),
                StructField("primary_source_systems", ArrayType(StringType()), False),
                StructField("target_patterns", ArrayType(StringType()), False),
                StructField("recommended_focus", StringType(), False),
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
    parser = argparse.ArgumentParser(description="Run the Databricks migration accelerator.")
    parser.add_argument("--catalog", default="migration_accelerator_dev")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--bronze-schema", default="bronze")
    parser.add_argument("--silver-schema", default="silver")
    parser.add_argument("--gold-schema", default="gold")
    parser.add_argument("--control-schema", default="control")
    args = parser.parse_args()
    if not args.source_root:
        args.source_root = default_source_root()
    return args


def main() -> None:
    args = parse_args()
    started_at = utc_now()
    start = datetime.now(timezone.utc)
    run_id = args.run_id or f"run_{start.strftime('%Y%m%d_%H%M%S')}"
    print(f"Starting migration accelerator run_id={run_id} catalog={args.catalog} source_root={args.source_root}")
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
        graph_edges = build_graph_edges(assets, dependencies, run_id)
        priority_matrix = build_asset_priority_matrix(
            assets,
            dependencies,
            risk_register,
            blueprint,
            dq_plan,
            run_id,
        )
        assessment_summary = build_assessment_summary(
            assets,
            dependencies,
            risk_register,
            blueprint,
            dq_plan,
            run_id,
        )
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
            graph_edges,
            table_schemas["graph_edges"],
            table_name(args.catalog, args.gold_schema, "graph_edges"),
            "overwrite",
        )
        write_table(
            spark,
            priority_matrix,
            table_schemas["asset_priority_matrix"],
            table_name(args.catalog, args.gold_schema, "asset_priority_matrix"),
            "overwrite",
        )
        write_table(
            spark,
            assessment_summary,
            table_schemas["assessment_summary"],
            table_name(args.catalog, args.gold_schema, "assessment_summary"),
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
            "graph_edges": len(graph_edges),
            "asset_priority_rows": len(priority_matrix),
            "high_risk_count": high_risk_count,
        }
        status = "SUCCESS"
        error_message = None
        print(f"Migration accelerator completed run_id={run_id} metrics={json.dumps(metrics, sort_keys=True)}")
    except Exception as exc:
        metrics = {}
        status = "FAILED"
        error_message = str(exc)
        print(f"Migration accelerator failed run_id={run_id} error={error_message}")
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


if (
    __name__ == "__main__"
    or "filename" in globals()
    or str(sys.argv[0]).replace("\\", "/").endswith("/run_accelerator.py")
):
    main()
