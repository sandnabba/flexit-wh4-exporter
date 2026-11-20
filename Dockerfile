FROM python:3.13.18-slim

WORKDIR /app
COPY --chmod=644 requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chmod=644 wh4_exporter.py points.yaml ./

USER nobody
EXPOSE 9846
ENTRYPOINT ["python", "-u", "/app/wh4_exporter.py"]
