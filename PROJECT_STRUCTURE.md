# Project Structure

Structure of the implemented system. See [plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md) for status, design decisions and roadmap. The backend (FastAPI + Playwright + SQLite) and frontend (React + TS + Vite) are both working; run them with `docker compose up` after copying the `.env.example` in each folder.

```
Web Defacement Project/
├── backend/                      # FastAPI service
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py           # auth/session/CSRF + DB dependencies
│   │   │   └── routes/           # auth, targets, checks, snapshots, review, config
│   │   ├── core/                 # config, errors, security, ssrf_guard, status, time
│   │   ├── db/                   # SQLAlchemy session/engine (SQLite)
│   │   ├── models/               # Target, Snapshot, CheckResult, User, Session
│   │   ├── schemas/              # Pydantic request/response models
│   │   ├── services/
│   │   │   ├── capture/          # capture.py, page_ready.py, overlays.py
│   │   │   ├── diff/             # diff.py (text + visual), structure.py
│   │   │   ├── checks.py         # check orchestration + status transitions
│   │   │   ├── concurrency.py    # semaphore-limited check runner
│   │   │   └── review.py         # baseline approval + acknowledgement
│   │   └── main.py               # app entrypoint, lifespan, error handlers
│   ├── alembic/                  # DB migrations (initial, auth/CSRF/lockout, structural detector)
│   ├── data/                     # local artifact storage
│   │   ├── screenshots/
│   │   ├── text/
│   │   └── html/
│   ├── scripts/
│   │   ├── create_user.py        # bootstrap a local user (interactive getpass)
│   │   └── smoke_test.py
│   └── tests/                    # pytest suite
│       └── fixtures/             # smoke-test fixture page
└── frontend/                     # React + TS + Vite dashboard
    ├── public/
    └── src/
        ├── api/                  # API client (targets, checks, snapshots, review, config)
        ├── components/           # ScreenshotCompare, TextDiffView, TargetStatusBadge, ArtifactError
        ├── hooks/                # useAuth + TanStack Query hooks
        ├── pages/                # Login, Target List, Target Detail, Check Detail
        └── types/
```

## Mapping to the original prototype plan

*(section references below are to [plan/archive/prototype-plan.md](plan/archive/prototype-plan.md))*

- `backend/app/api/routes` mirrors the endpoint groups in plan §7 (Targets, Checks, Snapshots, Baselines, Review), plus an `auth` group added later.
- `backend/app/models` / `backend/app/schemas` mirror the plan §6 data model (Target, Snapshot, CheckResult), plus `User` and `Session` for local authentication.
- `backend/app/services/capture` and `services/diff` isolate Playwright capture from text/visual diffing, matching the plan §4 pipeline (capture → diff → persist).
- `backend/app/services/concurrency.py` implements the bounded concurrency from plan §4 and §13 (`asyncio.Semaphore`, per-domain limit).
- `backend/data/*` gives local filesystem storage for screenshots/text/HTML artifacts per plan §3.
- `frontend/src/pages` maps to the three dashboard screens in plan §8 (Target List, Target Detail, Check Detail), plus a Login page.

## Dependency and config files

- Backend: `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pyproject.toml` (ruff/pytest/mypy config), `backend/alembic.ini`, `backend/.env.example`.
- Frontend: `frontend/package.json`, `frontend/tsconfig*.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/eslint.config.js`, `frontend/.env.example`.
- Root: `.gitignore`, `docker-compose.yml` (backend on `mcr.microsoft.com/playwright/python`, frontend on `node:20-alpine`).

## Planning documents

- `plan/PROJECT_PLAN.md` — the single active plan: current status, design principles, rejected approaches, and the staged roadmap.
- `plan/archive/` — all previous plans and review documents, kept for history.
- `refinement/` — dated project summaries.

## Known outstanding work

The prototype milestones are complete and three detectors (text, visual, structural) are running. The largest gaps are operational rather than functional: there is no scheduler and no notification channel, so checks must be triggered by hand and nothing tells anyone when a change is found. Several code-review findings also remain open (resource limits, full subresource IP pinning, artifact retention, durable job execution). See [plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md) for the full list and the current priority order.
