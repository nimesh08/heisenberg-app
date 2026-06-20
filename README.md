# Heisenberg

[![CI](https://github.com/nimesh08/heisenberg-app/actions/workflows/ci.yml/badge.svg)](https://github.com/nimesh08/heisenberg-app/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)

Heisenberg is a multi-tenant SaaS, browser-based IDE for quantum computing. Users sign in with OAuth or passkeys, write programs in **Spinor**, **Phonon**, or **Photon**, and submit jobs to real quantum hardware on IBM Quantum, AWS Braket, or Azure Quantum — with their own provider keys (BYOK) or via paid platform shots.

This repository is the **monorepo** that holds the FastAPI backend (`jobsvc/`) and the Next.js frontend (`web/`). The Heisenberg IDE itself (a fork of `microsoft/vscode`) lives in the sibling repo [nimesh08/heisenberg-ide](https://github.com/nimesh08/heisenberg-ide). The compiler and cloud submitter live in [nimesh08/quantum-stack](https://github.com/nimesh08/quantum-stack) and are consumed via the `heisenberg-photon` and `heisenberg-spinor-submit` PyPI wheels.

## Repository layout

```
heisenberg-app/
  web/                   Next.js 15 + Auth.js v5 + shadcn/ui + Tailwind
  jobsvc/                FastAPI 0.137 + SQLModel + Postgres 16
  launcher/              `heisenberg` CLI (setup-db, run, update-ide, ...)
  docs/                  mkdocs Material site
  .github/workflows/     CI for both pipelines
```

## Quickstart (local development)

```bash
# Prerequisites: Postgres 16, Python 3.12, Node 20, pnpm, uv
git clone https://github.com/nimesh08/heisenberg-app && cd heisenberg-app
export HEISENBERG_DATABASE_URL=postgresql+psycopg://heisenberg@localhost/heisenberg
uv sync
pnpm install
uv run alembic -c jobsvc/alembic.ini upgrade head
# Two terminals:
uv run uvicorn jobsvc.main:app --reload --port 8000
pnpm --filter web dev    # localhost:3000
```

For production deployment to a fresh EC2, see [`docs/operations/install.md`](docs/operations/install.md).

## License

- All source files in this repository are dual-clear: **Apache-2.0** for our own code (every file carries `# SPDX-License-Identifier: Apache-2.0`).
- Authored by **Nimesh Cheedella** `<chnimesh0808@gmail.com>`.

## Security

Found a vulnerability? Email `chnimesh0808@gmail.com`. Please do not open a public issue.

## Project status

v1 development. See [`CHANGELOG.md`](CHANGELOG.md) for what's shipped and the [v1 plan](https://github.com/nimesh08/heisenberg-app/blob/main/docs/v1-plan.md) for what's next.
