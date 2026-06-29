FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 orbi
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY apps/gateway/src ./apps/gateway/src
COPY apps/gateway/alembic.ini ./apps/gateway/alembic.ini
COPY apps/gateway/alembic ./apps/gateway/alembic
COPY apps/gateway/entrypoint.sh ./apps/gateway/entrypoint.sh
RUN pip install . && chmod +x apps/gateway/entrypoint.sh

USER orbi
EXPOSE 8000
CMD ["apps/gateway/entrypoint.sh"]
