# Aplicacao de EXEMPLO (dublê de teste). Build a partir da raiz do projeto.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.110" "uvicorn[standard]>=0.27" "pyyaml>=6"

COPY common/ ./common/
COPY mock_app/ ./mock_app/
COPY run_mock_app.py ./run_mock_app.py

EXPOSE 8000
CMD ["python", "run_mock_app.py"]
