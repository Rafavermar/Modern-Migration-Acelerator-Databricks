from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from modern_migration_accelerator.xlsx import xlsx_bytes_to_text

SUPPORTED_EXTENSIONS = {".csv", ".ipynb", ".json", ".sql", ".xlsx"}
SPARK_FILE_PREFIXES = ("dbfs:/", "/Volumes/", "abfss://", "wasbs://", "s3://", "gs://")


@dataclass(frozen=True)
class TextDocument:
    path: str
    content: str
    extension: str


def load_text_documents(source_root: str, spark=None) -> list[TextDocument]:
    """Load supported metadata files from local/workspace files or cloud paths."""
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
