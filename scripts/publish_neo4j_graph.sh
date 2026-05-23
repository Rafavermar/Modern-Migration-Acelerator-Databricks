#!/usr/bin/env bash
set -euo pipefail

python_cmd="${PYTHON:-python}"
if [ -x ".venv/Scripts/python.exe" ]; then
  python_cmd=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
  python_cmd=".venv/bin/python"
fi

"$python_cmd" scripts/publish_neo4j_graph.py "$@"
