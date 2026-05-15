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

& $python -m compileall src tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $python -c "from modern_migration_accelerator.discovery import load_text_documents; from modern_migration_accelerator.pipelines.run_accelerator import parse_documents, build_risk_register, build_blueprint, build_data_quality_plan; docs=load_text_documents('samples/legacy_metadata'); raw, assets, deps=parse_documents(docs, 'local_smoke'); risks=build_risk_register(assets, deps, 'local_smoke'); bp=build_blueprint(assets, 'local_smoke', 'migration_accelerator_dev'); dq=build_data_quality_plan(assets, 'local_smoke', 'migration_accelerator_dev'); print({'documents': len(raw), 'assets': len(assets), 'dependencies': len(deps), 'risks': len(risks), 'blueprint': len(bp), 'dq': len(dq)})"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
