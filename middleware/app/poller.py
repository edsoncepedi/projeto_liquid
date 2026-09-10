"""Orquestracao do ciclo de leitura.

    A cada POLL_INTERVAL:
        ler CLP -> interpretar -> comparar com o estado anterior
        -> se mudou, gerar evento -> HTTP POST

O intervalo de 1 segundo e decisao desta implementacao, nao exigencia do
protocolo Modbus, e vem de POLL_INTERVAL.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from common.modbus_map import ModbusMap

from .events import Event, EventDetector
from .http_client import EventPublisher
from .integration import IntegrationConfig
from .mapper import DataMapper, Snapshot
from .modbus_client import ModbusError, ModbusReader
from .state import Change, StateManager

log = logging.getLogger("middleware.polling")


class Poller:
    def __init__(
        self,
        mapping: ModbusMap,
        integration: IntegrationConfig,
        mapper: DataMapper,
        reader: ModbusReader,
        state: StateManager,
        detector: EventDetector,
        publisher: EventPublisher,
        poll_interval: float = 1.0,
        reconnect_delay: float = 3.0,
    ):
        self.map = mapping
        self.integration = integration
        self.mapper = mapper
        self.reader = reader
        self.state = state
        self.detector = detector
        self.publisher = publisher
        self.poll_interval = poll_interval
        self.reconnect_delay = reconnect_delay

        self.running = False
        self.last_cycle_at: datetime | None = None
        self.last_error: str | None = None
        self.events_detected = 0
        self.last_events: list[str] = []
        self._task: asyncio.Task | None = None

    # -- ciclo ----------------------------------------------------------------
    async def run_cycle(self) -> list[Event]:
        """Um ciclo completo. Levanta ModbusError se a leitura falhar."""
        raw = await self.reader.read_plan(self.mapper.read_plan)
        snapshot: Snapshot = self.mapper.decode(raw)

        primeiro = not self.state.has_baseline
        if primeiro and self.integration.initial_snapshot:
            changes = self._baseline_changes(snapshot)
        else:
            changes = self.state.diff(snapshot)

        self.state.commit(snapshot, changes)
        self.last_cycle_at = datetime.now()

        if primeiro and not self.integration.initial_snapshot:
            log.info(
                "Estado inicial registrado (%d pontos). Eventos so a partir da "
                "primeira mudanca.",
                len(snapshot),
            )
            return []

        if not changes:
            return []          # nada mudou: nada de log, nada de HTTP

        for change in changes:
            log.info(change.describe())

        events = self.detector.detect(changes, snapshot)
        self.events_detected += len(events)
        self.last_events = [event.describe() for event in events][-10:]
        for event in events:
            await self.publisher.publish(event)
        return events

    def _baseline_changes(self, snapshot: Snapshot) -> list[Change]:
        """Trata o primeiro ciclo como 'tudo mudou' (initial_snapshot: true)."""
        return [
            Change(
                point=reading.point,
                station=reading.station,
                previous=None,
                current=reading.value,
                previous_label=None,
                current_label=reading.label,
            )
            for reading in snapshot.values()
        ]

    # -- laco -----------------------------------------------------------------
    async def run(self) -> None:
        self.running = True
        log.info("Polling iniciado: %.1fs", self.poll_interval)
        while self.running:
            inicio = asyncio.get_running_loop().time()
            try:
                if not await self.reader.connect():
                    self.last_error = "sem conexao com o CLP"
                    self.state.reset()
                    await asyncio.sleep(self.reconnect_delay)
                    continue
                await self.run_cycle()
                self.last_error = None
            except ModbusError as exc:
                await self._handle_failure(str(exc))
                continue
            except asyncio.CancelledError:
                raise
            except (OSError, ConnectionError) as exc:
                await self._handle_failure(f"{type(exc).__name__}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 - o laco nao pode morrer
                log.exception("Erro inesperado no ciclo de polling: %s", exc)
                self.last_error = str(exc)

            decorrido = asyncio.get_running_loop().time() - inicio
            await asyncio.sleep(max(0.0, self.poll_interval - decorrido))

    async def _handle_failure(self, detail: str) -> None:
        """Perdeu o CLP: descarta a linha de base e tenta reconectar.

        A linha de base e descartada de proposito: enquanto o middleware
        esteve cego, o CLP pode ter mudado varias vezes, e comparar com um
        estado velho geraria eventos falsos.
        """
        self.last_error = detail
        self.reader.notify_disconnected()
        self.state.reset()
        log.error("Falha de conexao Modbus: %s. Nova tentativa em %.1fs", detail, self.reconnect_delay)
        await asyncio.sleep(self.reconnect_delay)

    # -- controle -------------------------------------------------------------
    def start(self) -> asyncio.Task:
        self._task = asyncio.create_task(self.run(), name="middleware-polling")
        return self._task

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("Polling encerrado")

    def stats(self) -> dict:
        return {
            "running": self.running,
            "connected": self.reader.connected,
            "poll_interval": self.poll_interval,
            "cycles": self.state.cycles,
            "last_cycle_at": self.last_cycle_at.isoformat() if self.last_cycle_at else None,
            "last_change_at": (
                self.state.last_change_at.isoformat() if self.state.last_change_at else None
            ),
            "events_detected": self.events_detected,
            "events_sent": self.publisher.sent,
            "events_failed": self.publisher.failed,
            "last_events": self.last_events,
            "last_error": self.last_error,
        }
