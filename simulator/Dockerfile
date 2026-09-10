# Build a partir da RAIZ do projeto (o simulador usa o pacote common/ e o
# mesmo config/ do middleware):
#   docker build -f simulator/Dockerfile .
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY simulator/requirements.txt ./simulator/requirements.txt
RUN pip install --no-cache-dir -r simulator/requirements.txt

COPY common/ ./common/
COPY config/ ./config/
COPY simulator/ ./simulator/
COPY run_simulator.py ./run_simulator.py

EXPOSE 8080 5020
# O script aplica o formato de log do projeto (common/logging_setup.py).
CMD ["python", "run_simulator.py"]
