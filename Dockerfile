# ---- builder: network allowed here (A4 — build-time, not runtime) ----
FROM python:3.12-slim-bookworm AS builder
WORKDIR /wheels
COPY requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

# ---- runtime: no network needed from here on ----
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN useradd -m appuser
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY src/ /app/src/
COPY run.py fixtures.json /app/
COPY entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh && chown -R appuser /app
USER appuser
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
