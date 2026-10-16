# Web Defacement Monitoring System Overview

**Date:** July 22, 2026  
**Document Name:** `SummaryProject-22-7-2026.md`  

---

## 1. Executive Summary

The **Web Defacement Monitoring System** is an automated website integrity and unauthorized change detection platform. Operating similarly to visual change detection platforms (e.g., Visualping), the system periodically captures snapshots of target websites and compares them against approved reference versions (**Baseline Snapshots**).

### Core Design Principles
- **Deterministic Detection:** Uses deterministic rules rather than non-deterministic AI models. Detection currently leverages **Text Diffing** and **Visual/Pixel Diffing**; rendered HTML is stored as an audit artifact but DOM/structural diffing is not yet enabled.
- **Headless Rendering via Playwright:** Fully supports modern single-page applications (SPAs) and dynamic client-side JavaScript rendering.
- **Security-First Architecture:** Hardened against external fetch vulnerabilities through an integrated **SSRF Guard** and secure authentication using **Cookie-based Session Authentication (Argon2id)**.

---

## 2. Technology Stack

| Component | Technology | Responsibility |
| :--- | :--- | :--- |
| **Backend Framework** | **FastAPI (Python 3.11+)** | High-performance RESTful API with async I/O and Pydantic validation. |
| **Headless Browser** | **Playwright (Python)** | Drives Chromium for full-page screenshots, rendered HTML DOM, and visible text capture. |
| **Diff & Comparison** | **Pillow (PIL) & difflib** | Pillow computes pixel-level difference metrics (Visual score); difflib evaluates textual similarity (Text score). |
| **Database & ORM** | **SQLite / SQLAlchemy 2.0** | SQLite for development environment (designed for PostgreSQL portability), managed via Alembic migrations. |
| **Frontend Framework** | **React 18 + TypeScript** | Built with Vite for rapid compilation, strict type-safety, and responsive UI performance. |
| **Styling & UI** | **Tailwind CSS & Lucide Icons** | Modern Slate dark mode aesthetic with functional, accessible iconography. |
| **State & Data Fetching** | **TanStack Query (React Query)** | Client-side query caching, polling synchronization, and mutation invalidation. |
| **Security & Protection** | **SSRF Guard & Slowapi** | DNS resolution validation against private/loopback CIDRs; rate limiting on authentication routes. |
| **Containerization** | **Docker Compose** | Standardized container orchestration bundling Python Playwright and Node runtime environments. |

---

## 3. Project Structure

```text
Web Defacement Project/
├── backend/                      # Backend service (FastAPI + SQLAlchemy)
│   ├── alembic/                  # Database migration scripts
│   ├── app/
│   │   ├── api/                  # API routes (targets, checks, snapshots, review, config, auth)
│   │   ├── core/                 # Settings, SSRF Guard, Status Machine, Security
│   │   ├── db/                   # Database session & Base model
│   │   ├── models/               # SQLAlchemy Models (Target, Snapshot, CheckResult, User, Session)
│   │   ├── schemas/              # Pydantic validation schemas
│   │   └── services/
│   │       ├── capture/          # Playwright Snapshot Capture engine
│   │       ├── diff/             # Visual (PIL) & Text (difflib) comparator
│   │       └── checks.py         # Check execution pipeline & evaluation orchestration
│   ├── data/                     # Local artifact storage (Screenshots, HTML, Text artifacts)
│   ├── scripts/                  # Helper scripts (Admin user bootstrap, smoke testing)
│   └── tests/                    # Pytest suite covering API, Capture, Diff, SSRF, Auth
├── frontend/                     # Operator dashboard (React + TypeScript + Vite)
│   ├── public/                   # Static assets
│   └── src/
│       ├── api/                  # API client modules
│       ├── components/           # Reusable UI components (TextDiffView, ScreenshotCompare, StatusBadge)
│       ├── hooks/                # Custom React hooks (useAuth, useTargets, useTargetDetail)
│       ├── pages/                # Application routes (LoginPage, TargetListPage, TargetDetailPage, CheckDetailPage)
│       └── types/                # TypeScript interface definitions
├── plan/                         # Architecture analysis and roadmap documents
│   ├── production-grade-plan-final.md           # Authoritative system plan
│   ├── prototype-plan.md                        # Initial prototype roadmap
│   ├── local-authentication-security-plan.md    # Authentication security standard
│   ├── local-authentication-implementation-review.md # Auth review summary
│   └── frontend-stack-recommendation.md         # Frontend stack evaluation
├── docker-compose.yml            # Docker orchestration file
├── PROJECT_STRUCTURE.md          # Directory structure documentation
└── SummaryProject-22-7-2026.md   # Project overview record
```

