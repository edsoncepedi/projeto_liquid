"""Modelo do mapa Modbus.

Toda a informacao de enderecamento vive em YAML (config/modbus_map.yaml).
Este modulo apenas le esse arquivo e o expoe como objetos. Trocar o CLP
virtual pelo CLP real deve exigir apenas a troca do YAML.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

# --- tipos de area Modbus ----------------------------------------------------
KIND_COIL = "coil"
KIND_DISCRETE_INPUT = "discrete_input"
KIND_HOLDING = "holding_register"
KIND_INPUT_REGISTER = "input_register"

ALL_KINDS = (KIND_COIL, KIND_DISCRETE_INPUT, KIND_HOLDING, KIND_INPUT_REGISTER)
BIT_KINDS = (KIND_COIL, KIND_DISCRETE_INPUT)
REGISTER_KINDS = (KIND_HOLDING, KIND_INPUT_REGISTER)
#: areas que o mestre Modbus nao pode escrever (somente leitura no protocolo)
READ_ONLY_KINDS = (KIND_DISCRETE_INPUT, KIND_INPUT_REGISTER)

#: quantos registradores de 16 bits cada tipo de dado ocupa
DATA_TYPE_WORDS = {"bool": 1, "uint16": 1, "int16": 1, "uint32": 2, "int32": 2}

SCOPE_GLOBAL = "global"
SCOPE_STATION = "station"


class ModbusMapError(ValueError):
    """Mapa Modbus invalido ou inconsistente."""


@dataclass(frozen=True)
class PointDef:
    """Um ponto do mapa: um valor logico e onde ele mora na memoria Modbus."""

    name: str
    kind: str
    address: int
    scope: str = SCOPE_GLOBAL
    stride: int = 0
    count: int = 1                     # > 1 = vetor (ex.: posicoes P/V1..V12)
    data_type: str = "uint16"
    scale: float = 1.0
    unit: str | None = None
    decimals: int = 0
    enum: str | None = None
    access: str = "rw"
    deadband: float = 0.0
    label: str | None = None
    item_labels: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    # -- caracteristicas derivadas -------------------------------------------
    @property
    def is_bit(self) -> bool:
        return self.kind in BIT_KINDS

    @property
    def is_array(self) -> bool:
        return self.count > 1

    @property
    def words(self) -> int:
        """Registradores (ou bits) ocupados por UM item deste ponto."""
        return 1 if self.is_bit else DATA_TYPE_WORDS[self.data_type]

    @property
    def span(self) -> int:
        """Enderecos ocupados por todo o ponto em uma estacao."""
        return self.words * self.count

    @property
    def readable(self) -> bool:
        return "r" in self.access

    @property
    def writable(self) -> bool:
        return "w" in self.access

    @property
    def per_station(self) -> bool:
        return self.scope == SCOPE_STATION

    def base_address(self, station: int | None = None) -> int:
        """Endereco inicial do ponto para a estacao informada."""
        if not self.per_station:
            return self.address
        if station is None:
            raise ModbusMapError(f"ponto {self.name} exige uma estacao")
        return self.address + (station - 1) * self.stride

    def item_address(self, station: int | None, index: int = 0) -> int:
        if not 0 <= index < self.count:
            raise ModbusMapError(
                f"indice {index} fora do ponto {self.name} (count={self.count})"
            )
        return self.base_address(station) + index * self.words

    def item_label(self, index: int) -> str:
        if index < len(self.item_labels):
            return self.item_labels[index]
        return f"{self.name}[{index}]"

    def display_label(self) -> str:
        return self.label or self.name


@dataclass(frozen=True)
class ModbusMap:
    """O mapa completo, carregado do YAML."""

    version: int
    name: str
    word_order: str
    station_ids: tuple[int, ...]
    station_labels: dict[int, str]
    memory_size: dict[str, int]
    enums: dict[str, dict[int, str]]
    points: dict[str, PointDef]
    source_path: Path | None = None

    # -- acesso ---------------------------------------------------------------
    def point(self, name: str) -> PointDef:
        try:
            return self.points[name]
        except KeyError:
            raise ModbusMapError(f"ponto desconhecido: {name}") from None

    def points_of_kind(self, kind: str) -> list[PointDef]:
        return [p for p in self.points.values() if p.kind == kind]

    def instances(
        self, *, readable_only: bool = False
    ) -> Iterator[tuple[PointDef, int | None]]:
        """Itera (ponto, estacao) para cada instancia concreta do mapa."""
        for point in self.points.values():
            if readable_only and not point.readable:
                continue
            if point.per_station:
                for station in self.station_ids:
                    yield point, station
            else:
                yield point, None

    def station_label(self, station: int) -> str:
        return self.station_labels.get(station, f"ESTACAO {station:02d}")

    # -- enums ----------------------------------------------------------------
    def enum_label(self, enum_name: str | None, value: Any) -> str | None:
        if not enum_name:
            return None
        table = self.enums.get(enum_name, {})
        try:
            return table.get(int(value))
        except (TypeError, ValueError):
            return None

    def enum_value(self, enum_name: str, label: str) -> int:
        for value, name in self.enums.get(enum_name, {}).items():
            if name == label:
                return value
        raise ModbusMapError(f"rotulo {label} nao existe no enum {enum_name}")

    def enum_table(self, enum_name: str) -> dict[int, str]:
        return dict(self.enums.get(enum_name, {}))

    def size_of(self, kind: str) -> int:
        return self.memory_size.get(kind, 0)


# --- carregamento -------------------------------------------------------------

def _as_tuple(value: Any) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(str(item) for item in value)


def _build_point(raw: dict[str, Any]) -> PointDef:
    missing = [k for k in ("name", "kind", "address") if k not in raw]
    if missing:
        raise ModbusMapError(f"ponto sem campos obrigatorios {missing}: {raw!r}")

    name = raw["name"]
    kind = raw["kind"]
    if kind not in ALL_KINDS:
        raise ModbusMapError(f"kind invalido {kind} no ponto {name}")

    scope = raw.get("scope", SCOPE_GLOBAL)
    if scope not in (SCOPE_GLOBAL, SCOPE_STATION):
        raise ModbusMapError(f"scope invalido {scope} no ponto {name}")

    data_type = "bool" if kind in BIT_KINDS else raw.get("data_type", "uint16")
    if data_type not in DATA_TYPE_WORDS:
        raise ModbusMapError(f"data_type invalido {data_type} no ponto {name}")

    if scope == SCOPE_STATION and "stride" not in raw:
        raise ModbusMapError(f"ponto de estacao {name} exige stride")

    access = raw.get("access", "rw")
    if kind in READ_ONLY_KINDS and "w" in access:
        raise ModbusMapError(
            f"ponto {name} esta em area somente leitura ({kind}) "
            f"e nao pode ter access {access}"
        )

    return PointDef(
        name=name,
        kind=kind,
        address=int(raw["address"]),
        scope=scope,
        stride=int(raw.get("stride", 0)),
        count=int(raw.get("count", 1)),
        data_type=data_type,
        scale=float(raw.get("scale", 1.0)),
        unit=raw.get("unit"),
        decimals=int(raw.get("decimals", 0)),
        enum=raw.get("enum"),
        access=access,
        deadband=float(raw.get("deadband", 0.0)),
        label=raw.get("label"),
        item_labels=_as_tuple(raw.get("item_labels")),
        minimum=raw.get("min"),
        maximum=raw.get("max"),
        description=str(raw.get("description", "")).strip(),
    )


def _check_overlaps(mapping: ModbusMap) -> None:
    """Impede que dois pontos ocupem o mesmo endereco.

    E o erro mais provavel ao editar o YAML na mao, e silencioso em producao.
    """
    used: dict[tuple[str, int], str] = {}
    for point, station in mapping.instances():
        owner = point.name if station is None else f"{point.name}[estacao {station}]"
        start = point.base_address(station)
        for address in range(start, start + point.span):
            key = (point.kind, address)
            if key in used:
                raise ModbusMapError(
                    f"conflito de endereco: {owner} e {used[key]} "
                    f"usam {point.kind} {address}"
                )
            used[key] = owner
            limit = mapping.size_of(point.kind)
            if limit and address >= limit:
                raise ModbusMapError(
                    f"{owner} usa {point.kind} {address}, fora do "
                    f"tamanho configurado ({limit})"
                )


def load_map(path: str | Path) -> ModbusMap:
    """Le e valida o mapa Modbus a partir de um arquivo YAML."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    stations = raw.get("stations") or {}
    station_ids = tuple(int(s) for s in stations.get("ids", [1]))
    station_labels = {int(k): str(v) for k, v in (stations.get("labels") or {}).items()}

    enums = {
        enum_name: {int(k): str(v) for k, v in (table or {}).items()}
        for enum_name, table in (raw.get("enums") or {}).items()
    }

    memory_size = {kind: 512 for kind in ALL_KINDS}
    memory_size.update({k: int(v) for k, v in (raw.get("memory_size") or {}).items()})

    points: dict[str, PointDef] = {}
    for entry in raw.get("points") or []:
        point = _build_point(entry)
        if point.name in points:
            raise ModbusMapError(f"ponto duplicado no mapa: {point.name}")
        if point.enum and point.enum not in enums:
            raise ModbusMapError(
                f"ponto {point.name} referencia enum inexistente {point.enum}"
            )
        points[point.name] = point

    word_order = str(raw.get("word_order", "big")).lower()
    if word_order not in ("big", "little"):
        raise ModbusMapError(f"word_order invalido: {word_order}")

    mapping = ModbusMap(
        version=int(raw.get("version", 1)),
        name=str(raw.get("name", path.stem)),
        word_order=word_order,
        station_ids=station_ids,
        station_labels=station_labels,
        memory_size=memory_size,
        enums=enums,
        points=points,
        source_path=path,
    )
    _check_overlaps(mapping)
    return mapping
