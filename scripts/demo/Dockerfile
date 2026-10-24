FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends chromium ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
WORKDIR /demo
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . playwright==1.55.0 && python -m playwright install ffmpeg
COPY scripts/demo ./scripts/demo
CMD ["python", "scripts/demo/record.py"]
