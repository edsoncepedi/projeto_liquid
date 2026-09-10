"""Atalho de desenvolvimento: python run_mock_app.py

Porta configuravel, porque 8000 e disputada com frequencia:
    MOCK_APP_PORT=8001 python run_mock_app.py

No Docker, mantenha a porta interna em 8000 e troque so a publicacao no host
(HOST_PORT_APLICACAO no docker-compose.yml).
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "mock_app.main:app",
        host=os.environ.get("MOCK_APP_HOST", "0.0.0.0"),
        port=int(os.environ.get("MOCK_APP_PORT", "8000")),
        log_config=None,
    )
