# ---- frontend build ----
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- runtime ----
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt requirements-azure.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-azure.txt
COPY backend/ backend/
COPY knowledge_base/ knowledge_base/
COPY samples/ samples/
COPY data/generate.py data/generate.py
COPY data/demo/ data/demo/
COPY evals/ evals/
COPY --from=ui /ui/dist frontend/dist
# pre-download the embedding model so containers start offline-capable
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
RUN useradd -m appuser && mkdir -p audit && chown -R appuser /app
USER appuser
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}"]
