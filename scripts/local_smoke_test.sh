#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}"

python -m compileall src tests
python -m unittest discover -s tests
python -c "from modern_migration_accelerator.discovery import load_text_documents; from modern_migration_accelerator.pipelines.run_accelerator import parse_documents, build_risk_register, build_blueprint, build_data_quality_plan; docs=load_text_documents('samples/legacy_metadata'); raw, assets, deps=parse_documents(docs, 'local_smoke'); risks=build_risk_register(assets, deps, 'local_smoke'); bp=build_blueprint(assets, 'local_smoke', 'migration_accelerator_dev'); dq=build_data_quality_plan(assets, 'local_smoke', 'migration_accelerator_dev'); print({'documents': len(raw), 'assets': len(assets), 'dependencies': len(deps), 'risks': len(risks), 'blueprint': len(bp), 'dq': len(dq)})"
