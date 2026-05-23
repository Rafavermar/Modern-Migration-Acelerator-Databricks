from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_PATH = globals().get("__file__") or globals().get("filename") or sys.argv[0]
SUPPORTED_EXTENSIONS = {".csv", ".ipynb", ".json", ".sql"}
SPARK_FILE_PREFIXES = ("dbfs:/", "/Volumes/", "abfss://", "wasbs://", "s3://", "gs://")
SENSITIVE_KEY_TERMS = ("password", "secret", "token", "key", "connectionstring", "sas")
PLAIN_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|secret|token|api[_-]?key|connectionstring|sas)\b\s*[:=]\s*['\"]?[^,'\"\s}]+"
)


@dataclass(frozen=True)
class TextDocument:
    path: str
    content: str
    extension: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(*parts: object) -> str:
    raw = "|".join(str(part).strip().lower() for part in parts if part is not None)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def quote_identifier(identifier: str) -> str:
    if not identifier or "\x00" in identifier:
        raise ValueError("Databricks identifiers cannot be empty.")
    return f"`{identifier.replace('`', '``')}`"


def table_name(catalog: str, schema: str, table: str) -> str:
    return ".".join(quote_identifier(part) for part in (catalog, schema, table))


def normalize_storage_path(value: str) -> str:
    normalized = value.rstrip("/")
    if normalized.startswith("dbfs:"):
        normalized = normalized[5:]
    return normalized


def default_source_root() -> str:
    script_path = Path(SCRIPT_PATH).resolve()
    if len(script_path.parents) >= 4:
        return str(script_path.parents[3] / "samples" / "legacy_metadata")
    return "samples/legacy_metadata"


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


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def redact_plain_text(value: str) -> str:
    return PLAIN_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=***REDACTED***", value)


def notebook_to_text(value: dict[str, Any]) -> str:
    cells = value.get("cells", [])
    parts: list[str] = []
    for index, cell in enumerate(cells):
        cell_type = str(cell.get("cell_type", "cell"))
        source = cell.get("source", "")
        if isinstance(source, list):
            source_text = "".join(str(item) for item in source)
        else:
            source_text = str(source)
        source_text = source_text.strip()
        if source_text:
            parts.append(f"Notebook cell {index + 1} ({cell_type}):\n{source_text}")
    return "\n\n".join(parts) or json.dumps(value, sort_keys=True)


def sanitize_document_content(document: TextDocument) -> str:
    if document.extension in {".json", ".ipynb"}:
        try:
            parsed = json.loads(document.content)
        except json.JSONDecodeError:
            return redact_plain_text(document.content)
        redacted = redact_sensitive_values(parsed)
        if document.extension == ".ipynb" and isinstance(redacted, dict):
            return redact_plain_text(notebook_to_text(redacted))
        return json.dumps(redacted, indent=2, sort_keys=True)
    return redact_plain_text(document.content)


def split_text_chunks(text: str, max_chars: int = 3200, overlap_chars: int = 400) -> list[str]:
    cleaned = normalize_whitespace(text)
    if not cleaned:
        return []
    if len(cleaned) <= max_chars:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = min(len(cleaned), start + max_chars)
        if end < len(cleaned):
            boundary = max(
                cleaned.rfind(". ", start, end),
                cleaned.rfind("; ", start, end),
                cleaned.rfind(" ", start, end),
            )
            if boundary > start + int(max_chars * 0.6):
                end = boundary + 1
        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(cleaned):
            break
        start = max(0, end - overlap_chars)
    return chunks


