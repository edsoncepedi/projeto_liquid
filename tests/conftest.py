"""Fixtures dos testes.

A maior parte dos testes nao abre socket nenhum: um leitor Modbus falso liga o
middleware direto a memoria do CLP virtual, mantendo a mesma interface do
ModbusReader real. O teste de integracao (test_end_to_end.py) usa Modbus TCP
de verdade.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.modbus_map import load_map  # noqa: E402
from middleware.app.commands import CommandHandler  # noqa: E402
from middleware.app.events import EventDetector  # noqa: E402
from middleware.app.integration import load_integration  # noqa: E402
from middleware.app.mapper import DataMapper  # noqa: E402
from middleware.app.state import StateManager  # noqa: E402
from simulator.app.memory import PlcMemory  # noqa: E402
from simulator.app.points import PointAccess  # noqa: E402
from simulator.app.process import ProcessLogic  # noqa: E402

MAP_PATH = ROOT / "config" / "modbus_map.yaml"
INTEGRATION_PATH = ROOT / "config" / "integration.yaml"


class FakeModbusReader:
    """Le e escreve direto na memoria do CLP virtual, sem rede.

    Mesma interface do ModbusReader; assim os testes exercitam o middleware de
    verdade, so trocando a infraestrutura.
    """

    def __init__(self, memory: PlcMemory, mapping):
        self.memory = memory
        self.map = mapping
        self.connected = True
        self.writes: list[tuple[str, int | None, object]] = []
        self.fail_next = False

    async def connect(self) -> bool:
        return self.connected

    def notify_disconnected(self) -> None:
        self.connected = False

    async def close(self) -> None:
        self.connected = False

    async def read_plan(self, blocks) -> dict[str, dict[int, int]]:
        if self.fail_next:
            from middleware.app.modbus_client import ModbusError

            self.fail_next = False
            raise ModbusError("falha simulada de leitura")
        raw: dict[str, dict[int, int]] = {}
        for block in blocks:
            values = self.memory.read(block.kind, block.address, block.count)
            area = raw.setdefault(block.kind, {})
            for offset, value in enumerate(values):
                area[block.address + offset] = value
        return raw

    async def write_point(self, point, value, station=None, index: int = 0) -> None:
        from common import codec

        words = codec.encode(point, value, self.map.word_order)
        address = point.item_address(station, index)
        self.memory.write(point.kind, address, words, source="middleware")
        self.writes.append((point.name, station, value))


class RecordingPublisher:
    """Publisher que so guarda os eventos, no lugar do cliente HTTP."""

    def __init__(self):
        self.events = []
        self.sent = 0
        self.failed = 0

    async def publish(self, event) -> bool:
        self.events.append(event)
        self.sent += 1
        return True

    def names(self) -> list[str]:
        return [event.name for event in self.events]

    def clear(self) -> None:
        self.events.clear()


@pytest.fixture
def mapping():
    return load_map(MAP_PATH)


@pytest.fixture
def integration():
    return load_integration(INTEGRATION_PATH)


@pytest.fixture
def plc(mapping):
    """CLP virtual pronto: memoria + pontos + programa, estacoes em VAZIO."""
    memory = PlcMemory(mapping.memory_size)
    points = PointAccess(memory, mapping)
    process = ProcessLogic(memory, mapping, points)
    process.initialize(voltage=121.0)
    return memory, points, process


@pytest.fixture
def middleware(mapping, integration, plc):
    """Middleware montado sobre o CLP virtual, sem rede e sem HTTP."""
    memory, _, _ = plc
    reader = FakeModbusReader(memory, mapping)
    return {
        "mapper": DataMapper(mapping),
        "reader": reader,
        "state": StateManager(),
        "detector": EventDetector(mapping, integration),
        "publisher": RecordingPublisher(),
        "commands": CommandHandler(mapping, integration, reader),
    }


@pytest.fixture
def poller(mapping, integration, middleware):
    """Poller completo sobre o CLP virtual, com publisher que so registra."""
    from middleware.app.poller import Poller

    return Poller(
        mapping,
        integration,
        middleware["mapper"],
        middleware["reader"],
        middleware["state"],
        middleware["detector"],
        middleware["publisher"],
        poll_interval=0.01,
        reconnect_delay=0.01,
    )
