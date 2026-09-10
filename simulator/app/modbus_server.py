"""Servidor Modbus TCP do simulador.

Roda como uma task no mesmo event loop do servidor Web, para que interface e
protocolo compartilhem a mesma memoria sem sincronizacao entre processos.
"""

from __future__ import annotations

import asyncio
import logging

from pymodbus.server import ModbusTcpServer

from common.modbus_map import ModbusMap

from .datastore import build_server_context
from .memory import PlcMemory

log = logging.getLogger("simulador.modbus")


class ModbusServerRunner:
    def __init__(self, memory: PlcMemory, mapping: ModbusMap, host: str, port: int):
        self.memory = memory
        self.map = mapping
        self.host = host
        self.port = port
        self._server: ModbusTcpServer | None = None
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        context = build_server_context(self.memory, self.map)
        self._server = ModbusTcpServer(context, address=(self.host, self.port))
        self._task = asyncio.create_task(self._server.serve_forever(), name="modbus-server")
        await asyncio.sleep(0)      # cede o loop para o socket entrar em escuta
        log.info("Servidor Modbus TCP escutando em %s:%s", self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.shutdown()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - encerramento
                pass
        log.info("Servidor Modbus TCP encerrado")
