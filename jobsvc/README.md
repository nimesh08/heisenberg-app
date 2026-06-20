# jobsvc — Heisenberg backend

FastAPI + SQLModel + Postgres 16. The HTTP/WS surface for the Heisenberg platform.

Authored by Nimesh Cheedella `<chnimesh0808@gmail.com>`. Apache-2.0.

## Install + run (dev)

```bash
# from the heisenberg-app root
uv sync --all-extras
export HEISENBERG_DATABASE_URL=postgresql+psycopg://heisenberg@localhost/heisenberg
uv run alembic -c jobsvc/alembic.ini upgrade head
uv run uvicorn jobsvc.main:app --reload --port 8000
```

## Layout

```
jobsvc/
  src/jobsvc/
    main.py          FastAPI app + lifespan
    config.py        pydantic-settings
    db.py            engine + session + RLS context
    models/          SQLModel classes (one per resource)
    auth/            password hashing, JWT verify, FastAPI deps
    routers/         REST + WS routes
    services/        engine.compile, transpile, providers, registry
    middleware/      security headers, RLS context
    lsp/             pygls server + sandbox
    worker.py        claim/work loop
  alembic/           migrations
  tests/             unit + integration + regression
```

## Tests

```bash
uv run pytest -q
```

Integration tests spin up an ephemeral Postgres via `testcontainers[postgres]`.
