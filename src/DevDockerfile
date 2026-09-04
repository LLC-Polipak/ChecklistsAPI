FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
COPY requirements.dev.txt .
RUN pip install --upgrade pip --no-cache-dir && pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -r requirements.dev.txt
COPY . .
