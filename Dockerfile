FROM python:3.11-slim

WORKDIR /app

COPY common /app/common
COPY service /app/service
COPY demo /app/demo
COPY tests /app/tests
COPY requirements.txt /app/requirements.txt
COPY README.md /app/README.md

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000 8001 8002

CMD ["bash", "-lc", "uvicorn service.app:app --host 0.0.0.0 --port ${PORT:-8000}"]
