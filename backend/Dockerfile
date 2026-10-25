FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY requirements-local-ai.txt .
ARG INSTALL_LOCAL_AI=false
RUN if [ "$INSTALL_LOCAL_AI" = "true" ]; then pip install --no-cache-dir -r requirements-local-ai.txt; fi

COPY . .

CMD ["sh", "-c", "python -m scripts.migrate && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
