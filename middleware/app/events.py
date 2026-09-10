"""Event Detector: mudancas de estado viram eventos de negocio.

As regras (quais pontos, qual endpoint, qual payload) vem de
config/integration.yaml. Este modulo implementa apenas os TIPOS de regra:

    enum_change       status mudou            -> status_changed
    counter_increase  contador subiu          -> approved / rejected
    value_change      medicao/contagem mudou  -> measurement_changed / counter_changed

Nao faz HTTP: apenas devolve os eventos a enviar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.modbus_map import ModbusMap

from .integration import (
    RULE_COUNTER_INCREASE,
    RULE_ENUM_CHANGE,
    RULE_VALUE_CHANGE,
    EventRule,
    IntegrationConfig,
)
from .mapper import Snapshot
from .state import Change

log = logging.getLogger("middleware.eventos")


@dataclass(frozen=True)
class Event:
    """Um evento pronto para ser enviado a aplicacao."""

    name: str
    endpoint: str
    method: str
    payload: dict[str, Any]
    station: int | None = None
    summary: str = ""

    def describe(self) -> str:
        return self.summary or f"{self.name} (estacao {self.station})"


def render_payload(template: Any, context: dict[str, Any]) -> Any:
    """Substitui os placeholders do payload configurado.

    Um campo que seja exatamente "{chave}" preserva o TIPO do valor (numero
    continua numero); placeholders no meio de um texto viram texto.
    """
    if isinstance(template, dict):
        return {key: render_payload(value, context) for key, value in template.items()}
    if isinstance(template, list):
        return [render_payload(item, context) for item in template]
    if isinstance(template, str):
        stripped = template.strip()
        if stripped.startswith("{") and stripped.endswith("}") and stripped.count("{") == 1:
            return context.get(stripped[1:-1])
        try:
            return template.format(**context)
        except (KeyError, IndexError):
            return template
    return template


class EventDetector:
    def __init__(self, mapping: ModbusMap, integration: IntegrationConfig):
        self.map = mapping
        self.integration = integration
        self._validate_points()

    def _validate_points(self) -> None:
        """Falha cedo se o contrato citar um ponto que o mapa nao tem."""
        for rule in self.integration.events.values():
            for name in rule.points:
                if name not in self.map.points:
                    raise ValueError(
                        f"evento {rule.name} referencia o ponto {name}, "
                        f"que nao existe no mapa {self.map.name}"
                    )

    # -- deteccao -------------------------------------------------------------
    def detect(self, changes: list[Change], current: Snapshot) -> list[Event]:
        if not changes:
            return []
        by_key = {change.key: change for change in changes}
        events: list[Event] = []
        for rule in self.integration.enabled_events():
            if rule.rule == RULE_ENUM_CHANGE:
                events.extend(self._enum_change(rule, by_key, current))
            elif rule.rule == RULE_COUNTER_INCREASE:
                events.extend(self._counter_increase(rule, by_key, current))
            elif rule.rule == RULE_VALUE_CHANGE:
                events.extend(self._value_change(rule, by_key, current))
        return events

    def _enum_change(self, rule, by_key, current) -> list[Event]:
        events = []
        for change in self._changes_for(rule, by_key):
            context = self._context(change)
            antes = change.previous_label or change.previous
            agora = change.current_label or change.current
            events.append(
                self._build(
                    rule,
                    change.station,
                    context,
                    f"Estacao {change.station}: status alterado {antes} -> {agora}",
                )
            )
        return events

    def _counter_increase(self, rule, by_key, current) -> list[Event]:
        events = []
        for change in self._changes_for(rule, by_key):
            delta = change.delta
            if delta is None or delta <= 0:
                continue          # zerar contador nao e aprovacao/reprovacao
            context = self._context(change)
            events.append(
                self._build(
                    rule,
                    change.station,
                    context,
                    f"Estacao {change.station}: {rule.name} "
                    f"(+{delta:g}, acumulado {change.current:g})",
                )
            )
        return events

    def _value_change(self, rule, by_key, current) -> list[Event]:
        """Agrupa varios pontos em um unico evento por estacao."""
        points = [self.map.point(name) for name in rule.points]
        touched = [p.name for p in points if any(key[0] == p.name for key in by_key)]
        if not touched:
            return []

        if not any(point.per_station for point in points):
            context = self._group_context(rule, None, by_key, current)
            return [self._build(rule, None, context, f"Bancada: {rule.name}")]

        # Um ponto global do grupo (ex.: tensao da bancada) afeta todas as estacoes.
        global_touched = any(not self.map.point(name).per_station for name in touched)
        stations = sorted(
            set(self.map.station_ids)
            if global_touched
            else {key[1] for key in by_key if key[0] in touched and key[1] is not None}
        )

        events = []
        for station in stations:
            context = self._group_context(rule, station, by_key, current)
            valores = ", ".join(
                f"{name}={context.get(name)}" for name in rule.points if name in context
            )
            events.append(
                self._build(rule, station, context, f"Estacao {station}: {rule.name} ({valores})")
            )
        return events

    # -- auxiliares -----------------------------------------------------------
    def _changes_for(self, rule: EventRule, by_key) -> list[Change]:
        return [change for key, change in sorted(by_key.items(), key=_sort_key)
                if key[0] in rule.points]

    def _base_context(self, station: int | None) -> dict[str, Any]:
        return {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "station": station,
            "station_label": self.map.station_label(station) if station else None,
        }

    def _context(self, change: Change) -> dict[str, Any]:
        context = self._base_context(change.station)
        context.update(
            {
                "point": change.point.name,
                "value": change.current,
                "value_label": change.current_label,
                "previous": change.previous,
                "previous_label": change.previous_label,
                "delta": change.delta,
                "unit": change.point.unit,
            }
        )
        context[change.point.name] = change.current
        return context

    def _group_context(self, rule: EventRule, station, by_key, current) -> dict[str, Any]:
        context = self._base_context(station)
        for name in rule.points:
            point = self.map.point(name)
            key = (name, station if point.per_station else None)
            reading = current.get(key)
            if reading is not None:
                context[name] = reading.value
            change = by_key.get(key)
            if change is not None and "point" not in context:
                context["point"] = name
                context["value"] = change.current
                context["previous"] = change.previous
                context["delta"] = change.delta
        return context

    def _build(self, rule: EventRule, station, context, summary: str) -> Event:
        payload = render_payload(rule.payload, context) if rule.payload else dict(context)
        return Event(
            name=rule.name,
            endpoint=rule.endpoint,
            method=rule.method,
            payload=payload,
            station=station,
            summary=summary,
        )


def _sort_key(item) -> tuple:
    (name, station), _ = item
    return (station if station is not None else 0, name)
