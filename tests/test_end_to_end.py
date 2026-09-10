"""Integracao real: simulador e middleware conversando por Modbus TCP.

Diferente dos outros testes, aqui sobem um servidor e um cliente Modbus de
verdade na porta local, exercitando pymodbus dos dois lados.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

from common.modbus_map import load_map
from middleware.app.commands import CommandHandler
from middleware.app.events import EventDetector
from middleware.app.integration import load_integration
from middleware.app.mapper import DataMapper
from middleware.app.modbus_client import ModbusReader
from middleware.app.poller import Poller
from middleware.app.state import StateManager
from simulator.app.memory import PlcMemory
from simulator.app.modbus_server import ModbusServerRunner
from simulator.app.points import PointAccess
from simulator.app.process import ProcessLogic

from conftest import INTEGRATION_PATH, MAP_PATH, RecordingPublisher


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def bancada():
    """Simulador (servidor Modbus) + middleware (cliente Modbus) ligados."""
    mapping = load_map(MAP_PATH)
    integration = load_integration(INTEGRATION_PATH)

    memory = PlcMemory(mapping.memory_size)
    points = PointAccess(memory, mapping)
    process = ProcessLogic(memory, mapping, points)
    process.initialize(voltage=121.0)

    porta = porta_livre()
    servidor = ModbusServerRunner(memory, mapping, "127.0.0.1", porta)
    await servidor.start()

    reader = ModbusReader(mapping, "127.0.0.1", porta, unit_id=1, timeout=2.0)
    publisher = RecordingPublisher()
    poller = Poller(
        mapping, integration, DataMapper(mapping), reader, StateManager(),
        EventDetector(mapping, integration), publisher,
        poll_interval=0.05, reconnect_delay=0.05,
    )
    commands = CommandHandler(mapping, integration, reader)
    assert await reader.connect()

    try:
        yield {
            "points": points, "process": process, "poller": poller,
            "publisher": publisher, "commands": commands, "reader": reader,
            "servidor": servidor, "porta": porta, "memory": memory, "mapping": mapping,
        }
    finally:
        await reader.close()
        await servidor.stop()


async def test_leitura_pelo_modbus_reflete_a_memoria_do_simulador(bancada):
    bancada["points"].write("power", 850, 1)
    bancada["process"].apply_event(2, "inserir_produto")

    await bancada["poller"].run_cycle()
    snapshot = bancada["poller"].state.previous

    assert snapshot[("power", 1)].value == 850
    assert snapshot[("voltage", None)].value == 121.0
    assert snapshot[("status", 2)].label == "PRODUTO_INSERIDO"


async def test_cadeia_completa_do_clique_ao_evento(bancada):
    """IHM -> memoria -> Modbus -> middleware -> evento."""
    poller, publisher, process = bancada["poller"], bancada["publisher"], bancada["process"]
    await poller.run_cycle()                       # linha de base

    for evento in ("inserir_produto", "iniciar_teste", "aprovar"):
        process.apply_event(1, evento)
    await poller.run_cycle()

    nomes = publisher.names()
    assert "status_changed" in nomes
    assert "approved" in nomes
    aprovado = next(e for e in publisher.events if e.name == "approved")
    assert aprovado.payload["station"] == 1
    assert aprovado.payload["count"] == 1


async def test_comando_da_aplicacao_chega_ao_clp_pelo_modbus(bancada):
    process, points = bancada["process"], bancada["points"]
    for evento in ("inserir_produto", "iniciar_teste", "reprovar"):
        process.apply_event(4, evento)
    assert points.read("total", 4) == 1

    await bancada["commands"].execute("reset", station=4)

    assert points.read("total", 4) == 0
    assert points.read("rejected", 4) == 0


async def test_middleware_reconecta_quando_o_clp_volta(bancada):
    """CLP cai, o middleware falha, o CLP volta e o ciclo continua."""
    poller, reader, servidor = bancada["poller"], bancada["reader"], bancada["servidor"]
    await poller.run_cycle()

    await servidor.stop()
    with pytest.raises(Exception):
        await poller.run_cycle()

    reader.notify_disconnected()
    poller.state.reset()
    await asyncio.sleep(0.1)

    novo = ModbusServerRunner(
        bancada["memory"], bancada["mapping"], "127.0.0.1", bancada["porta"]
    )
    await novo.start()
    try:
        assert await reader.connect()
        await poller.run_cycle()               # nova linha de base
        bancada["points"].write("power", 777, 1)
        await poller.run_cycle()
        assert "measurement_changed" in bancada["publisher"].names()
    finally:
        await novo.stop()
