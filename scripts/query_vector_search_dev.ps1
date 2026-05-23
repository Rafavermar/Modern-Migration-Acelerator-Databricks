param(
    [string]$Query = "Which high risk legacy assets should be migrated first?",
    [int]$NumResults = 5
)

$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path = ".env")

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or -not $line.Contains("=")) {
            return
        }

        $parts = $line.Split("=", 2)
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function DatabricksArgs {
    if ($env:DATABRICKS_PROFILE) {
        return @("--profile", $env:DATABRICKS_PROFILE)
    }
    return @()
}

Import-DotEnv

$catalog = if ($env:DATABRICKS_CATALOG) { $env:DATABRICKS_CATALOG } else { "migration_accelerator_dev" }
$indexName = if ($env:DATABRICKS_VECTOR_SEARCH_INDEX) { $env:DATABRICKS_VECTOR_SEARCH_INDEX } else { "$catalog.gold.semantic_legacy_documents_vs" }
$profileArgs = DatabricksArgs

$body = @{
    query_text = $Query
    query_type = "HYBRID"
    num_results = $NumResults
    columns = @(
        "chunk_id",
        "document_type",
        "asset_name",
        "asset_type",
        "source_system",
        "risk_level",
        "review_priority",
        "target_pattern",
        "source_path",
        "chunk_text"
    )
}
$bodyFile = New-TemporaryFile
$jsonText = $body | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($bodyFile.FullName, $jsonText, [System.Text.UTF8Encoding]::new($false))
$jsonArg = "@$($bodyFile.FullName)"

$path = "/api/2.0/vector-search/indexes/$indexName/query"
& databricks @profileArgs api post $path --json $jsonArg -o json

Remove-Item -Path $bodyFile -Force
