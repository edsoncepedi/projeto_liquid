"""Aplicacao do simulador: interface Web + servidor Modbus TCP no mesmo processo."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.logging_setup import configure_logging
from common.modbus_map import ModbusMap, load_map

from .api import router
from .config import SimulatorSettings, get_settings
from .memory import PlcMemory
from .modbus_server import ModbusServerRunner
from .points import PointAccess
from .process import ProcessLogic

log = logging.getLogger("simulador")

STATIC_DIR = Path(__file__).parent / "static"


@dataclass
class Runtime:
    """Objetos que compoem o CLP virtual, montados a partir do mapa."""

    settings: SimulatorSettings
    map: ModbusMap
    memory: PlcMemory
    points: PointAccess
    process: ProcessLogic


def build_runtime(settings: SimulatorSettings | None = None) -> Runtime:
    """Monta o CLP virtual sem subir servidor nenhum (usado tambem nos testes)."""
    settings = settings or get_settings()
    mapping = load_map(settings.modbus_map_path)
    memory = PlcMemory(mapping.memory_size)
    points = PointAccess(memory, mapping)
    process = ProcessLogic(memory, mapping, points)
    process.initialize(settings.initial_voltage)
    return Runtime(settings, mapping, memory, points, process)


def create_app(*, start_modbus: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = get_settings()
        configure_logging(settings.log_level)
        runtime = build_runtime(settings)
        log.info(
            "Mapa carregado: %s (%s) - %d pontos, estacoes %s",
            runtime.map.name,
            settings.modbus_map_path,
            len(runtime.map.points),
            list(runtime.map.station_ids),
        )

        app.state.settings = settings
        app.state.map = runtime.map
        app.state.memory = runtime.memory
        app.state.points = runtime.points
        app.state.process = runtime.process

        runner = None
        if start_modbus:
            runner = ModbusServerRunner(
                runtime.memory, runtime.map, settings.modbus_bind_host, settings.modbus_bind_port
            )
            await runner.start()
        log.info("Interface Web disponivel em http://%s:%s", settings.web_host, settings.web_port)

        try:
            yield
        finally:
            if runner is not None:
                await runner.stop()

    app = FastAPI(
        title="Simulador de CLP - Teste de liquidificadores",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health", tags=["infra"])
    def health() -> dict:
        return {"status": "ok", "revision": app.state.memory.revision}

    return app


app = create_app()
