FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    FISCYCLE_RUNTIME_ENV=production FISCYCLE_MODEL_SOURCE=local \
    FISCYCLE_MODEL_CACHE=/data/runtime \
    FISCYCLE_DATABASE_PATH=/data/state/bsf_history.sqlite3 \
    FISCYCLE_REPLAY_PATH=/data/replay YOLO_AUTOINSTALL=false YOLO_OFFLINE=true PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home ai
WORKDIR /service
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 app/ app/
COPY --chown=10001:10001 model_registry.json ./
COPY --chown=10001:10001 model_artifacts/ model_artifacts/
COPY --chown=10001:10001 tests/fixtures/ tests/fixtures/
COPY --chown=10001:10001 assets/demo_gallery/ assets/demo_gallery/
COPY --chown=10001:10001 replay/ /data/replay/
RUN mkdir -p /data/runtime /data/state /data/replay/water \
    && chown -R 10001:10001 /data /service
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:'+__import__('os').getenv('PORT','8000')+'/health')); assert d['ready']"
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