def load_text_documents(source_root: str, spark=None) -> list[TextDocument]:
    normalized_root = source_root.rstrip("/")

    if normalized_root.startswith("/Workspace/"):
        raise ValueError(
            "Workspace Files are for bundle code, not semantic source input. "
            "Use a Unity Catalog volume path such as /Volumes/<catalog>/landing/legacy_metadata."
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
                documents.append(
                    TextDocument(
                        path=str(file_path),
                        content=file_path.read_text(encoding="utf-8"),
                        extension=file_path.suffix.lower(),
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
        documents.append(
            TextDocument(
                path=row["path"],
                content=bytes(row["content"]).decode("utf-8"),
                extension=extension,
            )
        )
    return sorted(documents, key=lambda item: item.path)


def as_clean_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(as_clean_string(item) for item in value if item is not None)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return str(value)


def make_chunk_rows(
    *,
    run_id: str,
    document_type: str,
    source_path: str,
    source_format: str,
    document_text: str,
    generated_at: str,
    asset_id: str = "",
    asset_name: str = "",
    asset_type: str = "",
    source_system: str = "",
    target_pattern: str = "",
    risk_level: str = "",
    review_priority: str = "",
) -> list[dict[str, Any]]:
    rows = []
    for chunk_index, chunk_text in enumerate(split_text_chunks(document_text)):
        chunk_hash = content_hash(chunk_text)
        rows.append(
            {
                "chunk_id": stable_id(run_id, document_type, source_path, chunk_index, chunk_hash),
                "run_id": run_id,
                "document_type": document_type,
                "source_path": source_path,
                "source_format": source_format,
                "asset_id": asset_id,
                "asset_name": asset_name,
                "asset_type": asset_type,
                "source_system": source_system,
                "target_pattern": target_pattern,
                "risk_level": risk_level,
                "review_priority": review_priority,
                "chunk_index": chunk_index,
                "chunk_text": chunk_text,
                "content_hash": chunk_hash,
                "generated_at": generated_at,
            }
        )
    return rows


def build_source_document_chunks(
    documents: list[TextDocument],
    asset_context_by_path: dict[str, dict[str, Any]],
    run_id: str,
    generated_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for document in documents:
        context = asset_context_by_path.get(document.path) or asset_context_by_path.get(Path(document.path).name) or {}
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="legacy_artifact",
                source_path=document.path,
                source_format=document.extension.lstrip("."),
                document_text=sanitize_document_content(document),
                generated_at=generated_at,
                asset_id=as_clean_string(context.get("asset_id")),
                asset_name=as_clean_string(context.get("asset_name")),
                asset_type=as_clean_string(context.get("asset_type")),
                source_system=as_clean_string(context.get("source_system")),
            )
        )
    return rows


def build_asset_context(spark, catalog: str, silver_schema: str, run_id: str) -> dict[str, dict[str, Any]]:
    from pyspark.sql import functions as functions

    source = table_name(catalog, silver_schema, "assets")
    rows = (
        spark.table(source)
        .where(functions.col("run_id") == run_id)
        .select("asset_id", "asset_name", "asset_type", "source_system", "raw_path")
        .collect()
    )
    context: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = row.asDict(recursive=True)
        raw_path = as_clean_string(item.get("raw_path"))
        if raw_path:
            context[raw_path] = item
            context[Path(raw_path).name] = item
    return context


def latest_successful_run(spark, catalog: str, control_schema: str) -> dict[str, Any]:
    from pyspark.sql import functions as functions

    source = table_name(catalog, control_schema, "run_log")
    rows = (
        spark.table(source)
        .where(functions.col("status") == "SUCCESS")
        .orderBy(functions.col("ended_at").desc())
        .select("run_id", "source_root")
        .limit(1)
        .collect()
    )
    if not rows:
        raise ValueError(f"No successful accelerator run found in {source}. Run the accelerator job first.")
    return rows[0].asDict(recursive=True)


def collect_generated_rows(spark, full_table_name: str, run_id: str) -> list[dict[str, Any]]:
    from pyspark.sql import functions as functions

    return [
        row.asDict(recursive=True)
        for row in spark.table(full_table_name).where(functions.col("run_id") == run_id).collect()
    ]


def build_generated_output_chunks(
    spark,
    catalog: str,
    gold_schema: str,
    run_id: str,
    generated_at: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    blueprint_table = table_name(catalog, gold_schema, "target_databricks_blueprint")
    for item in collect_generated_rows(spark, blueprint_table, run_id):
        text = (
            f"Databricks target blueprint for {as_clean_string(item.get('asset_name'))}. "
            f"Legacy type: {as_clean_string(item.get('legacy_asset_type'))}. "
            f"Target pattern: {as_clean_string(item.get('target_pattern'))}. "
            f"Target object: {as_clean_string(item.get('target_catalog'))}."
            f"{as_clean_string(item.get('target_schema'))}.{as_clean_string(item.get('target_object'))}. "
            f"Migration notes: {as_clean_string(item.get('migration_notes'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="target_blueprint",
                source_path=f"delta:{blueprint_table}#{as_clean_string(item.get('asset_id'))}",
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
                asset_id=as_clean_string(item.get("asset_id")),
                asset_name=as_clean_string(item.get("asset_name")),
                asset_type=as_clean_string(item.get("legacy_asset_type")),
                target_pattern=as_clean_string(item.get("target_pattern")),
            )
        )

    risk_table = table_name(catalog, gold_schema, "risk_register")
    for item in collect_generated_rows(spark, risk_table, run_id):
        text = (
            f"Migration risk for {as_clean_string(item.get('asset_name'))}. "
            f"Asset type: {as_clean_string(item.get('asset_type'))}. "
            f"Risk level: {as_clean_string(item.get('risk_level'))}. "
            f"Risk score: {as_clean_string(item.get('risk_score'))}. "
            f"Risk factors: {as_clean_string(item.get('risk_factors'))}. "
            f"Recommended action: {as_clean_string(item.get('recommended_action'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="risk_register",
                source_path=f"delta:{risk_table}#{as_clean_string(item.get('asset_id'))}",
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
                asset_id=as_clean_string(item.get("asset_id")),
                asset_name=as_clean_string(item.get("asset_name")),
                asset_type=as_clean_string(item.get("asset_type")),
                risk_level=as_clean_string(item.get("risk_level")),
            )
        )

    priority_table = table_name(catalog, gold_schema, "asset_priority_matrix")
    for item in collect_generated_rows(spark, priority_table, run_id):
        text = (
            f"Migration review priority for {as_clean_string(item.get('asset_name'))}. "
            f"Priority: {as_clean_string(item.get('review_priority'))}. "
            f"Risk level: {as_clean_string(item.get('risk_level'))}. "
            f"Risk score: {as_clean_string(item.get('risk_score'))}. "
            f"Dependency count: {as_clean_string(item.get('dependency_count'))}. "
            f"Data quality check count: {as_clean_string(item.get('dq_check_count'))}. "
            f"Target pattern: {as_clean_string(item.get('target_pattern'))}. "
            f"Next action: {as_clean_string(item.get('next_action'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="asset_priority",
                source_path=f"delta:{priority_table}#{as_clean_string(item.get('asset_id'))}",
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
                asset_id=as_clean_string(item.get("asset_id")),
                asset_name=as_clean_string(item.get("asset_name")),
                asset_type=as_clean_string(item.get("asset_type")),
                source_system=as_clean_string(item.get("source_system")),
                target_pattern=as_clean_string(item.get("target_pattern")),
                risk_level=as_clean_string(item.get("risk_level")),
                review_priority=as_clean_string(item.get("review_priority")),
            )
        )

    dq_table = table_name(catalog, gold_schema, "data_quality_plan")
    for item in collect_generated_rows(spark, dq_table, run_id):
        text = (
            f"Data quality migration check for {as_clean_string(item.get('asset_name'))}. "
            f"Check: {as_clean_string(item.get('check_name'))}. "
            f"Type: {as_clean_string(item.get('check_type'))}. "
            f"Severity: {as_clean_string(item.get('severity'))}. "
            f"Rule: {as_clean_string(item.get('rule_description'))}. "
            f"Target table: {as_clean_string(item.get('target_table'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="data_quality_plan",
                source_path=f"delta:{dq_table}#{as_clean_string(item.get('asset_id'))}#{as_clean_string(item.get('check_name'))}",
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
                asset_id=as_clean_string(item.get("asset_id")),
                asset_name=as_clean_string(item.get("asset_name")),
            )
        )

    graph_table = table_name(catalog, gold_schema, "graph_edges")
    for item in collect_generated_rows(spark, graph_table, run_id):
        text = (
            f"Legacy dependency from {as_clean_string(item.get('from_asset_name'))} "
            f"({as_clean_string(item.get('from_asset_type'))}) to {as_clean_string(item.get('to_asset_name'))} "
            f"({as_clean_string(item.get('to_asset_type'))}). "
            f"Dependency type: {as_clean_string(item.get('dependency_type'))}. "
            f"Evidence: {as_clean_string(item.get('evidence'))}. "
            f"Confidence: {as_clean_string(item.get('confidence'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="graph_edge",
                source_path=(
                    f"delta:{graph_table}#{as_clean_string(item.get('from_asset_id'))}"
                    f"->{as_clean_string(item.get('to_asset_id'))}"
                ),
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
                asset_id=as_clean_string(item.get("from_asset_id")),
                asset_name=as_clean_string(item.get("from_asset_name")),
                asset_type=as_clean_string(item.get("from_asset_type")),
            )
        )

    summary_table = table_name(catalog, gold_schema, "assessment_summary")
    for item in collect_generated_rows(spark, summary_table, run_id):
        text = (
            f"Migration assessment summary. Asset count: {as_clean_string(item.get('asset_count'))}. "
            f"Dependency count: {as_clean_string(item.get('dependency_count'))}. "
            f"High risk count: {as_clean_string(item.get('high_risk_count'))}. "
            f"Medium risk count: {as_clean_string(item.get('medium_risk_count'))}. "
            f"Low risk count: {as_clean_string(item.get('low_risk_count'))}. "
            f"Primary source systems: {as_clean_string(item.get('primary_source_systems'))}. "
            f"Target patterns: {as_clean_string(item.get('target_patterns'))}. "
            f"Recommended focus: {as_clean_string(item.get('recommended_focus'))}."
        )
        rows.extend(
            make_chunk_rows(
                run_id=run_id,
                document_type="assessment_summary",
                source_path=f"delta:{summary_table}#{as_clean_string(item.get('summary_name'))}",
                source_format="delta",
                document_text=text,
                generated_at=generated_at,
            )
        )

    return rows


