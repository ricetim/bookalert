FROM python:3.12-alpine

ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium-browser

WORKDIR /app
COPY pyproject.toml .

# Single RUN keeps install + cleanup in one layer so build deps
# don't bloat the final image
RUN apk add --no-cache chromium nss freetype harfbuzz ca-certificates ttf-freefont curl \
    && apk add --no-cache --virtual .build-deps gcc musl-dev python3-dev \
    && pip install --no-cache-dir -e . \
    && apk del .build-deps

COPY *.py ./
COPY templates/ ./templates/

RUN mkdir -p /data

EXPOSE 5000

CMD ["python", "web.py"]
