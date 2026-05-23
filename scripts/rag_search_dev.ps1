param(
    [string]$Question = "Which high risk legacy assets should be migrated first?",
    [int]$NumResults = 5,
    [switch]$GenerateAnswer,
    [string]$LlmEndpoint = "",
    [int]$MaxTokens = 700,
    [double]$Temperature = 0.0,
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

if ($GenerateAnswer) {
    $args += "--generate-answer"
}
if ($LlmEndpoint) {
    $args += @("--llm-endpoint", $LlmEndpoint)
}
if ($GenerateAnswer) {
    $args += @("--max-tokens", "$MaxTokens", "--temperature", "$Temperature")
}
if ($LogMlflow) {
    $args += "--log-mlflow"
}

& $python @args
