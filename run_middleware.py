"""Atalho de desenvolvimento: python run_middleware.py"""

import uvicorn

from common.logging_setup import configure_logging
from middleware.app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        "middleware.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_config=None,
    )
