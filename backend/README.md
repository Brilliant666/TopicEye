# TopicEye Backend

FastAPI + SQLAlchemy + SQLite backend for TopicEye.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
./venv/bin/python -m uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Database backend

The backend runtime supports two OLTP profiles through `DATABASE_URL`:

- SQLite: `sqlite+aiosqlite:///./topiceye.db`
- PostgreSQL: `postgresql+asyncpg://user:password@host:5432/topiceye`

SQLAlchemy remains the write path. DuckDB is the analytical read layer and
attaches the configured OLTP database in read-only mode. Backend-specific URL
normalization, DuckDB attach SQL, diagnostics, and secret redaction live in
`app/core/db_backend.py`.

Important boundaries:

- Startup table creation uses SQLAlchemy metadata for both supported backends.
- Local upgrade helpers in `app/main.py` are SQLite-only compatibility patches
  for existing developer databases.
- PostgreSQL production upgrades should be handled by a migration tool such as
  Alembic before relying on long-lived production data.
- `DATABASE_SQLITE_DOMAIN_SPLIT_ENABLED` currently exposes deterministic SQLite
  domain database URLs for future routing work; repositories still use the
  primary `DATABASE_URL`.

## Tests

```bash
cd backend
source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

Files such as `scripts/duckdb_check.py`, `scripts/estimate_llm_cost.py`,
`scripts/duckdb_perf.py`, and `scripts/perf_baseline.py` are manual diagnostics
rather than pytest tests.

## Manual diagnostics

```bash
cd backend
python scripts/duckdb_perf.py
python scripts/perf_baseline.py
python scripts/duckdb_check.py
```

Operational helper scripts live under `scripts/` as well. For example,
`scripts/batch_analyze.sh` analyzes pending content through the HTTP API, so it
works with either SQLite or PostgreSQL as long as the backend is running:

```bash
cd backend
AUTH_TOKEN=<login-token> BASE_URL=http://localhost:8000 ./scripts/batch_analyze.sh
```
