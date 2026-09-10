# Build a partir da RAIZ do projeto:
#   docker build -f middleware/Dockerfile .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY middleware/requirements.txt ./middleware/requirements.txt
RUN pip install --no-cache-dir -r middleware/requirements.txt

COPY common/ ./common/
COPY config/ ./config/
COPY middleware/ ./middleware/
COPY run_middleware.py ./run_middleware.py

EXPOSE 8090
# O script aplica o formato de log do projeto (common/logging_setup.py).
CMD ["python", "run_middleware.py"]
