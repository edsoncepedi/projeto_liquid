"""API REST da interface Web do simulador.

A interface Web NAO fala com o middleware: ela so escreve na memoria do CLP
virtual. O middleware enxerga tudo exclusivamente pelo Modbus TCP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from common.modbus_map import ALL_KINDS, BIT_KINDS, ModbusMapError

from .process import TransitionError

router = APIRouter(prefix="/api", tags=["simulador"])


# --- modelos de requisicao ----------------------------------------------------

class PointWrite(BaseModel):
    value: Any = Field(..., description="Valor em unidade de engenharia (ja escalado)")
    station: int | None = None
    index: int | None = Field(None, description="Posicao, para pontos vetoriais")


class StationEvent(BaseModel):
    event: str
    force: bool = False


class RawWrite(BaseModel):
    kind: str
    address: int
    values: list[int]


# --- auxiliares ---------------------------------------------------------------

def _ctx(request: Request):
    state = request.app.state
    return state.memory, state.map, state.points, state.process


def _point_description(mapping, point) -> dict:
    return {
        "name": point.name,
        "label": point.display_label(),
        "kind": point.kind,
        "scope": point.scope,
        "data_type": point.data_type,
        "unit": point.unit,
        "decimals": point.decimals,
        "scale": point.scale,
        "access": point.access,
        "count": point.count,
        "item_labels": list(point.item_labels),
        "deadband": point.deadband,
        "min": point.minimum,
        "max": point.maximum,
        "enum": mapping.enum_table(point.enum) if point.enum else None,
        "description": point.description,
        "addresses": {
            str(station): point.base_address(station)
            for station in (mapping.station_ids if point.per_station else [None])
        },
    }


# --- rotas --------------------------------------------------------------------

@router.get("/map")
def get_map(request: Request) -> dict:
    """Mapa resolvido: a UI se monta a partir daqui, sem enderecos no codigo."""
    _, mapping, _, _ = _ctx(request)
    return {
        "name": mapping.name,
        "version": mapping.version,
        "source": str(mapping.source_path),
        "word_order": mapping.word_order,
        "title": request.app.state.settings.title,
        "stations": [
            {"id": s, "label": mapping.station_label(s)} for s in mapping.station_ids
        ],
        "memory_size": mapping.memory_size,
        "points": [_point_description(mapping, p) for p in mapping.points.values()],
    }


@router.get("/state")
def get_state(request: Request) -> dict:
    memory, mapping, points, process = _ctx(request)
    snapshot = points.snapshot()
    return {
        "revision": memory.revision,
        "globals": snapshot["globals"],
        "stations": {
            str(station): {
                **values,
                "status_label": process.status_label(station),
                "allowed_events": process.allowed_events(station),
            }
            for station, values in snapshot["stations"].items()
        },
    }


@router.post("/points/{name}")
def write_point(name: str, body: PointWrite, request: Request) -> dict:
    _, mapping, points, _ = _ctx(request)
    try:
        point = mapping.point(name)
    except ModbusMapError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if point.per_station and body.station is None:
        raise HTTPException(status_code=400, detail=f"ponto {name} exige 'station'")

    value = body.value
    if point.enum and isinstance(value, str):
        try:
            value = mapping.enum_value(point.enum, value)
        except ModbusMapError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        written = points.write(point, value, body.station, body.index, source="ihm")
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"point": name, "station": body.station, "index": body.index, "value": written}


@router.post("/stations/{station}/event")
def station_event(station: int, body: StationEvent, request: Request) -> dict:
    _, mapping, _, process = _ctx(request)
    if station not in mapping.station_ids:
        raise HTTPException(status_code=404, detail=f"estacao {station} nao existe no mapa")
    try:
        return process.apply_event(station, body.event, force=body.force)
    except TransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/stations/{station}/reset")
def station_reset(station: int, request: Request) -> dict:
    _, mapping, _, process = _ctx(request)
    if station not in mapping.station_ids:
        raise HTTPException(status_code=404, detail=f"estacao {station} nao existe no mapa")
    process.reset_station(station, source="ihm")
    return {"station": station, "reset": True}


@router.get("/memory")
def get_memory(request: Request, limit: int = 64) -> dict:
    """Dump da memoria Modbus para a aba de diagnostico."""
    memory, mapping, _, _ = _ctx(request)
    owners = _address_owners(mapping)
    areas = {}
    for kind in ALL_KINDS:
        values = memory.dump(kind)[:limit]
        areas[kind] = [
            {
                "address": address,
                "value": value,
                "owner": owners.get((kind, address)),
                "bit": kind in BIT_KINDS,
            }
            for address, value in enumerate(values)
        ]
    return {"revision": memory.revision, "limit": limit, "areas": areas}


@router.post("/memory")
def write_memory(body: RawWrite, request: Request) -> dict:
    """Escrita crua, util para reproduzir um estado especifico do CLP."""
    memory, _, _, _ = _ctx(request)
    if body.kind not in ALL_KINDS:
        raise HTTPException(status_code=400, detail=f"area invalida: {body.kind}")
    try:
        changes = memory.write(body.kind, body.address, body.values, source="diagnostico")
    except IndexError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"changed": len(changes)}


def _address_owners(mapping) -> dict[tuple[str, int], str]:
    owners: dict[tuple[str, int], str] = {}
    for point, station in mapping.instances():
        for index in range(point.count):
            start = point.item_address(station, index)
            label = point.name if point.count == 1 else f"{point.name}.{point.item_label(index)}"
            if station is not None:
                label = f"E{station:02d}.{label}"
            for offset in range(point.words):
                owners[(point.kind, start + offset)] = label
    return owners
