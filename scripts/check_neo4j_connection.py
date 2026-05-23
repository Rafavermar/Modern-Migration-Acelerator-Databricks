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
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


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
        print(
            "Neo4j Python driver is not installed. Run setup with graph deps:\n"
            "  powershell -ExecutionPolicy Bypass -File .\\scripts\\setup_dev_env.ps1 -InstallGraphDeps\n"
            "or\n"
            "  INSTALL_GRAPH_DEPS=1 bash scripts/setup_dev_env.sh",
            file=sys.stderr,
        )
        return 2

    try:
        uri = require_env("NEO4J_URI")
        username = require_env("NEO4J_USERNAME")
        password = require_env("NEO4J_PASSWORD")
        database = os.environ.get("NEO4J_DATABASE", "neo4j").strip() or "neo4j"
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
        with driver.session(database=database) as session:
            record = session.run("RETURN 1 AS ok").single()
            if record is None or record["ok"] != 1:
                print("Neo4j connectivity check returned an unexpected result.", file=sys.stderr)
                return 1
    finally:
        driver.close()

    instance_name = os.environ.get("AURA_INSTANCENAME", "").strip()
    instance_suffix = f" ({instance_name})" if instance_name else ""
    print(f"Neo4j connectivity OK: {uri} / database={database}{instance_suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