> Note: PROJECT_STRUCTURE.md and docker-compose.yml comments initially stated that application code was not present; this was outdated text contradicted by the fully functioning backend and frontend codebases.

---

## 4. Implemented Features & Core Subsystems

### 4.1 Backend & Core Engine
1. **Target Management System (`backend/app/api/routes/targets.py`):**
   - Supports creating, reading, updating target name/active state, and soft-deleting targets. (Target URL updates were disallowed at this stage).
2. **Snapshot Capture Engine (`backend/app/services/capture/capture.py`):**
   - Orchestrates Playwright browser instances, waiting for the `networkidle` state.
   - Captures three persistent artifacts: Full-page PNG screenshot, visible body text, and fully rendered HTML.
   - Enforces file size ceilings (`MAX_ARTIFACT_SIZE_MB`).
3. **Diff & Comparator Service (`backend/app/services/diff/diff.py`):**
   - **Text Diffing:** Compares text changes with `difflib.SequenceMatcher`, with line-based fallbacks for documents exceeding 100 KB.
   - **Visual Diffing:** Compares pixel variance with Pillow (`ImageChops.difference`) offloaded via `asyncio.to_thread` to preserve event loop responsiveness.
4. **Status State Machine (`backend/app/core/status.py`):**
   - Strictly enforces target lifecycle state transitions:
     - `Never Checked` ➔ `Checking`
     - `Checking` ➔ `OK` | `Changed` | `Failed`
     - `Changed` ➔ `Acknowledged` | `OK` | `Checking`
5. **SSRF Guard & Security (`backend/app/core/ssrf_guard.py` & `auth.py`):**
   - **SSRF Guard:** Performs pre-flight DNS resolution to block connections targeting private IP blocks (127.0.0.1, 10.0.0.0/8, 192.168.0.0/16), loopback, link-local, or IPv6-mapped addresses, while restricting redirects.
   - **Authentication:** Issues `HttpOnly` + `SameSite=Lax` session cookies, hashes passwords with `Argon2id`, and enforces rate limiting (`5/minute`) with progressive account lockout on failed login attempts.

### 4.2 Frontend Dashboard
1. **LoginPage (`frontend/src/pages/LoginPage.tsx`):**
   - Secure authentication view with brute-force protection feedback.
2. **TargetListPage (`frontend/src/pages/TargetListPage.tsx`):**
   - Displays all monitored websites with color-coded status badges (`OK`, `Changed`, `Failed`, `Checking`).
   - Includes controls to create new targets and trigger immediate checks.
3. **TargetDetailPage (`frontend/src/pages/TargetDetailPage.tsx`):**
   - Displays target metadata, historical check timelines, and snapshot logs.
   - Enables operators to review and promote snapshots as the active baseline.
4. **CheckDetailPage (`frontend/src/pages/CheckDetailPage.tsx`):**
   - Detailed side-by-side visual diff comparison interface.
   - Integrated text diff view highlighting added and deleted content.

---

## 5. Future Roadmap & Production Readiness

Based on the architectural specifications in `plan/production-grade-plan-final.md`, planned future extensions include:

1. **False-Positive Control & Baseline Governance:**
   - **Ignore-Selectors:** Ability to exclude noisy DOM subtrees (ads, clocks, dynamic carousels).
   - **Visual Masking:** Canvas masks to suppress diffing over regions with high dynamic fluctuation.
2. **Verification Queue & Retry Logic:**
   - Staging verification passes to confirm changes before escalating critical alerts, eliminating transient network blips.
3. **Multi-Channel Alerting Engine:**
   - Outbound notifications via SMTP Email, Webhooks, Slack, Microsoft Teams, or Discord on `Changed` or `Failed` events.
4. **Production Infrastructure Scaling:**
   - Migration from SQLite to PostgreSQL.
   - Offloading artifact storage from local disk to S3-compatible object stores (Amazon S3 / MinIO).
   - Celery + Redis or Temporal for distributed worker task orchestration.

---

## 6. Historical Record & Workspace Status

- **Version Control Note:** Initial git history could not be verified in this early snapshot due to incomplete `.git` directory state.
- **Record Attribution:** This document records the baseline architectural status as of July 22, 2026.
