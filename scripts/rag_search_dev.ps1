param(
    [string]$Question = "Which high risk legacy assets should be migrated first?",
    [int]$NumResults = 5,
    [switch]$LogMlflow
)

$ErrorActionPreference = "Stop"

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$srcPath = Join-Path (Get-Location) "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
}
else {
    $env:PYTHONPATH = $srcPath
}

$args = @(
    "-m",
    "modern_migration_accelerator.rag_search",
    $Question,
    "--num-results",
    "$NumResults"
)

if ($LogMlflow) {
    $args += "--log-mlflow"
}

& $python @args
