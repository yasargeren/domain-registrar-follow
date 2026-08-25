FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Istanbul

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 10001 monitor \
 && mkdir -p /app/data /app/logs \
 && chown -R monitor:monitor /app

USER monitor

CMD ["python", "-m", "app.monitor"]
