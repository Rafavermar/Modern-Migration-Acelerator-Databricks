from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".csv", ".ipynb", ".json", ".sql"}


@dataclass(frozen=True)
class TextDocument:
    path: str
    content: str
    extension: str


def load_text_documents(source_root: str, spark=None) -> list[TextDocument]:
    """Load supported metadata files from local/workspace files or cloud paths."""
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
