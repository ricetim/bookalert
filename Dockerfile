FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY *.py ./
COPY templates/ ./templates/

RUN mkdir -p /data

EXPOSE 5000

CMD ["python", "web.py"]
