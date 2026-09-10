"""Conversao entre valores de negocio e palavras Modbus.

Concentra tipo de dado, escala e ordem de palavras em um unico lugar, para que
mudar o mapa (uint16 -> uint32, escala 1.0 -> 0.1) nao exija mudar logica.
"""

from __future__ import annotations

from .modbus_map import PointDef

WORD_MASK = 0xFFFF


def _to_words(value: int, words: int, word_order: str) -> list[int]:
    parts = [(value >> (16 * i)) & WORD_MASK for i in range(words)]
    parts.reverse()                       # parts[0] = palavra mais significativa
    if word_order == "little":
        parts.reverse()
    return parts


def _from_words(words: list[int], word_order: str) -> int:
    parts = list(words)
    if word_order == "little":
        parts.reverse()
    value = 0
    for part in parts:                    # parts[0] = palavra mais significativa
        value = (value << 16) | (int(part) & WORD_MASK)
    return value


def _signed(value: int, bits: int) -> int:
    limit = 1 << (bits - 1)
    return value - (1 << bits) if value >= limit else value


def decode(point: PointDef, words: list[int] | list[bool], word_order: str = "big"):
    """Converte as palavras cruas de UM item do ponto no valor de negocio."""
    if point.is_bit:
        return bool(words[0])

    raw = _from_words(list(words), word_order)
    if point.data_type == "int16":
        raw = _signed(raw, 16)
    elif point.data_type == "int32":
        raw = _signed(raw, 32)

    if point.scale == 1.0:
        return raw
    return round(raw * point.scale, max(point.decimals, 6))


def encode(point: PointDef, value, word_order: str = "big") -> list[int]:
    """Converte um valor de negocio nas palavras cruas de UM item do ponto."""
    if point.is_bit:
        return [1 if _truthy(value) else 0]

    raw = round(float(value) / point.scale) if point.scale != 1.0 else int(round(float(value)))
    raw = int(raw)

    words = 1 if point.data_type in ("uint16", "int16") else 2
    bits = 16 * words
    if point.data_type.startswith("int"):
        low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    else:
        low, high = 0, (1 << bits) - 1
    if not low <= raw <= high:
        raise ValueError(
            f"valor {value} fora da faixa de {point.data_type} no ponto {point.name}"
        )

    return _to_words(raw & ((1 << bits) - 1), words, word_order)


def _truthy(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "on", "yes", "sim")
    return bool(value)


def clamp(point: PointDef, value):
    """Aplica os limites min/max declarados no mapa, quando existirem."""
    if point.is_bit:
        return _truthy(value)
    value = float(value)
    if point.minimum is not None:
        value = max(value, float(point.minimum))
    if point.maximum is not None:
        value = min(value, float(point.maximum))
    return value


def format_value(point: PointDef, value) -> str:
    """Texto de exibicao do valor, com unidade e casas decimais do mapa."""
    if point.is_bit:
        return "1" if value else "0"
    text = f"{float(value):.{point.decimals}f}"
    return f"{text} {point.unit}" if point.unit else text
