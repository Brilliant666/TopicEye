# TopicEye Backend

FastAPI + SQLAlchemy + SQLite backend for TopicEye.

## Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Tests

```bash
cd backend
source venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest
```

Files such as `tests/test_duckdb.py`, `tests/test_cost.py`, and `test_perf.py`
are manual diagnostics rather than pytest tests.
