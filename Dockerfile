FROM python:3.12-alpine

# System Chromium from Alpine repos (avoids Playwright's bundled ~500MB download)
# Build deps are installed temporarily for pip packages with C extensions (e.g. MarkupSafe)
RUN apk add --no-cache chromium nss freetype harfbuzz ca-certificates ttf-freefont curl \
    && apk add --no-cache --virtual .build-deps gcc musl-dev python3-dev

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e . \
    && apk del .build-deps

COPY *.py ./
COPY templates/ ./templates/

RUN mkdir -p /data

EXPOSE 5000

CMD ["python", "web.py"]
