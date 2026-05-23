$ErrorActionPreference = "Stop"

if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".venv\Scripts\python.exe"
}
else {
    $python = "python"
}

& $python scripts/publish_neo4j_graph.py @args
