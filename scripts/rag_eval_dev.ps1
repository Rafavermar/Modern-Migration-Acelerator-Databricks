param(
    [string]$Cases = "contracts/rag_eval_questions.json",
    [int]$NumResults = 5,
    [switch]$GenerateAnswer,
    [string]$LlmEndpoint = "",
    [int]$MaxTokens = 1200,
    [double]$Temperature = 0.0,
    [switch]$LogMlflow,
    [switch]$FailOnMiss
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
    "modern_migration_accelerator.rag_eval",
    "--cases",
    $Cases,
    "--num-results",
    "$NumResults"
)

if ($GenerateAnswer) {
    $args += "--generate-answer"
    $args += @("--max-tokens", "$MaxTokens", "--temperature", "$Temperature")
}
if ($LlmEndpoint) {
    $args += @("--llm-endpoint", $LlmEndpoint)
}
if ($LogMlflow) {
    $args += "--log-mlflow"
}
if ($FailOnMiss) {
    $args += "--fail-on-miss"
}

& $python @args
