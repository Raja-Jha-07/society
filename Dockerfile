FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UTTHAN_DATA_DIR=/data \
    UTTHAN_HOST=0.0.0.0 \
    UTTHAN_PORT=8765

WORKDIR /app
COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt \
    && useradd --create-home --uid 10001 utthan \
    && mkdir -p /data && chown utthan:utthan /data

COPY web_app.py .
COPY src ./src

USER utthan
VOLUME ["/data"]
EXPOSE 8765
CMD ["python", "web_app.py"]
