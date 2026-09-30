FROM mcr.microsoft.com/playwright/python:v1.48.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Production Compose supplies a host-selected non-root UID/GID. Only /app/data
# and /tmp are writable at runtime.
USER 1000:1000

# Only the frontend Nginx container is allowed to supply proxy headers.  Its
# address is fixed in docker-compose.yml so this remains a real trust boundary.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=172.30.0.2"]
