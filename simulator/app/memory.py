"""Memoria do CLP virtual.

Esta e a unica fonte de verdade do simulador. A interface Web escreve aqui e o
servidor Modbus le/escreve aqui - ninguem conversa diretamente com ninguem.

    Interface Web -> PlcMemory -> Servidor Modbus TCP -> Middleware

Tudo roda no mesmo event loop do uvicorn (o servidor Modbus e uma task), mas o
lock e mantido porque os callbacks do pymodbus sao sincronos e nada garante,
no futuro, que continuarao na mesma thread.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from common.modbus_map import ALL_KINDS, BIT_KINDS

WORD_MASK = 0xFFFF


@dataclass(frozen=True)
class Change:
    """Uma alteracao efetiva (valor realmente diferente) na memoria."""

    kind: str
    address: int
    previous: int
    current: int
    source: str


Listener = Callable[[list[Change]], None]


class PlcMemory:
    """As quatro areas de memoria Modbus, com notificacao de mudanca."""

    def __init__(self, sizes: dict[str, int]):
        self._blocks: dict[str, list[int]] = {
            kind: [0] * int(sizes.get(kind, 0)) for kind in ALL_KINDS
        }
        self._lock = threading.RLock()
        self._listeners: list[Listener] = []
        self._revision = 0

    # -- consulta -------------------------------------------------------------
    @property
    def revision(self) -> int:
        """Contador incrementado a cada mudanca (usado pela UI para detectar
        que algo mudou sem comparar o estado inteiro)."""
        return self._revision

    def size(self, kind: str) -> int:
        return len(self._blocks[kind])

    def validate(self, kind: str, address: int, count: int = 1) -> bool:
        return address >= 0 and count > 0 and address + count <= self.size(kind)

    def read(self, kind: str, address: int, count: int = 1) -> list[int]:
        with self._lock:
            if not self.validate(kind, address, count):
                raise IndexError(
                    f"leitura fora da faixa: {kind} {address}+{count} "
                    f"(tamanho {self.size(kind)})"
                )
            return list(self._blocks[kind][address : address + count])

    def dump(self, kind: str) -> list[int]:
        with self._lock:
            return list(self._blocks[kind])

    # -- escrita --------------------------------------------------------------
    def write(
        self, kind: str, address: int, values, source: str = "simulador"
    ) -> list[Change]:
        """Escreve valores e notifica os ouvintes apenas do que mudou."""
        values = list(values)
        with self._lock:
            if not self.validate(kind, address, len(values)):
                raise IndexError(
                    f"escrita fora da faixa: {kind} {address}+{len(values)} "
                    f"(tamanho {self.size(kind)})"
                )
            block = self._blocks[kind]
            changes: list[Change] = []
            for offset, value in enumerate(values):
                value = self._normalize(kind, value)
                index = address + offset
                previous = block[index]
                if previous == value:
                    continue
                block[index] = value
                changes.append(Change(kind, index, previous, value, source))
            if changes:
                self._revision += 1

        # notifica fora do lock: um ouvinte pode escrever de volta (o programa
        # do CLP reagindo a um comando), e isso nao pode travar.
        for change_list in ([changes] if changes else []):
            for listener in list(self._listeners):
                listener(change_list)
        return changes

    @staticmethod
    def _normalize(kind: str, value) -> int:
        if kind in BIT_KINDS:
            return 1 if value else 0
        return int(value) & WORD_MASK

    # -- observadores ---------------------------------------------------------
    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def reset(self) -> None:
        with self._lock:
            for kind, block in self._blocks.items():
                self._blocks[kind] = [0] * len(block)
            self._revision += 1
