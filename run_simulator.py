"""Atalho de desenvolvimento: python run_simulator.py"""

import uvicorn

from common.logging_setup import configure_logging
from simulator.app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "simulator.app.main:app",
        host=settings.web_host,
        port=settings.web_port,
        log_config=None,
    )
