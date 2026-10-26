# API-only image built from backend/ as the context (e.g. Render with Root Directory
# "backend"). The SPA is deployed separately; the root Dockerfile bundles both.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY . /app/
RUN useradd --create-home --uid 1000 app
USER app
EXPOSE 8000
# Render injects PORT; locally it defaults to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
