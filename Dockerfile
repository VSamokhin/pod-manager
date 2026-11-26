# Base image pinned by digest; Dependabot keeps it current.
FROM python:3.13-slim@sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50

ARG APP_VERSION=dev
LABEL org.opencontainers.image.title="POD Manager" \
      org.opencontainers.image.source="https://github.com/VSamokhin/pod-manager" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    POD_DATA_DIR=/data \
    APP_VERSION=${APP_VERSION}

# Cairo for SVG/PDF rendering, fonts for titles.
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends libcairo2 fonts-dejavu-core fonts-liberation2 fontconfig \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 pod \
 && mkdir -p /data && chown pod:pod /data

WORKDIR /app
COPY requirements.txt .
# pip and setuptools are not needed at runtime; removing them drops their vendored packages too.
RUN pip install --no-cache-dir -r requirements.txt \
 && pip uninstall -y pip setuptools wheel
COPY app ./app

USER 1000:1000
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
