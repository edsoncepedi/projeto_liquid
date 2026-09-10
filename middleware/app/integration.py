"""Contrato de integracao carregado de config/integration.yaml.

Quais eventos existem, com que regra sao detectados, para qual endpoint vao e
com que payload. Nada disso e codigo, para que o contrato real da aplicacao
possa ser ajustado sem tocar no middleware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

RULE_ENUM_CHANGE = "enum_change"
RULE_COUNTER_INCREASE = "counter_increase"
RULE_VALUE_CHANGE = "value_change"
RULES = (RULE_ENUM_CHANGE, RULE_COUNTER_INCREASE, RULE_VALUE_CHANGE)

MODE_PULSE = "pulse"
MODE_SET = "set"


class IntegrationConfigError(ValueError):
    """Configuracao de integracao invalida."""


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3
    backoff_seconds: float = 0.5


@dataclass(frozen=True)
class HttpConfig:
    timeout_seconds: float = 5.0
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EventRule:
    name: str
    rule: str
    points: tuple[str, ...]
    endpoint: str
    method: str = "POST"
    enabled: bool = True
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CommandDef:
    name: str
    point: str
    mode: str = MODE_SET
    value: Any = None
    idle_value: Any = 0
    pulse_ms: int = 300
    description: str = ""


@dataclass(frozen=True)
class IntegrationConfig:
    version: int
    http: HttpConfig
    events: dict[str, EventRule]
    commands: dict[str, CommandDef]
    initial_snapshot: bool = False
    source_path: Path | None = None

    def enabled_events(self) -> list[EventRule]:
        return [rule for rule in self.events.values() if rule.enabled]

    def command(self, name: str) -> CommandDef:
        try:
            return self.commands[name]
        except KeyError:
            raise IntegrationConfigError(f"comando desconhecido: {name}") from None


def load_integration(path: str | Path) -> IntegrationConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    http_raw = raw.get("http") or {}
    retry_raw = http_raw.get("retry") or {}
    http = HttpConfig(
        timeout_seconds=float(http_raw.get("timeout_seconds", 5.0)),
        retry=RetryPolicy(
            attempts=int(retry_raw.get("attempts", 3)),
            backoff_seconds=float(retry_raw.get("backoff_seconds", 0.5)),
        ),
        headers={str(k): str(v) for k, v in (http_raw.get("headers") or {}).items()},
    )

    events: dict[str, EventRule] = {}
    for name, entry in (raw.get("events") or {}).items():
        entry = entry or {}
        rule = entry.get("rule")
        if rule not in RULES:
            raise IntegrationConfigError(
                f"evento {name}: regra invalida {rule!r} (use uma de {list(RULES)})"
            )
        points = tuple(entry.get("points") or ())
        if not points:
            raise IntegrationConfigError(f"evento {name}: nenhum ponto declarado em 'points'")
        if not entry.get("endpoint"):
            raise IntegrationConfigError(f"evento {name}: 'endpoint' e obrigatorio")
        events[name] = EventRule(
            name=name,
            rule=rule,
            points=points,
            endpoint=str(entry["endpoint"]),
            method=str(entry.get("method", "POST")).upper(),
            enabled=bool(entry.get("enabled", True)),
            payload=entry.get("payload") or {},
        )

    commands: dict[str, CommandDef] = {}
    for name, entry in (raw.get("commands") or {}).items():
        entry = entry or {}
        if not entry.get("point"):
            raise IntegrationConfigError(f"comando {name}: 'point' e obrigatorio")
        mode = str(entry.get("mode", MODE_SET))
        if mode not in (MODE_PULSE, MODE_SET):
            raise IntegrationConfigError(f"comando {name}: modo invalido {mode}")
        commands[name] = CommandDef(
            name=name,
            point=str(entry["point"]),
            mode=mode,
            value=entry.get("value"),
            idle_value=entry.get("idle_value", 0),
            pulse_ms=int(entry.get("pulse_ms", 300)),
            description=str(entry.get("description", "")),
        )

    return IntegrationConfig(
        version=int(raw.get("version", 1)),
        http=http,
        events=events,
        commands=commands,
        initial_snapshot=bool(raw.get("initial_snapshot", False)),
        source_path=path,
    )
