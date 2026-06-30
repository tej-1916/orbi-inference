FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10002 orbi-node
WORKDIR /app

COPY apps/node/pyproject.toml apps/node/README.md ./
COPY apps/node/src ./src
RUN pip install .

USER orbi-node
ENTRYPOINT ["orbi-node"]
