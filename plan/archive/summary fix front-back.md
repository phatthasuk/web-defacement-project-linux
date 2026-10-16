# Summary: Frontend–Backend Integration Improvements

This document summarizes the system and interface modifications implemented to ensure seamless end-to-end integration across the Web Defacement Monitoring system.

---

## 📋 Task Summary (To-dos)

| Task | Scope | Area | Outcomes and Changes |
| :--- | :--- | :---: | :--- |
| **To-do 1** | Surface `last_error` in UI | Frontend | Display diagnostic error messages on Dashboard and Target Detail pages when check operations fail (`Failed` status). |
| **To-do 2** | Handle `accepted: false` & errors | Frontend | Gracefully handle duplicate manual trigger attempts while checks are in progress, surfacing clear user feedback notices from the API. |
| **To-do 3** | Expose diff thresholds via API | Both | Introduced `/config` endpoint to dynamically supply active backend thresholds to the frontend, removing hardcoded values. |
| **To-do 4** | Poll target detail on checking | Frontend | Automatically poll target status only while in `Checking` state, immediately invalidating query caches upon check completion. |
| **To-do 5** | Format FastAPI 422 errors | Frontend | Transformed FastAPI 422 validation error arrays into structured, human-readable form field messages. |
| **To-do 6** | Document `CHECK_TIMEOUT_SECONDS` | Backend | Added documentation and default configurations for check timeouts in `.env.example`. |

---

## 🛠️ Files Modified

### 🖥️ Backend

* **[NEW] [config.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/schemas/config.py)**: Created Pydantic schema for exposing threshold settings.
* **[NEW] [config.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/api/routes/config.py)**: Added `GET /config` endpoint.
* **[MODIFY] [main.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/app/main.py)**: Registered configuration routes.
* **[MODIFY] [test_api_routes.py](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/tests/test_api_routes.py)**: Added tests covering `/config`.
* **[MODIFY] [.env.example](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/backend/.env.example)**: Documented default `CHECK_TIMEOUT_SECONDS=90`.

### 🎨 Frontend

* **[MODIFY] [target.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/types/target.ts)**: Added `last_error` property to Target interface.
* **[NEW] [config.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/config.ts)**: Added API client method for `/config`.
* **[MODIFY] [client.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/client.ts)**: Formatted FastAPI 422 response bodies into clean error summaries.
* **[MODIFY] [client.test.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/api/client.test.ts)**: Added unit tests asserting 422 error parsing.
* **[MODIFY] [useTargetDetail.ts](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/hooks/useTargetDetail.ts)**: Configured conditional polling during check execution and added query hook for configuration settings.
* **[MODIFY] [TargetStatusBadge.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/components/TargetStatusBadge.tsx)**: Supported `title` attribute for displaying error details on tooltip hover.
* **[MODIFY] [TargetListPage.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetListPage.tsx)**: Displayed inline error messages and concurrency notices, passing `last_error` to status badges.
* **[MODIFY] [TargetDetailPage.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.tsx)**: Rendered error banners on check failures and invalidated cache queries upon check completion.
* **[MODIFY] [TargetDetailPage.test.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetDetailPage.test.tsx)** & **[TargetListPage.test.tsx](file:///C:/Users/phatthasuk.pi/Desktop/Web%20Defacement%20Project/frontend/src/pages/TargetListPage.test.tsx)**: Updated test mocks to support threshold queries and trigger mutations.

---

## 🧪 Verification Status

> [!TIP]
> All code suites satisfied security, availability, and strict type-checking criteria at time of verification.

* **Backend**
  * **pytest**: 46/46 passed.
  * **ruff check**: Passed without warnings.
  * **mypy**: Passed clean.
* **Frontend**
  * **vitest**: 20/20 passed.
  * **eslint**: Passed without warnings.
  * **tsc**: Passed TypeScript compiler type-check.
