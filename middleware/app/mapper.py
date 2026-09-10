"""Data Mapper: registradores crus <-> pontos do mapa.

Duas responsabilidades:
  1. montar o PLANO DE LEITURA (quais blocos contiguos ler do CLP);
  2. decodificar os blocos lidos em valores de negocio.

Nao conhece HTTP, nao guarda estado e nao decide o que e evento.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from common import codec
from common.modbus_map import BIT_KINDS, ModbusMap, PointDef

#: limites do protocolo Modbus por requisicao
MAX_REGISTERS_PER_READ = 125
MAX_BITS_PER_READ = 2000
#: lacuna maxima entre enderecos que ainda compensa ler junto (1 requisicao a
#: menos vale mais que alguns registradores inuteis)
MERGE_GAP = 8


@dataclass(frozen=True)
class ReadBlock:
    """Uma requisicao de leitura Modbus."""

    kind: str
    address: int
    count: int

    def __str__(self) -> str:
        return f"{self.kind}[{self.address}..{self.address + self.count - 1}]"


@dataclass(frozen=True)
class Reading:
    """O valor de um ponto (de uma estacao) em um ciclo de leitura."""

    point: PointDef
    station: int | None
    value: Any
    label: str | None = None

    @property
    def key(self) -> tuple[str, int | None]:
        return (self.point.name, self.station)

    def describe(self) -> str:
        alvo = f"estacao {self.station}" if self.station else "global"
        return f"{self.point.name}({alvo})"


#: estado completo lido em um ciclo
Snapshot = dict[tuple[str, int | None], Reading]


def _merge_addresses(addresses: Iterable[int], limit: int, gap: int) -> list[tuple[int, int]]:
    blocks: list[tuple[int, int]] = []
    start: int | None = None
    end: int | None = None
    for address in sorted(addresses):
        if start is None:
            start, end = address, address
            continue
        if address - end <= gap and (address - start + 1) <= limit:
            end = address
        else:
            blocks.append((start, end - start + 1))
            start, end = address, address
    if start is not None:
        blocks.append((start, end - start + 1))
    return blocks


def build_read_plan(mapping: ModbusMap) -> list[ReadBlock]:
    """Blocos contiguos que cobrem todos os pontos legiveis do mapa."""
    used: dict[str, set[int]] = defaultdict(set)
    for point, station in mapping.instances(readable_only=True):
        start = point.base_address(station)
        used[point.kind].update(range(start, start + point.span))

    plan: list[ReadBlock] = []
    for kind, addresses in used.items():
        limit = MAX_BITS_PER_READ if kind in BIT_KINDS else MAX_REGISTERS_PER_READ
        for address, count in _merge_addresses(addresses, limit, MERGE_GAP):
            plan.append(ReadBlock(kind, address, count))
    return sorted(plan, key=lambda block: (block.kind, block.address))


class DataMapper:
    """Traduz o que veio do CLP para os pontos declarados no mapa."""

    def __init__(self, mapping: ModbusMap):
        self.map = mapping
        self.read_plan = build_read_plan(mapping)

    def decode(self, raw: dict[str, dict[int, int]]) -> Snapshot:
        """raw: area -> {endereco: valor cru} (o que o ModbusReader devolveu)."""
        snapshot: Snapshot = {}
        for point, station in self.map.instances(readable_only=True):
            values = raw.get(point.kind, {})
            decoded = [
                self._decode_item(point, values, point.item_address(station, index))
                for index in range(point.count)
            ]
            value = decoded if point.is_array else decoded[0]
            label = self.map.enum_label(point.enum, value) if point.enum else None
            reading = Reading(point=point, station=station, value=value, label=label)
            snapshot[reading.key] = reading
        return snapshot

    def _decode_item(self, point: PointDef, values: dict[int, int], address: int) -> Any:
        words = [values.get(address + offset, 0) for offset in range(point.words)]
        return codec.decode(point, words, self.map.word_order)


def value_of(snapshot: Snapshot, name: str, station: int | None = None) -> Any:
    reading = snapshot.get((name, station))
    return reading.value if reading else None
