# Contributing

This repository follows a lightweight Gitflow model.

## Branches

- `main`: stable baseline and future release tags.
- `develop`: integration branch for completed work.
- `feature/<short-name>`: new development branches created from `develop`.
- `release/<version>`: release stabilization branches when the MVP is ready to promote.
- `hotfix/<short-name>`: urgent fixes created from `main`.

## Commit style

Use small, reviewable commits with Conventional Commit prefixes:

- `feat:` for user-visible capability.
- `fix:` for bug fixes.
- `docs:` for documentation.
- `test:` for tests and fixtures.
- `chore:` for repo maintenance.
- `refactor:` for behavior-preserving code changes.

## Local checks

Run this before merging a feature into `develop`:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\local_smoke_test.ps1
```

When Bash is available, the equivalent is:

```bash
bash scripts/local_smoke_test.sh
```

Do not run Databricks deployment commands until the Full Trial workspace is configured.

## Pull requests

Preferred flow:

1. Push `feature/<short-name>`.
2. Open a PR into `develop`.
3. Confirm local checks pass.
4. Merge with a merge commit to preserve branch context.

For solo development, a local no-fast-forward merge into `develop` is acceptable after checks pass. Avoid treating self-approval as independent review; when branch protection is enabled, GitHub may also block approving your own PR.
