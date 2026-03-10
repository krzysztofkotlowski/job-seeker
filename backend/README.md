# Job Seeker Tracker — Backend

FastAPI 2.x, SQLAlchemy 2, Celery. PostgreSQL, Elasticsearch, Ollama/OpenAI.

See [project root README](../README.md) for full documentation, setup, and deployment.

## Quick start

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Tests

```bash
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test
pytest
```
