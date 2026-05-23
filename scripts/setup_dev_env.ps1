param(
    [switch]$InstallMissingTools,
    [switch]$InstallDevDeps,
    [switch]$InstallLocalSpark
)

$ErrorActionPreference = "Stop"

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

    $command = Get-Command bash -ErrorAction SilentlyContinue
    if ($command -and $command.Source -notlike "*\Windows\system32\bash.exe") {
        return $command.Source
    }

    return $null
}

function Require-Command {
    param(
        [string]$Name,
        [string]$InstallId = ""
    )

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) {
        Write-Host "OK: $Name -> $($command.Source)"
        return
    }

    if ($InstallMissingTools -and $InstallId) {
        $winget = Get-Command winget -ErrorAction SilentlyContinue
        if (-not $winget) {
            throw "$Name is missing and winget is not available."
        }
        Write-Host "Installing $Name with winget package $InstallId..."
        winget install --id $InstallId --exact --source winget --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
        return
    }

    throw "$Name is missing. Install it or rerun with -InstallMissingTools when supported."
}

Require-Command -Name "python" -InstallId "Python.Python.3.12"
Require-Command -Name "git" -InstallId "Git.Git"

$gitBash = Find-GitBash
if (-not $gitBash) {
    if ($InstallMissingTools) {
        Require-Command -Name "git" -InstallId "Git.Git"
        $gitBash = Find-GitBash
    }

    if (-not $gitBash) {
        throw "Git Bash was not found. Install Git for Windows, then rerun this script."
    }
}
Write-Host "OK: Git Bash -> $gitBash"

$docker = Get-Command docker -ErrorAction SilentlyContinue
if ($docker) {
    Write-Host "OK: docker -> $($docker.Source)"
}
else {
    Write-Host "WARN: docker is missing. Install Docker Desktop before using the SQL Server fixture."
}

$databricks = Get-Command databricks -ErrorAction SilentlyContinue
if ($databricks) {
    Write-Host "OK: databricks -> $($databricks.Source)"
}
else {
    Write-Host "WARN: databricks CLI is missing. Install/login only when the Full Trial workspace is ready."
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python was not found at $venvPython."
}

& $venvPython -m pip install --no-build-isolation -e .
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

if ($InstallDevDeps -or $InstallLocalSpark) {
    $extras = @()
    if ($InstallDevDeps) {
        $extras += "dev"
    }
    if ($InstallLocalSpark) {
        $extras += "local-spark"
    }
    & $venvPython -m pip install --no-build-isolation -e ".[$($extras -join ',')]"
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

Write-Host ""
Write-Host "Development environment ready."
Write-Host "PowerShell smoke test:"
Write-Host "  powershell -ExecutionPolicy Bypass -File .\scripts\local_smoke_test.ps1"
Write-Host "Git Bash smoke test:"
Write-Host "  & '$gitBash' scripts/local_smoke_test.sh"
