FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY tech-trend-searcher/package*.json ./
RUN npm ci
COPY tech-trend-searcher/ ./
ENV VITE_RADAR_API=same-origin
RUN npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1 \
    RADAR_UI_DIR=/app/ui \
    RADAR_RUNS_DIR=/app/radar-runs \
    RADAR_DEMO=1
WORKDIR /app
COPY hackathon/requirements.txt ./
# Только CPU: GPU и CUDA для приложения не требуются.
RUN pip install torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install -r requirements.txt
# Векторная модель загружается при сборке, затем работает без сети.
RUN HF_HUB_OFFLINE=0 python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"
COPY hackathon/radar/ ./radar/
COPY hackathon/samples/ ./samples/
COPY --from=frontend /ui/dist/ ./ui/
RUN useradd --uid 1000 --create-home radar \
 && mkdir -p /app/radar-runs \
 && chown -R radar:radar /app/radar-runs
USER radar
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# Один процесс: очередь анализа и квоты хранятся в его памяти.
CMD ["uvicorn", "radar.public:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
