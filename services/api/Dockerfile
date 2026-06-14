FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app/src

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg[binary]

COPY src ./src

EXPOSE 8000
CMD ["uvicorn", "aec_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
