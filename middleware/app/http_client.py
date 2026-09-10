"""HTTP Client: entrega os eventos na aplicacao.

Nao decide o que enviar nem para onde - endpoint e payload ja vem prontos do
Event Detector, que os montou a partir de config/integration.yaml.
"""

from __future__ import annotations

import asyncio
import logging

import httpx

from .events import Event
from .integration import HttpConfig

log = logging.getLogger("middleware.http")


class EventPublisher:
    def __init__(self, base_url: str, config: HttpConfig):
        self.base_url = base_url.rstrip("/")
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self.sent = 0
        self.failed = 0

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.config.timeout_seconds,
            headers=self.config.headers,
        )
        log.info("Cliente HTTP apontando para %s", self.base_url)

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def publish(self, event: Event) -> bool:
        """Envia um evento, com as tentativas configuradas. True se entregou."""
        if self._client is None:
            await self.start()

        attempts = max(1, self.config.retry.attempts)
        for attempt in range(1, attempts + 1):
            try:
                response = await self._client.request(
                    event.method, event.endpoint, json=event.payload
                )
                response.raise_for_status()
                self.sent += 1
                log.info("Evento enviado: %s -> %s", event.name, event.endpoint)
                return True
            except httpx.HTTPStatusError as exc:
                detail = f"HTTP {exc.response.status_code}"
            except httpx.HTTPError as exc:
                detail = f"{type(exc).__name__}: {exc}"

            if attempt < attempts:
                espera = self.config.retry.backoff_seconds * attempt
                log.warning(
                    "Falha ao enviar evento HTTP %s (%s). Tentativa %d/%d, "
                    "nova tentativa em %.1fs",
                    event.name, detail, attempt, attempts, espera,
                )
                await asyncio.sleep(espera)
            else:
                self.failed += 1
                log.error(
                    "Falha ao enviar evento HTTP %s para %s apos %d tentativas (%s)",
                    event.name, event.endpoint, attempts, detail,
                )
        return False
