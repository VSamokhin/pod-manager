# Contributing

## Branches and pull requests

- `feature/<description>`: new features and enhancements
- `bugfix/<description>`: bug fixes
- `chore/<description>`: maintenance (CI/CD, dependencies, documentation)

`main` only changes through pull requests. The local `no-commit-to-branch` hook refuses commits on `main`.

## Versions and releases

Versions follow [SemVer](https://semver.org) and come from the labels of merged pull requests ([Release Drafter](https://github.com/release-drafter/release-drafter)):

| Label | Set by | Next version |
|---|---|---|
| `minor` | automatically for `feature/*` branches | 0.**X**.0 |
| `patch` | automatically for `bugfix/*`, `chore/*` and Dependabot branches | 0.0.**X** |
| `major` | by hand, only for serious, incompatible changes the maintainer agreed to | **X**.0.0 |
| `skip-changelog` | by hand | left out of the release notes |

Every PR needs exactly one of these labels (checked in CI). Every push to `main` updates a **draft** release with the computed version and notes. The maintainer publishes the draft when ready; publishing creates the `vX.Y.Z` tag and the `ghcr.io/vsamokhin/pod-manager:X.Y.Z` and `:latest` images.

## Local checks

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pre-commit install            # pre-commit and pre-push hooks
pre-commit run --all-files    # everything once
```

On commit: ruff (lint and format), mypy, bandit, codespell, gitleaks, hadolint, actionlint, workflow and Dependabot schema checks, file hygiene. On push: the test suite with the coverage gate, and pip-audit when requirements change.

## CI gates (GitHub Actions)

| Workflow | Gate |
|---|---|
| CI › Lint & static checks | all pre-commit hooks |
| CI › Tests, coverage & licence gate | pytest, branch coverage ≥ 90 % (`pyproject.toml`), no copyleft runtime dependencies |
| CI › Dependency vulnerabilities | pip-audit, no known vulnerabilities |
| CI › Security scan | bandit, nothing of medium severity or above; results in code scanning |
| CI › Docker build & image scan | image builds and starts, Trivy finds no fixable critical/high issues, Dockerfile/compose config scan |
| CodeQL | Python, JavaScript and workflow analysis (security-and-quality) |
| Dependency review | new dependencies: no moderate+ vulnerabilities, no GPL/AGPL/SSPL/non-commercial licences |
| Secret scan | gitleaks over the full history |
| Release drafter | PR labels, exactly one version label |
| OpenSSF Scorecard | supply-chain posture, weekly and on `main` |

Actions are pinned to commit SHAs; Dependabot updates them, the Python packages, the base image and the pre-commit hooks weekly.

## Licences

The project is MIT licensed. New dependencies must be permissive (MIT, BSD, Apache-2.0, ISC, PSF, …) or LGPL used as an unmodified library, and must be added to [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The licence test fails otherwise.
