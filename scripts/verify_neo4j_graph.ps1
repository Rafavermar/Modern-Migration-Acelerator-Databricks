$ErrorActionPreference = "Stop"

if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".venv\Scripts\python.exe"
}
else {
    $python = "python"
}

& $python scripts/verify_neo4j_graph.py
