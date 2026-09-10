"""Infraestrutura Modbus do middleware.

Unica camada que conhece pymodbus. Tudo acima trabalha com pontos do mapa.
Serve tanto o CLP virtual quanto o CLP real - a diferenca esta so no host/porta.
"""

from __future__ import annotations

import asyncio
import logging

from pymodbus.client import AsyncModbusTcpClient

from common import codec
from common.modbus_map import (
    KIND_COIL,
    KIND_DISCRETE_INPUT,
    KIND_HOLDING,
    KIND_INPUT_REGISTER,
    READ_ONLY_KINDS,
    ModbusMap,
    PointDef,
)

from .mapper import ReadBlock

log = logging.getLogger("middleware.modbus")


class ModbusError(RuntimeError):
    """Falha de comunicacao ou resposta de excecao do CLP."""


class ModbusReader:
    """Cliente Modbus TCP com conexao preguicosa e reconexao."""

    def __init__(
        self,
        mapping: ModbusMap,
        host: str,
        port: int,
        unit_id: int = 1,
        timeout: float = 3.0,
    ):
        self.map = mapping
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self._client = AsyncModbusTcpClient(host, port=port, timeout=timeout)
        self._was_connected = False
        # O polling e os comandos vindos da aplicacao usam a mesma conexao;
        # o lock impede que duas requisicoes se cruzem no mesmo socket.
        self._io_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return bool(self._client.connected)

    async def connect(self) -> bool:
        """Tenta conectar. Loga apenas quando o estado muda, nao a cada ciclo."""
        if self.connected:
            return True
        await self._client.connect()
        if self.connected:
            log.info("Conectado ao Modbus %s:%s (unit id %s)", self.host, self.port, self.unit_id)
            self._was_connected = True
        elif self._was_connected:
            log.error("Falha de conexao Modbus com %s:%s", self.host, self.port)
            self._was_connected = False
        return self.connected

    def notify_disconnected(self) -> None:
        if self._was_connected:
            log.error("Conexao Modbus perdida com %s:%s", self.host, self.port)
        self._was_connected = False

    async def close(self) -> None:
        self._client.close()
        log.info("Cliente Modbus encerrado")

    # -- leitura --------------------------------------------------------------
    async def read_plan(self, blocks: list[ReadBlock]) -> dict[str, dict[int, int]]:
        """Executa o plano de leitura e devolve area -> {endereco: valor cru}."""
        result: dict[str, dict[int, int]] = {}
        for block in blocks:
            values = await self._read_block(block)
            area = result.setdefault(block.kind, {})
            for offset, value in enumerate(values):
                area[block.address + offset] = int(value)
        return result

    async def _read_block(self, block: ReadBlock) -> list[int]:
        readers = {
            KIND_COIL: (self._client.read_coils, "bits"),
            KIND_DISCRETE_INPUT: (self._client.read_discrete_inputs, "bits"),
            KIND_HOLDING: (self._client.read_holding_registers, "registers"),
            KIND_INPUT_REGISTER: (self._client.read_input_registers, "registers"),
        }
        reader, attribute = readers[block.kind]
        async with self._io_lock:
            response = await reader(block.address, count=block.count, slave=self.unit_id)
        if response.isError():
            raise ModbusError(f"erro ao ler {block}: {response}")
        return list(getattr(response, attribute))[: block.count]

    # -- escrita --------------------------------------------------------------
    async def write_point(
        self, point: PointDef, value, station: int | None = None, index: int = 0
    ) -> None:
        """Escreve UM item de um ponto, respeitando tipo e escala do mapa."""
        if point.kind in READ_ONLY_KINDS:
            raise ModbusError(f"ponto {point.name} esta em area somente leitura ({point.kind})")
        if not point.writable:
            raise ModbusError(f"ponto {point.name} nao permite escrita (access={point.access})")

        address = point.item_address(station, index)
        words = codec.encode(point, value, self.map.word_order)

        async with self._io_lock:
            if point.kind == KIND_COIL:
                response = await self._client.write_coil(
                    address, bool(words[0]), slave=self.unit_id
                )
            elif len(words) == 1:
                response = await self._client.write_register(
                    address, words[0], slave=self.unit_id
                )
            else:
                response = await self._client.write_registers(
                    address, words, slave=self.unit_id
                )

        if response.isError():
            raise ModbusError(f"erro ao escrever {point.name} em {address}: {response}")
        log.info(
            "Escrita Modbus: %s%s = %s (%s %s)",
            point.name,
            f" estacao {station}" if station else "",
            value,
            point.kind,
            address,
        )
