FROM python:3.10-slim

WORKDIR /app

RUN pip3 install --no-cache-dir fastapi==0.109.2 uvicorn==0.27.1 openpyxl==3.1.2

# Copy only the mock server (minimal image)
COPY tests/e2e/mock_data_server/server.py /app/server.py

ENV MOCK_DATA_PORT=8765
ENV MOCK_DATA_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 8765

CMD ["python", "server.py"]
