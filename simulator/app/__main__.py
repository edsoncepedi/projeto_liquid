"""Permite executar o simulador com: python -m simulator.app"""

import uvicorn

from common.logging_setup import configure_logging

from .config import get_settings

settings = get_settings()
configure_logging(settings.log_level)
uvicorn.run(
    "simulator.app.main:app",
    host=settings.web_host,
    port=settings.web_port,
    log_config=None,
)
