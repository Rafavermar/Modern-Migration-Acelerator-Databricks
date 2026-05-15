from __future__ import annotations

import re


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


def strip_sql_comments(sql_text: str) -> str:
    sql_text = re.sub(r"/\*.*?\*/", " ", sql_text, flags=re.DOTALL)
    return re.sub(r"--.*?$", " ", sql_text, flags=re.MULTILINE)


def normalize_identifier(identifier: str) -> str:
    cleaned = identifier.strip().strip(";,.()")
    cleaned = cleaned.replace("[", "").replace("]", "")
    cleaned = cleaned.replace("`", "").replace('"', "")
    return re.sub(r"\s+", "", cleaned).lower()


def extract_sql_references(sql_text: str) -> list[str]:
    """Extract table-like references from SQL using conservative keyword matching."""
    cleaned_sql = strip_sql_comments(sql_text)
    references: list[str] = []
    seen = set()

    for match in REFERENCE_PATTERN.finditer(cleaned_sql):
        reference = normalize_identifier(match.group("identifier"))
        if not reference or reference.startswith(("#", "@")):
            continue
        if reference in {"select", "values", "with"}:
            continue
        if reference not in seen:
            seen.add(reference)
            references.append(reference)

    return references
