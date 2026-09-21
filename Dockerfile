# Web interface build
FROM node:20-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build -- --outDir /out/static --emptyOutDir

# Runtime
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    NTTL_CONFIG=/config/config.toml \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY nttl/ ./nttl/
COPY --from=web /out/static/ ./nttl/server/static/
RUN pip install .

VOLUME ["/config", "/data"]
EXPOSE 8765
ENTRYPOINT ["nttl"]
CMD ["web", "--host", "0.0.0.0", "--port", "8765", "--config", "/config/config.toml"]
