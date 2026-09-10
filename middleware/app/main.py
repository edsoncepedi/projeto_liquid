"""Middleware: Modbus -> estado -> eventos -> HTTP (e o caminho de volta).

Montagem das camadas em um so lugar; cada uma delas e testavel isoladamente:

    ModbusReader -> DataMapper -> StateManager -> EventDetector -> EventPublisher
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI

from common.logging_setup import configure_logging
from common.modbus_map import ModbusMap, load_map

from .api import router
from .commands import CommandHandler
from .config import MiddlewareSettings, get_settings
from .events import EventDetector
from .http_client import EventPublisher
from .integration import IntegrationConfig, load_integration
from .mapper import DataMapper
from .modbus_client import ModbusReader
from .poller import Poller
from .state import StateManager

log = logging.getLogger("middleware")


@dataclass
class Runtime:
    settings: MiddlewareSettings
    map: ModbusMap
    integration: IntegrationConfig
    mapper: DataMapper
    reader: ModbusReader
    state: StateManager
    detector: EventDetector
    publisher: EventPublisher
    commands: CommandHandler
    poller: Poller


def build_runtime(settings: MiddlewareSettings | None = None) -> Runtime:
    """Monta as camadas sem iniciar o polling (os testes reaproveitam isto)."""
    settings = settings or get_settings()
    mapping = load_map(settings.modbus_map_path)
    integration = load_integration(settings.integration_config_path)

    mapper = DataMapper(mapping)
    reader = ModbusReader(
        mapping,
        settings.modbus_host,
        settings.modbus_port,
        settings.modbus_unit_id,
        settings.modbus_timeout,
    )
    state = StateManager()
    detector = EventDetector(mapping, integration)
    publisher = EventPublisher(settings.application_base_url, integration.http)
    commands = CommandHandler(mapping, integration, reader)
    poller = Poller(
        mapping, integration, mapper, reader, state, detector, publisher,
        poll_interval=settings.poll_interval,
        reconnect_delay=settings.reconnect_delay,
    )
    return Runtime(
        settings, mapping, integration, mapper, reader, state,
        detector, publisher, commands, poller,
    )


def create_app(*, start_polling: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        configure_logging(settings.log_level)
        runtime = build_runtime(settings)

        log.info(
            "Mapa: %s (%s) - %d pontos, %d requisicoes de leitura por ciclo",
            runtime.map.name,
            settings.modbus_map_path,
            len(runtime.map.points),
            len(runtime.mapper.read_plan),
        )
        log.info(
            "Contrato de integracao: %s - eventos ativos: %s",
            settings.integration_config_path,
            ", ".join(rule.name for rule in runtime.integration.enabled_events()) or "nenhum",
        )
        log.info("CLP alvo: %s:%s (unit id %s)", settings.modbus_host,
                 settings.modbus_port, settings.modbus_unit_id)

        app.state.settings = settings
        app.state.map = runtime.map
        app.state.integration = runtime.integration
        app.state.mapper = runtime.mapper
        app.state.commands = runtime.commands
        app.state.poller = runtime.poller

        await runtime.publisher.start()
        if start_polling:
            runtime.poller.start()
        try:
            yield
        finally:
            await runtime.poller.stop()
            await runtime.publisher.aclose()
            await runtime.reader.close()

    app = FastAPI(
        title="Middleware CLP -> Aplicacao",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
