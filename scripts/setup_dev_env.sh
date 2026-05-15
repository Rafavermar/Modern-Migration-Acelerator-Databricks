#!/usr/bin/env bash
set -euo pipefail

python_cmd="${PYTHON:-python}"

if ! command -v "$python_cmd" >/dev/null 2>&1; then
  echo "Python is required. Set PYTHON=/path/to/python if it is not on PATH." >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "Git is required." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "WARN: docker is missing. Install Docker Desktop before using the SQL Server fixture." >&2
fi

if ! command -v databricks >/dev/null 2>&1; then
  echo "WARN: databricks CLI is missing. Install/login only when the Full Trial workspace is ready." >&2
fi

if [ ! -d .venv ]; then
  "$python_cmd" -m venv .venv
fi

if [ -x .venv/Scripts/python.exe ]; then
  venv_python=".venv/Scripts/python.exe"
else
  venv_python=".venv/bin/python"
fi

"$venv_python" -m pip install --no-build-isolation -e .

extras=()
if [ "${INSTALL_DEV_DEPS:-0}" = "1" ]; then
  extras+=("dev")
fi
if [ "${INSTALL_LOCAL_SPARK:-0}" = "1" ]; then
  extras+=("local-spark")
fi
if [ "${#extras[@]}" -gt 0 ]; then
  joined="$(IFS=,; echo "${extras[*]}")"
  "$venv_python" -m pip install --no-build-isolation -e ".[$joined]"
fi

echo
echo "Development environment ready."
echo "Run: bash scripts/local_smoke_test.sh"
