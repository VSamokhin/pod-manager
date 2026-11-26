FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    POD_DATA_DIR=/data

# Cairo for SVG/PDF rendering, fonts for titles.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libcairo2 fonts-dejavu-core fonts-liberation2 fontconfig \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 pod \
 && mkdir -p /data && chown pod:pod /data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app

USER pod
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
