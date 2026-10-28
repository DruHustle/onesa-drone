FROM python:3.11-alpine@sha256:79440cc1dfa86a5f98d67efcd219726a8e9d8083cc0aafd27c7bef5976c38868
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements-runtime.lock /tmp/requirements.lock
RUN apk upgrade --no-cache     && pip install --no-cache-dir --no-deps -r /tmp/requirements.lock     && python -m pip uninstall -y pip setuptools wheel     && addgroup -g 10001 drone && adduser -D -u 10001 -G drone drone
COPY backend /app/backend
COPY autonomy /app/autonomy
COPY simulation /app/simulation
COPY integrations /app/integrations
COPY edge /app/edge
COPY scripts/migrate.py /app/scripts/migrate.py
USER 10001:10001
EXPOSE 8400
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8400/api/v1/health', timeout=2)"
CMD ["python","-m","uvicorn","backend.app.main:app","--host","0.0.0.0","--port","8400","--workers","1","--no-access-log","--no-proxy-headers","--limit-concurrency","64","--timeout-keep-alive","5"]
