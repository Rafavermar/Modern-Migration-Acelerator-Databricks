#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"
export MSYS_NO_PATHCONV=1
export MSYS2_ARG_CONV_EXCL="*"

if [ -x .venv/Scripts/python.exe ]; then
  python_cmd=".venv/Scripts/python.exe"
elif [ -x .venv/bin/python ]; then
  python_cmd=".venv/bin/python"
else
  python_cmd="${PYTHON:-python}"
fi

"$python_cmd" -m modern_migration_accelerator.rag_eval "$@"
