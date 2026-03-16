# Testing Plan for Job Seeker Tracker

## Goals

- Backend and frontend tests run reliably in CI and locally
- Good coverage of critical paths (jobs, import, resume, auth)
- Simple pipeline: test → build → deploy via Docker Compose

---

## 1. Backend Testing (pytest)

### 1.1 Current Coverage

| Area | File | Status |
|------|------|--------|
| Jobs API | `test_jobs_api.py` | Create, get, list, analytics |
| Backup | `test_backup_api.py` | Unsupported DB error |
| Auth | `test_auth.py` | Config when disabled |
| Skills | `test_skills_api.py` | Summary |
| Resume | `test_resume_api.py` | Analyze (mocked), history |

### 1.2 Gaps to Address

1. **Resume analyze without auth** — Verify analyze works when `user=None` (no token)
2. **Resume analyze with auth** — When user present, verify `ResumeRow` is created
3. **Jobs router** — Parse URL, create job, update, delete
4. **Imports router** — Status, start (mock Celery)
5. **Resume service** — Unit tests for `match_jobs_to_skills`, `build_by_category`
6. **User service** — `get_or_create_user`

### 1.3 Test Infrastructure

- **Conftest**: `KEYCLOAK_URL` unset so auth is disabled by default
- **Fixtures**: `factories.py` with `create_job()`, `create_user()`
- **DB**: Session-scoped; use `TEST_DATABASE_URL` or `jobseeker_test` DB

### 1.4 Running Backend Tests

```bash
cd backend
pip install -r requirements.txt
export DATABASE_URL=postgresql://jobseeker:jobseeker@localhost:5432/jobseeker_test
# Ensure DB exists: createdb jobseeker_test
python -m pytest tests/ -v
```

---

## 2. Frontend Testing (Vitest + RTL)

### 2.1 Current Coverage

| Area | File | Status |
|------|------|--------|
| App | `App.test.tsx` | Backup button, nav |
| JobListPage | `JobListPage.test.tsx` | Jobs, status counts |
| ImportPage | `ImportPage.test.tsx` | Task status |
| ResumeAnalysisPage | `ResumeAnalysisPage.test.tsx` | Upload, results |

### 2.2 Gaps to Address

1. **DashboardPage** — Analytics charts render
2. **SkillsPage** — Summary, category filter
3. **JobDetailPage** — Job display, status update
4. **Auth** — Login/logout buttons when config enabled
5. **API client** — Error handling, token injection

### 2.3 Test Infrastructure

- **Setup**: `setupTests.ts` — jest-dom, fetch mock for auth config
- **Fixtures**: `test/fixtures.ts` — `createMockJob`, `createMockAnalytics`, etc.
- **Mocks**: `vi.mock("../api/client")` per test file; use inline data to avoid hoisting issues

### 2.4 Running Frontend Tests

```bash
cd frontend
npm install
npm run test
```

---

## 3. Pipeline: Test + Build

### 3.1 Flow

1. Run backend tests (requires Postgres)
2. Run frontend tests
3. If both pass → `docker compose up --build -d`

### 3.2 Script: `scripts/test-and-build.sh`

- Backend: `cd backend && pytest`
- Frontend: `cd frontend && npm run test`
- Build: `docker compose up --build -d`

### 3.3 Prerequisites

- Postgres running (e.g. `docker compose up postgres -d` for tests)
- `jobseeker_test` database created for backend tests
- Node.js and Python in PATH

---

## 4. Implementation Checklist

- [x] Resume analyze: optional auth
- [x] Backend: test for resume without auth
- [x] Backend: test for resume with auth + persistence
- [x] Backend: test for imports status/start
- [x] Frontend: add DashboardPage test
- [x] Frontend: add SkillsPage test (optional)
- [x] Pipeline script: `scripts/test-and-build.sh`
- [x] Testing plan: `docs/TESTING_PLAN.md`

## 5. Pipeline Usage

```bash
# From project root
./scripts/test-and-build.sh
```

Prerequisites:
- `pip install -r backend/requirements.txt`
- Postgres: `docker compose up postgres -d`
- Test DB: `docker compose exec postgres psql -U jobseeker -tc "SELECT 1 FROM pg_database WHERE datname='jobseeker_test'" | grep -q 1 || docker compose exec postgres psql -U jobseeker -c "CREATE DATABASE jobseeker_test;"`
