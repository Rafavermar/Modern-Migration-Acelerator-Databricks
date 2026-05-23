#!/usr/bin/env bash
set -euo pipefail

if [ -x .venv/Scripts/python.exe ]; then
  python_cmd=".venv/Scripts/python.exe"
elif [ -x .venv/bin/python ]; then
  python_cmd=".venv/bin/python"
else
  python_cmd="${PYTHON:-python}"
fi

"$python_cmd" scripts/check_neo4j_connection.py
