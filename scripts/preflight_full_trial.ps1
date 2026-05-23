$ErrorActionPreference = "Stop"

function Import-DotEnv {
    param([string]$Path = ".env")

    if (-not (Test-Path $Path)) {
        Write-Host "WARN: .env not found. Copy .env.example to .env before the first Databricks run."
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

function Require-Command {
    param([string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Name is required but was not found on PATH."
    }

    Write-Host "OK: $Name -> $($command.Source)"
}

function Find-GitBash {
    $candidates = @(
        "C:\Program Files\Git\bin\bash.exe",
        "C:\Program Files\Git\usr\bin\bash.exe",
        "C:\Program Files (x86)\Git\bin\bash.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

Import-DotEnv

Require-Command -Name "python"
Require-Command -Name "git"
Require-Command -Name "databricks"

$gitBash = Find-GitBash
if ($gitBash) {
    Write-Host "OK: Git Bash -> $gitBash"
}
else {
    Write-Host "WARN: Git Bash not found. Use PowerShell commands or install Git for Windows."
}

if (-not $env:DATABRICKS_PROFILE) {
    Write-Host "WARN: DATABRICKS_PROFILE is not set. Databricks CLI will use its default auth resolution."
}
else {
    Write-Host "OK: DATABRICKS_PROFILE=$env:DATABRICKS_PROFILE"
}

if ($env:DATABRICKS_WORKSPACE_ID) {
    Write-Host "OK: DATABRICKS_WORKSPACE_ID=$env:DATABRICKS_WORKSPACE_ID"
}

if (-not $env:DATABRICKS_CATALOG) {
    throw "DATABRICKS_CATALOG is required."
}
Write-Host "OK: DATABRICKS_CATALOG=$env:DATABRICKS_CATALOG"

if (-not $env:DATABRICKS_NODE_TYPE_ID) {
    throw "DATABRICKS_NODE_TYPE_ID is required."
}
Write-Host "OK: DATABRICKS_NODE_TYPE_ID=$env:DATABRICKS_NODE_TYPE_ID"

$databricksArgs = @()
if ($env:DATABRICKS_PROFILE) {
    $databricksArgs += @("--profile", $env:DATABRICKS_PROFILE)
}

$currentUserJson = & databricks @databricksArgs current-user me --output json 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Databricks CLI is not authenticated for the configured profile. Run databricks auth login against the Full Trial workspace."
}

Write-Host "OK: Databricks CLI authentication works."

$workspaceJson = & databricks @databricksArgs auth describe --output json 2>$null
if ($LASTEXITCODE -eq 0 -and $workspaceJson) {
    if ($workspaceJson -match "community" -or $workspaceJson -match "free") {
        throw "Configured Databricks auth appears to reference Free/Community Edition. Do not deploy. Re-login to the Full Trial workspace."
    }
    Write-Host "OK: Databricks auth description retrieved."
}
else {
    Write-Host "WARN: Could not inspect Databricks auth description. Confirm manually that this is the Full Trial workspace."
}

Write-Host ""
Write-Host "Preflight passed. Next safe step: bash scripts/validate_bundle.sh"
