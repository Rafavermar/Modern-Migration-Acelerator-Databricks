$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

& $python scripts/check_neo4j_connection.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
