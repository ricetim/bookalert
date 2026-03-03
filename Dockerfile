FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Install Chromium only (skips Firefox + WebKit) + its system deps + curl for healthcheck
RUN playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY *.py ./
COPY templates/ ./templates/
COPY static/ ./static/

RUN mkdir -p /data

EXPOSE 5000

CMD ["python", "web.py"]