def schemas():
    from pyspark.sql.types import LongType, StringType, StructField, StructType

    return {
        "semantic_legacy_documents": StructType(
            [
                StructField("chunk_id", StringType(), False),
                StructField("run_id", StringType(), False),
                StructField("document_type", StringType(), False),
                StructField("source_path", StringType(), False),
                StructField("source_format", StringType(), False),
                StructField("asset_id", StringType(), False),
                StructField("asset_name", StringType(), False),
                StructField("asset_type", StringType(), False),
                StructField("source_system", StringType(), False),
                StructField("target_pattern", StringType(), False),
                StructField("risk_level", StringType(), False),
                StructField("review_priority", StringType(), False),
                StructField("chunk_index", LongType(), False),
                StructField("chunk_text", StringType(), False),
                StructField("content_hash", StringType(), False),
                StructField("generated_at", StringType(), False),
            ]
        )
    }


def write_semantic_table(spark, rows: list[dict[str, Any]], catalog: str, gold_schema: str, table: str) -> str:
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {quote_identifier(catalog)}.{quote_identifier(gold_schema)}")
    full_table_name = table_name(catalog, gold_schema, table)
    dataframe = spark.createDataFrame(rows, schema=schemas()["semantic_legacy_documents"])
    dataframe.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(full_table_name)
    spark.sql(f"ALTER TABLE {full_table_name} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    return full_table_name


def get_spark():
    from pyspark.sql import SparkSession

    return SparkSession.builder.appName("modern-migration-semantic-index-prep").getOrCreate()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare semantic corpus rows for Databricks Vector Search.")
    parser.add_argument("--catalog", default="migration_accelerator_dev")
    parser.add_argument("--source-root", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--silver-schema", default="silver")
    parser.add_argument("--gold-schema", default="gold")
    parser.add_argument("--control-schema", default="control")
    parser.add_argument("--semantic-table", default="semantic_legacy_documents")
    args = parser.parse_args()
    if not args.source_root:
        args.source_root = default_source_root()
    return args


def main() -> None:
    args = parse_args()
    generated_at = utc_now()
    spark = get_spark()
    latest_run = None if args.run_id else latest_successful_run(spark, args.catalog, args.control_schema)
    run_id = args.run_id or as_clean_string(latest_run.get("run_id"))
    if latest_run:
        run_source_root = as_clean_string(latest_run.get("source_root"))
        if normalize_storage_path(run_source_root) != normalize_storage_path(args.source_root):
            print(
                "WARN: semantic source_root differs from latest accelerator source_root. "
                f"semantic_source_root={args.source_root} accelerator_source_root={run_source_root}"
            )

    print(
        "Starting semantic index prep "
        f"run_id={run_id} catalog={args.catalog} source_root={args.source_root}"
    )

    documents = load_text_documents(args.source_root, spark=spark)
    if not documents:
        raise ValueError(f"No supported metadata files found in {args.source_root}")

    asset_context = build_asset_context(spark, args.catalog, args.silver_schema, run_id)
    source_rows = build_source_document_chunks(documents, asset_context, run_id, generated_at)
    generated_rows = build_generated_output_chunks(spark, args.catalog, args.gold_schema, run_id, generated_at)
    rows = source_rows + generated_rows
    if not rows:
        raise ValueError("No semantic chunks were generated.")

    full_table_name = write_semantic_table(spark, rows, args.catalog, args.gold_schema, args.semantic_table)
    metrics = {
        "run_id": run_id,
        "source_documents": len(documents),
        "semantic_chunks": len(rows),
        "source_chunks": len(source_rows),
        "generated_output_chunks": len(generated_rows),
        "target_table": full_table_name,
    }
    print(f"Semantic index prep completed metrics={json.dumps(metrics, sort_keys=True)}")


if (
    __name__ == "__main__"
    or "filename" in globals()
    or str(sys.argv[0]).replace("\\", "/").endswith("/run_semantic_index_prep.py")
):
    main()
