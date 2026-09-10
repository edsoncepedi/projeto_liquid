"""O mapa e a peca que sera trocada quando o CLP real for conhecido."""

from __future__ import annotations

import textwrap

import pytest

from common import codec
from common.modbus_map import ModbusMapError, load_map


def escrever_mapa(tmp_path, corpo: str):
    caminho = tmp_path / "mapa.yaml"
    caminho.write_text(textwrap.dedent(corpo), encoding="utf-8")
    return caminho


def test_enderecos_por_estacao_seguem_o_stride(mapping):
    status = mapping.point("status")
    assert [status.base_address(s) for s in mapping.station_ids] == [100, 120, 140, 160]


def test_ponto_global_ignora_a_estacao(mapping):
    assert mapping.point("voltage").base_address() == 0


def test_ponto_vetorial_enderca_cada_item(mapping):
    positions = mapping.point("positions")
    assert positions.item_address(2, 0) == 16
    assert positions.item_address(2, 12) == 28
    assert positions.item_label(0) == "P"


def test_uint32_ocupa_dois_registradores(mapping):
    assert mapping.point("total").span == 2
    assert mapping.point("approved").base_address(1) == 104


def test_ponto_de_comando_nao_entra_nas_leituras(mapping):
    legiveis = {p.name for p, _ in mapping.instances(readable_only=True)}
    assert "cmd_reset" not in legiveis
    assert "status" in legiveis


def test_mapa_com_enderecos_sobrepostos_e_recusado(tmp_path):
    caminho = escrever_mapa(tmp_path, """
        version: 1
        stations: {ids: [1, 2]}
        memory_size: {holding_register: 64}
        points:
          - {name: a, scope: station, kind: holding_register, address: 10, stride: 2, data_type: uint32}
          - {name: b, scope: station, kind: holding_register, address: 11, stride: 2}
    """)
    with pytest.raises(ModbusMapError, match="conflito de endereco"):
        load_map(caminho)


def test_endereco_fora_do_tamanho_da_area_e_recusado(tmp_path):
    caminho = escrever_mapa(tmp_path, """
        version: 1
        stations: {ids: [1]}
        memory_size: {holding_register: 16}
        points:
          - {name: a, kind: holding_register, address: 20}
    """)
    with pytest.raises(ModbusMapError, match="fora do tamanho"):
        load_map(caminho)


def test_escrita_em_area_somente_leitura_e_recusada(tmp_path):
    caminho = escrever_mapa(tmp_path, """
        version: 1
        stations: {ids: [1]}
        points:
          - {name: a, kind: input_register, address: 0, access: rw}
    """)
    with pytest.raises(ModbusMapError, match="somente leitura"):
        load_map(caminho)


def test_tipos_e_escalas_alternativos_funcionam_sem_mudar_codigo(tmp_path):
    """int16 negativo, uint32 grande e escala em input_register."""
    caminho = escrever_mapa(tmp_path, """
        version: 1
        word_order: big
        stations: {ids: [1]}
        points:
          - {name: temperatura, kind: input_register, address: 0, data_type: int16, scale: 0.1, access: r}
          - {name: horimetro, kind: input_register, address: 1, data_type: uint32, access: r}
    """)
    mapa = load_map(caminho)

    temperatura = mapa.point("temperatura")
    assert codec.encode(temperatura, -12.5) == [0xFF83]
    assert codec.decode(temperatura, [0xFF83]) == -12.5

    horimetro = mapa.point("horimetro")
    palavras = codec.encode(horimetro, 100000)
    assert palavras == [1, 34464]
    assert codec.decode(horimetro, palavras) == 100000


def test_word_order_little_inverte_as_palavras(tmp_path):
    caminho = escrever_mapa(tmp_path, """
        version: 1
        word_order: little
        stations: {ids: [1]}
        points:
          - {name: contador, kind: holding_register, address: 0, data_type: uint32}
    """)
    mapa = load_map(caminho)
    ponto = mapa.point("contador")
    palavras = codec.encode(ponto, 100000, mapa.word_order)
    assert palavras == [34464, 1]
    assert codec.decode(ponto, palavras, mapa.word_order) == 100000
