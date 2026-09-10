"""Configuracao de log compartilhada.

Formato proximo ao pedido na especificacao ("[INFO] mensagem"), com horario e
origem, e sem ruido das bibliotecas a cada ciclo de polling.
"""

from __future__ import annotations

import logging

FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATEFMT = "%H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, str(level).upper(), logging.INFO),
        format=FORMAT,
        datefmt=DATEFMT,
        force=True,
    )
    # O pymodbus e o uvicorn.access falam a cada requisicao/poll; em regime
    # normal isso soterraria os eventos de processo, que sao o que interessa.
    logging.getLogger("pymodbus").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
