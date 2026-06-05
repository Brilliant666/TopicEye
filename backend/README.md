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

## Tests

```bash
cd backend
source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

Files such as `tests/test_duckdb.py`, `tests/test_cost.py`,
`scripts/duckdb_perf.py`, and `scripts/perf_baseline.py` are manual diagnostics
rather than pytest tests.

## Manual diagnostics

```bash
cd backend
python scripts/duckdb_perf.py
python scripts/perf_baseline.py
```

Operational helper scripts live under `scripts/` as well. For example,
`scripts/batch_analyze.sh` analyzes local content items that do not yet have an
AI analysis:

```bash
cd backend
./scripts/batch_analyze.sh
```
