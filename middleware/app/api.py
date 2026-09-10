"""API de entrada do middleware (aplicacao -> middleware -> CLP).

Alem dos comandos, expoe o que o middleware esta enxergando: util para
depurar sem abrir o simulador.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .commands import CommandError

router = APIRouter(tags=["middleware"])


class CommandRequest(BaseModel):
    command: str = Field(..., description="Nome do comando em config/integration.yaml")
    station: int | None = Field(None, description="Estacao alvo, quando o ponto for por estacao")
    value: Any = Field(None, description="Valor a escrever, para comandos de modo 'set'")


@router.get("/health")
def health(request: Request) -> dict:
    poller = request.app.state.poller
    return {"status": "ok", "modbus_connected": poller.reader.connected}


@router.get("/status")
def status(request: Request) -> dict:
    """Situacao do ciclo de polling e da entrega de eventos."""
    return request.app.state.poller.stats()


@router.get("/state")
def state(request: Request) -> dict:
    """Ultimo estado conhecido pelo middleware, por ponto e estacao."""
    previous = request.app.state.poller.state.previous
    if not previous:
        return {"ready": False, "detail": "nenhum ciclo de leitura concluido ainda"}

    globais: dict[str, Any] = {}
    estacoes: dict[str, dict[str, Any]] = {}
    for (name, station), reading in previous.items():
        entry: dict[str, Any] = {"value": reading.value}
        if reading.label:
            entry["label"] = reading.label
        if station is None:
            globais[name] = entry
        else:
            estacoes.setdefault(str(station), {})[name] = entry
    return {"ready": True, "globals": globais, "stations": estacoes}


@router.get("/commands")
def list_commands(request: Request) -> dict:
    return {"commands": request.app.state.commands.available()}


@router.post("/commands")
async def run_command(body: CommandRequest, request: Request) -> dict:
    """Converte um comando da aplicacao em escrita Modbus no CLP."""
    handler = request.app.state.commands
    try:
        return await handler.execute(body.command, body.station, body.value)
    except CommandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - falha de comunicacao vira 502
        raise HTTPException(status_code=502, detail=f"falha ao escrever no CLP: {exc}") from exc


@router.get("/config")
def config(request: Request) -> dict:
    """O que esta configurado agora - conferencia rapida de ambiente."""
    settings = request.app.state.settings
    integration = request.app.state.integration
    mapping = request.app.state.map
    return {
        "modbus": {
            "host": settings.modbus_host,
            "port": settings.modbus_port,
            "unit_id": settings.modbus_unit_id,
            "poll_interval": settings.poll_interval,
        },
        "application_base_url": settings.application_base_url,
        "map": {
            "name": mapping.name,
            "source": str(mapping.source_path),
            "points": len(mapping.points),
            "stations": list(mapping.station_ids),
            "read_requests_per_cycle": len(request.app.state.mapper.read_plan),
        },
        "events": [
            {
                "name": rule.name,
                "rule": rule.rule,
                "points": list(rule.points),
                "endpoint": rule.endpoint,
                "enabled": rule.enabled,
            }
            for rule in integration.events.values()
        ],
    }
