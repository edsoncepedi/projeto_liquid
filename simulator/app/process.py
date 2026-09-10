"""Programa do CLP virtual: transicoes de ciclo e reacao a comandos.

Representa o que o CLP real faria sozinho. Deliberadamente simples: nao simula
fisica do liquidificador, apenas move o estado das estacoes e mantem os
contadores coerentes, como descrito na especificacao.
"""

from __future__ import annotations

import logging

from common.modbus_map import ModbusMap

from .memory import Change, PlcMemory
from .points import PointAccess

log = logging.getLogger("simulador.processo")

VAZIO = "VAZIO"
PRODUTO_INSERIDO = "PRODUTO_INSERIDO"
TESTANDO = "TESTANDO"
APROVADO = "APROVADO"
REPROVADO = "REPROVADO"

#: evento da IHM -> (estados de origem aceitos, estado de destino)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "inserir_produto": ((VAZIO,), PRODUTO_INSERIDO),
    "iniciar_teste": ((PRODUTO_INSERIDO,), TESTANDO),
    "aprovar": ((TESTANDO,), APROVADO),
    "reprovar": ((TESTANDO,), REPROVADO),
    "retirar_produto": ((APROVADO, REPROVADO), VAZIO),
}

#: eventos que contabilizam uma peca
COUNTED = {"aprovar": "approved", "reprovar": "rejected"}


class TransitionError(RuntimeError):
    """Transicao de estado nao permitida pelo ciclo."""


class ProcessLogic:
    def __init__(self, memory: PlcMemory, mapping: ModbusMap, points: PointAccess):
        self.memory = memory
        self.map = mapping
        self.points = points
        self._reset_point = mapping.points.get("cmd_reset")
        memory.subscribe(self._on_memory_change)

    # -- inicializacao --------------------------------------------------------
    def initialize(self, voltage: float = 121.0) -> None:
        """Deixa o CLP virtual em um estado inicial coerente."""
        if "voltage" in self.map.points:
            self.points.write("voltage", voltage, source="inicializacao")
        for station in self.map.station_ids:
            self.points.write("status", self._status_value(VAZIO), station, source="inicializacao")
            for name in ("power", "total", "approved", "rejected"):
                if name in self.map.points:
                    self.points.write(name, 0, station, source="inicializacao")
            self._clear_positions(station, source="inicializacao")
        log.info("CLP virtual inicializado: %d estacoes em %s", len(self.map.station_ids), VAZIO)

    # -- eventos de processo (acionados pela interface Web) --------------------
    def allowed_events(self, station: int) -> list[str]:
        current = self.status_label(station)
        return [name for name, (origins, _) in TRANSITIONS.items() if current in origins]

    def status_label(self, station: int) -> str:
        return self.points.label_of("status", station) or VAZIO

    def apply_event(self, station: int, event: str, *, force: bool = False) -> dict:
        if event not in TRANSITIONS:
            raise TransitionError(f"evento desconhecido: {event}")

        origins, target = TRANSITIONS[event]
        current = self.status_label(station)
        if current not in origins and not force:
            raise TransitionError(
                f"estacao {station}: {event} exige estado em {list(origins)}, mas esta em {current}"
            )

        self.points.write("status", self._status_value(target), station, source="ihm")

        counter = COUNTED.get(event)
        if counter:
            self.points.increment("total", station, source="ihm")
            self.points.increment(counter, station, source="ihm")

        if target == VAZIO:
            self.points.write("power", 0, station, source="ihm")
            self._clear_positions(station, source="ihm")

        log.info("Estacao %s: %s -> %s (evento %s)", station, current, target, event)
        return {"station": station, "event": event, "from": current, "to": target}

    # -- reset ----------------------------------------------------------------
    def reset_station(self, station: int, source: str = "ihm") -> None:
        for name in ("total", "approved", "rejected"):
            if name in self.map.points:
                self.points.write(name, 0, station, source=source)
        log.info("Estacao %s: contadores zerados (origem: %s)", station, source)

    # -- reacao a escritas Modbus vindas do middleware ------------------------
    def _on_memory_change(self, changes: list[Change]) -> None:
        """Executa a parte do programa do CLP que responde a comandos.

        O middleware escreve a coil cmd_reset; o CLP zera os contadores e
        devolve a coil para 0, exatamente como um CLP real faria.
        """
        if self._reset_point is None:
            return
        point = self._reset_point
        for change in changes:
            if change.kind != point.kind or change.current != 1:
                continue
            for station in self.map.station_ids:
                if point.base_address(station) != change.address:
                    continue
                log.info("Comando de reset recebido via Modbus na estacao %s", station)
                self.reset_station(station, source="modbus")
                self.memory.write(point.kind, change.address, [0], source="clp")

    # -- auxiliares -----------------------------------------------------------
    def _status_value(self, label: str) -> int:
        point = self.map.point("status")
        return self.map.enum_value(point.enum, label) if point.enum else 0

    def _clear_positions(self, station: int, source: str) -> None:
        point = self.map.points.get("positions")
        if point is not None:
            self.points.write(point, [False] * point.count, station, source=source)
