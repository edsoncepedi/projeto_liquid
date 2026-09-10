"""Acesso a memoria do CLP virtual em termos de PONTOS do mapa.

Camada fina entre a memoria crua (enderecos) e a logica/UI (nomes de negocio).
Nenhum endereco aparece acima desta camada.
"""

from __future__ import annotations

from typing import Any

from common import codec
from common.modbus_map import ModbusMap, PointDef

from .memory import PlcMemory


class PointAccess:
    def __init__(self, memory: PlcMemory, mapping: ModbusMap):
        self.memory = memory
        self.map = mapping

    # -- leitura --------------------------------------------------------------
    def read(self, name: str | PointDef, station: int | None = None) -> Any:
        point = self._point(name)
        if point.is_array:
            return [self.read_item(point, station, i) for i in range(point.count)]
        return self.read_item(point, station, 0)

    def read_item(self, name: str | PointDef, station: int | None, index: int = 0) -> Any:
        point = self._point(name)
        address = point.item_address(station, index)
        words = self.memory.read(point.kind, address, point.words)
        return codec.decode(point, words, self.map.word_order)

    def label_of(self, name: str | PointDef, station: int | None = None) -> str | None:
        point = self._point(name)
        return self.map.enum_label(point.enum, self.read(point, station))

    # -- escrita --------------------------------------------------------------
    def write(
        self,
        name: str | PointDef,
        value: Any,
        station: int | None = None,
        index: int | None = None,
        source: str = "simulador",
    ) -> Any:
        point = self._point(name)
        if point.is_array and index is None:
            values = list(value)
            if len(values) != point.count:
                raise ValueError(
                    f"ponto {point.name} espera {point.count} valores, recebeu {len(values)}"
                )
            return [
                self.write(point, item, station, i, source) for i, item in enumerate(values)
            ]

        value = codec.clamp(point, value)
        words = codec.encode(point, value, self.map.word_order)
        address = point.item_address(station, index or 0)
        self.memory.write(point.kind, address, words, source=source)
        return value

    def increment(
        self, name: str | PointDef, station: int | None = None, step: int = 1, source: str = "simulador"
    ) -> Any:
        current = self.read(name, station)
        return self.write(name, current + step, station, source=source)

    # -- visao completa -------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        """Estado de todos os pontos, agrupado por escopo/estacao."""
        globals_: dict[str, Any] = {}
        stations: dict[int, dict[str, Any]] = {s: {} for s in self.map.station_ids}

        for point, station in self.map.instances():
            value = self.read(point, station)
            entry: dict[str, Any] = {"value": value}
            if point.enum:
                entry["label"] = self.map.enum_label(point.enum, value)
            if station is None:
                globals_[point.name] = entry
            else:
                stations[station][point.name] = entry

        return {"globals": globals_, "stations": stations}

    def _point(self, name: str | PointDef) -> PointDef:
        return name if isinstance(name, PointDef) else self.map.point(name)
