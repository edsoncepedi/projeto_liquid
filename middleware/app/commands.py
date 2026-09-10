"""Caminho inverso: aplicacao -> middleware -> CLP.

    Aplicacao --HTTP--> Middleware --Modbus--> CLP (virtual ou real)

Os comandos disponiveis e o que cada um escreve estao em
config/integration.yaml; aqui so existe COMO escrever (pulso ou valor fixo).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from common.modbus_map import ModbusMap

from .integration import MODE_PULSE, IntegrationConfig, IntegrationConfigError
from .modbus_client import ModbusReader

log = logging.getLogger("middleware.comandos")


class CommandError(RuntimeError):
    """Comando invalido ou impossivel de executar."""


class CommandHandler:
    def __init__(self, mapping: ModbusMap, integration: IntegrationConfig, reader: ModbusReader):
        self.map = mapping
        self.integration = integration
        self.reader = reader
        self.executed = 0

    def available(self) -> list[dict[str, Any]]:
        """Lista os comandos configurados (a aplicacao pode consultar)."""
        return [
            {
                "command": command.name,
                "point": command.point,
                "mode": command.mode,
                "requires_station": self.map.point(command.point).per_station,
                "requires_value": command.mode != MODE_PULSE,
                "description": command.description,
            }
            for command in self.integration.commands.values()
        ]

    async def execute(
        self, command_name: str, station: int | None = None, value: Any = None
    ) -> dict[str, Any]:
        try:
            command = self.integration.command(command_name)
        except IntegrationConfigError as exc:
            raise CommandError(str(exc)) from exc

        point = self.map.point(command.point)

        if point.per_station:
            if station is None:
                raise CommandError(f"comando {command_name} exige a estacao")
            if station not in self.map.station_ids:
                raise CommandError(f"estacao {station} nao existe no mapa")
        else:
            station = None

        if not self.reader.connected and not await self.reader.connect():
            raise CommandError("sem conexao com o CLP")

        if command.mode == MODE_PULSE:
            await self._pulse(command, point, station)
            escrito = command.value
        else:
            escrito = self._resolve_value(command, point, value)
            await self.reader.write_point(point, escrito, station)

        self.executed += 1
        log.info(
            "Comando %s executado%s (ponto %s = %s)",
            command_name,
            f" na estacao {station}" if station else "",
            point.name,
            escrito,
        )
        return {
            "command": command_name,
            "station": station,
            "point": point.name,
            "value": escrito,
            "mode": command.mode,
        }

    async def _pulse(self, command, point, station) -> None:
        """Liga, espera e desliga - como um botao momentaneo na IHM."""
        await self.reader.write_point(point, command.value, station)
        await asyncio.sleep(command.pulse_ms / 1000)
        await self.reader.write_point(point, command.idle_value, station)

    def _resolve_value(self, command, point, value) -> Any:
        if value is None:
            if command.value is None:
                raise CommandError(f"comando {command.name} exige o campo 'value'")
            value = command.value
        if point.enum and isinstance(value, str):
            try:
                return self.map.enum_value(point.enum, value)
            except Exception as exc:  # noqa: BLE001 - vira erro de comando
                raise CommandError(str(exc)) from exc
        return value
