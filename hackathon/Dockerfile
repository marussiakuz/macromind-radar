# Образ публичного MVP радара.
#
# Два решения, которые стоит объяснить:
#
# 1. **torch берём процессорной сборкой.** Обычное колесо тянет драйверы CUDA — больше
#    двух гигабайт впустую: локальные эмбеддинги считаются на процессоре, GPU не нужен.
# 2. **Модель эмбеддингов кладём внутрь образа.** `radar/vectors.py` открывает её с
#    `local_files_only=True`, то есть в рантайме за ней в сеть не пойдёт. Если её не
#    положить заранее, склейка эквивалентных технологий молча перестанет работать.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf \
    HF_HUB_OFFLINE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu \
 && pip install --no-cache-dir -r requirements.txt

# Скачивание модели — единственный шаг сборки, которому нужна сеть.
RUN HF_HUB_OFFLINE=0 python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('intfloat/multilingual-e5-small')"

COPY radar/ ./radar/
COPY samples/ ./samples/

# Каталог прогонов — это состояние: учёт расходов, квота и сохранённые разборы.
# В compose он подключается томом, иначе после перезапуска сервис забудет, сколько денег
# уже потрачено, и начнёт отсчёт заново.
RUN mkdir -p /app/radar-runs && useradd -m radar && chown -R radar:radar /app
USER radar

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "radar.public:app", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-keep-alive", "75", "--log-level", "warning"]
