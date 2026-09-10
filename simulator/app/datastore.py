"""Ponte entre a memoria do CLP virtual e o datastore do pymodbus.

O pymodbus nao guarda estado nenhum aqui: todo acesso e delegado a PlcMemory.
Assim, o que o middleware le pelo Modbus e exatamente o que a interface Web
mostra, sem copia intermediaria.
"""

from __future__ import annotations

import logging

from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
from pymodbus.datastore.store import BaseModbusDataBlock

from common.modbus_map import (
    KIND_COIL,
    KIND_DISCRETE_INPUT,
    KIND_HOLDING,
    KIND_INPUT_REGISTER,
    ModbusMap,
)

from .memory import PlcMemory

log = logging.getLogger("simulador.modbus")


class MemoryDataBlock(BaseModbusDataBlock):
    """Bloco de dados do pymodbus que le e escreve direto na PlcMemory."""

    def __init__(self, memory: PlcMemory, kind: str):
        self.memory = memory
        self.kind = kind
        self.address = 0
        self.default_value = 0
        self.values = []          # exigido pela classe base; nao usado

    def validate(self, address: int, count: int = 1) -> bool:
        return self.memory.validate(self.kind, address, count)

    def getValues(self, address: int, count: int = 1) -> list[int]:
        return self.memory.read(self.kind, address, count)

    def setValues(self, address: int, values) -> None:
        values = values if isinstance(values, (list, tuple)) else [values]
        changes = self.memory.write(self.kind, address, values, source="modbus")
        for change in changes:
            log.info(
                "Escrita Modbus: %s %s = %s (antes %s)",
                change.kind, change.address, change.current, change.previous,
            )

    def __str__(self) -> str:
        return f"MemoryDataBlock({self.kind}, size={self.memory.size(self.kind)})"


def build_server_context(memory: PlcMemory, mapping: ModbusMap) -> ModbusServerContext:
    """Contexto Modbus com enderecamento direto (zero_mode).

    zero_mode=True faz o endereco do protocolo ser o mesmo do mapa: coil 0 do
    YAML e a coil 0 lida pelo middleware, sem deslocamento de 1.
    """
    slave = ModbusSlaveContext(
        co=MemoryDataBlock(memory, KIND_COIL),
        di=MemoryDataBlock(memory, KIND_DISCRETE_INPUT),
        hr=MemoryDataBlock(memory, KIND_HOLDING),
        ir=MemoryDataBlock(memory, KIND_INPUT_REGISTER),
        zero_mode=True,
    )
    log.debug("Contexto Modbus criado para o mapa %s", mapping.name)
    return ModbusServerContext(slaves=slave, single=True)
