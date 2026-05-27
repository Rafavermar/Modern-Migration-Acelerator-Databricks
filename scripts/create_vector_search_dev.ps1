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

function Get-VectorIndex {
    param([string]$IndexName)

    try {
        $json = & databricks @profileArgs vector-search-indexes get-index $IndexName -o json 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) {
            return $null
        }
        return ($json | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Wait-VectorIndexReady {
    param(
        [string]$IndexName,
        [int]$MaxAttempts = 60,
        [int]$SleepSeconds = 20
    )

    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $index = Get-VectorIndex -IndexName $IndexName
        if ($index -and $index.status -and $index.status.ready -eq $true) {
            Write-Host "Vector Search index is ready: $IndexName"
            return
        }

        $message = if ($index -and $index.status) { $index.status.message } else { "status unavailable" }
        Write-Host "Waiting for Vector Search index readiness ($attempt/$MaxAttempts): $message"
        Start-Sleep -Seconds $SleepSeconds
    }

    throw "Vector Search index did not become ready in time: $IndexName"
}

Import-DotEnv

$catalog = if ($env:DATABRICKS_CATALOG) { $env:DATABRICKS_CATALOG } else { "migration_accelerator_dev" }
$endpoint = if ($env:DATABRICKS_VECTOR_SEARCH_ENDPOINT) { $env:DATABRICKS_VECTOR_SEARCH_ENDPOINT } else { "mma-vector-search-dev" }
$endpointType = if ($env:DATABRICKS_VECTOR_SEARCH_ENDPOINT_TYPE) { $env:DATABRICKS_VECTOR_SEARCH_ENDPOINT_TYPE } else { "STANDARD" }
$indexName = if ($env:DATABRICKS_VECTOR_SEARCH_INDEX) { $env:DATABRICKS_VECTOR_SEARCH_INDEX } else { "$catalog.gold.semantic_legacy_documents_vs" }
$sourceTable = if ($env:DATABRICKS_VECTOR_SEARCH_SOURCE_TABLE) { $env:DATABRICKS_VECTOR_SEARCH_SOURCE_TABLE } else { "$catalog.gold.semantic_legacy_documents" }
$embeddingEndpoint = if ($env:DATABRICKS_EMBEDDING_MODEL_ENDPOINT) { $env:DATABRICKS_EMBEDDING_MODEL_ENDPOINT } else { "databricks-qwen3-embedding-0-6b" }
$profileArgs = DatabricksArgs

Write-Host "Vector Search endpoint: $endpoint ($endpointType)"
$endpointExists = $false
try {
    & databricks @profileArgs vector-search-endpoints get-endpoint $endpoint *> $null
    $endpointExists = $LASTEXITCODE -eq 0
}
catch {
    $endpointExists = $false
}

if ($endpointExists) {
    Write-Host "Endpoint already exists."
}
else {
    & databricks @profileArgs vector-search-endpoints create-endpoint $endpoint $endpointType --timeout 30m
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

$indexExists = $false
try {
    & databricks @profileArgs vector-search-indexes get-index $indexName *> $null
    $indexExists = $LASTEXITCODE -eq 0
}
catch {
    $indexExists = $false
}

if ($indexExists) {
    Write-Host "Index already exists: $indexName"
}
else {
    $body = @{
        name = $indexName
        endpoint_name = $endpoint
        primary_key = "chunk_id"
        index_type = "DELTA_SYNC"
        index_subtype = "HYBRID"
        delta_sync_index_spec = @{
            source_table = $sourceTable
            pipeline_type = "TRIGGERED"
            embedding_source_columns = @(
                @{
                    name = "chunk_text"
                    embedding_model_endpoint_name = $embeddingEndpoint
                }
            )
            columns_to_sync = @(
                "chunk_id",
                "run_id",
                "document_type",
                "source_path",
                "source_format",
                "asset_id",
                "asset_name",
                "asset_type",
                "source_system",
                "target_pattern",
                "risk_level",
                "review_priority",
                "chunk_text",
                "content_hash",
                "generated_at"
            )
        }
    }
    $bodyFile = New-TemporaryFile
    $jsonText = $body | ConvertTo-Json -Depth 10
    [System.IO.File]::WriteAllText($bodyFile.FullName, $jsonText, [System.Text.UTF8Encoding]::new($false))
    $jsonArg = "@$($bodyFile.FullName)"
    & databricks @profileArgs vector-search-indexes create-index --json $jsonArg
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Remove-Item -Path $bodyFile -Force
}

Wait-VectorIndexReady -IndexName $indexName

Write-Host "Triggering index sync: $indexName"
& databricks @profileArgs vector-search-indexes sync-index $indexName

Wait-VectorIndexReady -IndexName $indexName

Write-Host "Vector Search index status:"
& databricks @profileArgs vector-search-indexes get-index $indexName -o json
