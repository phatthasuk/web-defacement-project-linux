# Project Structure

Structure of the implemented system. See [plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md) for status, design decisions and roadmap. The backend (FastAPI + Playwright + SQLite) and frontend (React + TS + Vite) are both working; run them with `docker compose up` after copying the `.env.example` in each folder.

```
Web Defacement Project/
├── backend/                      # FastAPI service
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py           # auth/session/CSRF + DB dependencies
│   │   │   └── routes/           # auth, targets, checks, snapshots, review, config, tags
│   │   ├── core/                 # config, errors, security, ssrf_guard, status, time
│   │   ├── db/                   # SQLAlchemy session/engine (SQLite)
│   │   ├── models/               # Target, Snapshot, CheckResult, User, Session, Tag, TargetTag
│   │   ├── schemas/              # Pydantic request/response models (target, check, tag, etc.)
│   │   ├── services/
│   │   │   ├── capture/          # capture.py, page_ready.py, overlays.py, ssrf_proxy.py
│   │   │   ├── diff/             # diff.py (text + visual), structure.py
│   │   │   ├── checks.py         # check orchestration + status transitions
│   │   │   ├── concurrency.py    # semaphore-limited check runner
│   │   │   ├── scheduler.py      # automated check scheduling loop with jitter
│   │   │   └── review.py         # baseline approval + acknowledgement
│   │   └── main.py               # app entrypoint, lifespan, error handlers
│   ├── alembic/                  # DB migrations (up to nested tags: b7c8d9e0f1a2)
│   ├── data/                     # local artifact storage (sqlite db, screenshots, html, text)
│   ├── scripts/
│   │   ├── create_user.py        # bootstrap a local user (interactive getpass)
│   │   └── smoke_test.py
│   └── tests/                    # pytest suite (205 tests)
└── frontend/                     # React + TS + Vite dashboard
    ├── public/
    └── src/
        ├── api/                  # API client (targets, checks, snapshots, review, config, tags)
        ├── components/           # ScreenshotCompare, TextDiffView, TargetStatusBadge, Tags, Modals
        ├── hooks/                # useAuth, useTargets, useTags, TanStack Query hooks
        ├── pages/                # Login, Target List, Target Detail, Check Detail, Tags
        └── types/
```

## Mapping to the original prototype plan

*(section references below are to [plan/archive/prototype-plan.md](plan/archive/prototype-plan.md))*

- `backend/app/api/routes` mirrors the endpoint groups in plan §7 (Targets, Checks, Snapshots, Baselines, Review), plus `auth` and `tags`.
- `backend/app/models` / `backend/app/schemas` mirror the data models (Target, Snapshot, CheckResult, User, Session, Tag, TargetTag).
- `backend/app/services/capture` and `services/diff` isolate Playwright capture from text/visual/structural diffing.
- `backend/app/services/concurrency.py` and `scheduler.py` implement bounded concurrency and scheduled check execution.
- `backend/data/*` provides local filesystem storage for screenshots/text/HTML artifacts.
- `frontend/src/pages` provides the dashboard screens (Target List, Target Detail, Check Detail, Tags Management, Login).

## Dependency and config files

- Backend: `backend/requirements.txt`, `backend/requirements-dev.txt`, `backend/pyproject.toml` (ruff/pytest/mypy config), `backend/alembic.ini`, `backend/.env.example`.
- Frontend: `frontend/package.json`, `frontend/tsconfig*.json`, `frontend/vite.config.ts`, `frontend/tailwind.config.js`, `frontend/postcss.config.js`, `frontend/eslint.config.js`, `frontend/.env.example`.
- Root: `.gitignore`, `docker-compose.yml` (production multi-stage with Nginx TLS), `docker-compose.dev.yml`.

## Planning documents

- `plan/PROJECT_PLAN.md` — the active core monitoring roadmap: current status, design principles, rejected approaches, and staged plan.
- `plan/archive/TAGS_MANAGEMENT_PLAN.md` — specifications for website tags & hierarchical taxonomy (implemented).
- `plan/MEMBER_MANAGEMENT_PLAN.md` — standalone add-on plan for Admin/Operator roles, member administration, website assignments, password/session lifecycle, audit events and scoped use of existing Tags. It owns its delivery sequence and acceptance criteria; implementation timing is not yet set.
- `plan/archive/` — all previous plans and review documents, kept for history.
- `refinement/` — dated project summaries and remediation records.

## Current Operational Status

Stage 1 is complete: the automated scheduler (`CheckScheduler`) runs unattended checks with jitter, unchanged captures consume zero disk, availability issues are distinguished from defacements, and 3 deterministic detectors (Text, Visual, Structural) are active. The Tag Management feature is implemented. See [plan/PROJECT_PLAN.md](plan/PROJECT_PLAN.md) for the core roadmap and its last recorded operational update; this documentation update does not verify the live server's status.

Member Management and website assignments remain planned as a standalone add-on, with no Stage number or dependency on notification delivery. See [plan/MEMBER_MANAGEMENT_PLAN.md](plan/MEMBER_MANAGEMENT_PLAN.md) for its scope and release criteria.
