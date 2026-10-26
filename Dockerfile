FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
RUN groupadd --system --gid 10001 drugshield \
    && useradd --system --uid 10001 --gid drugshield --home-dir /nonexistent drugshield

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
RUN mkdir -p /var/lib/drugshield && chown 10001:10001 /var/lib/drugshield
COPY --chown=10001:10001 config ./config
COPY --chown=10001:10001 src ./src
COPY --chown=10001:10001 scripts ./scripts
COPY --chown=10001:10001 models/registry ./models/registry
COPY --chown=10001:10001 main.py ./

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers"]
