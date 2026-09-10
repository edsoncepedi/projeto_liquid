"""State Manager: guarda o ciclo anterior e diz o que mudou.

E o que evita mandar os mesmos dados para a aplicacao a cada segundo:

    850 -> 850   nao envia
    850 -> 850   nao envia
    850 -> 900   mudou -> gera evento

Nao faz HTTP nem Modbus: recebe snapshots e devolve diferencas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from common.modbus_map import PointDef

from .mapper import Snapshot


@dataclass(frozen=True)
class Change:
    """Uma diferenca relevante entre o ciclo anterior e o atual."""

    point: PointDef
    station: int | None
    previous: Any
    current: Any
    previous_label: str | None = None
    current_label: str | None = None

    @property
    def key(self) -> tuple[str, int | None]:
        return (self.point.name, self.station)

    @property
    def delta(self) -> Any:
        """Diferenca numerica; None quando os valores nao sao numericos."""
        if isinstance(self.current, (int, float)) and isinstance(self.previous, (int, float)):
            if isinstance(self.current, bool) or isinstance(self.previous, bool):
                return None
            return round(self.current - self.previous, 6)
        return None

    def describe(self) -> str:
        alvo = f"Estacao {self.station}" if self.station else "Bancada"
        antes = self.previous_label or self.previous
        agora = self.current_label or self.current
        return f"{alvo}: {self.point.name} alterado {antes} -> {agora}"


def is_significant(point: PointDef, previous: Any, current: Any) -> bool:
    """Aplica o deadband do mapa: ruido de medicao nao vira evento."""
    if previous == current:
        return False
    if point.deadband and isinstance(previous, (int, float)) and isinstance(current, (int, float)):
        if not isinstance(previous, bool) and not isinstance(current, bool):
            return abs(current - previous) >= point.deadband
    return True


class StateManager:
    """Mantem o estado anterior e produz a lista de mudancas do ciclo."""

    def __init__(self):
        self._previous: Snapshot | None = None
        self.cycles = 0
        self.last_change_at: datetime | None = None

    @property
    def previous(self) -> Snapshot | None:
        return self._previous

    @property
    def has_baseline(self) -> bool:
        return self._previous is not None

    def diff(self, current: Snapshot) -> list[Change]:
        """Compara com o ciclo anterior. Sem linha de base, nao ha mudanca."""
        if self._previous is None:
            return []

        changes: list[Change] = []
        for key, reading in current.items():
            before = self._previous.get(key)
            if before is None:
                continue
            if not is_significant(reading.point, before.value, reading.value):
                continue
            changes.append(
                Change(
                    point=reading.point,
                    station=reading.station,
                    previous=before.value,
                    current=reading.value,
                    previous_label=before.label,
                    current_label=reading.label,
                )
            )
        return changes

    def commit(self, current: Snapshot, changes: list[Change] | None = None) -> None:
        """Adota a referencia para a proxima comparacao.

        Para os pontos que NAO mudaram de forma relevante, mantem o ultimo
        valor reportado em vez do valor lido agora. Sem isso, uma medicao que
        anda de 850 para 853 e depois 856 nunca ultrapassaria um deadband de
        5 W: a referencia acompanharia a deriva e o evento nunca sairia.
        """
        changes = changes or []
        if self._previous is None:
            self._previous = dict(current)
        else:
            changed_keys = {change.key for change in changes}
            self._previous = {
                key: reading
                if key in changed_keys or key not in self._previous
                else self._previous[key]
                for key, reading in current.items()
            }
        self.cycles += 1
        if changes:
            self.last_change_at = datetime.now()

    def reset(self) -> None:
        """Descarta a linha de base (usado apos perder a conexao com o CLP)."""
        self._previous = None
