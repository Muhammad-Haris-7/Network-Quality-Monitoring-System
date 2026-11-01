FROM python:3.12-slim

# ping is not included in slim images
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# The database lives in /data so it can be kept in a volume
RUN mkdir -p /data
ENV DATABASE_URL=sqlite:////data/monitor.db

EXPOSE 8000

# Platforms such as Render set PORT; locally it falls back to 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]