"""Simulador: memoria, ciclo das estacoes e reacao a comandos Modbus."""

from __future__ import annotations

import pytest

from common.modbus_map import KIND_COIL, KIND_HOLDING
from simulator.app.process import TransitionError


def test_memoria_so_notifica_o_que_realmente_mudou(plc):
    memory, _, _ = plc
    vistos = []
    memory.subscribe(vistos.append)

    memory.write(KIND_HOLDING, 300, [7])
    memory.write(KIND_HOLDING, 300, [7])       # mesmo valor: nao e mudanca

    assert len(vistos) == 1
    assert vistos[0][0].previous == 0 and vistos[0][0].current == 7


def test_memoria_recusa_acesso_fora_da_faixa(plc):
    memory, _, _ = plc
    with pytest.raises(IndexError):
        memory.read(KIND_HOLDING, memory.size(KIND_HOLDING) - 1, 4)


def test_ciclo_completo_aprovando_uma_peca(plc):
    _, points, process = plc

    process.apply_event(1, "inserir_produto")
    assert process.status_label(1) == "PRODUTO_INSERIDO"
    process.apply_event(1, "iniciar_teste")
    assert process.status_label(1) == "TESTANDO"
    process.apply_event(1, "aprovar")

    assert process.status_label(1) == "APROVADO"
    assert points.read("total", 1) == 1
    assert points.read("approved", 1) == 1
    assert points.read("rejected", 1) == 0


def test_reprovacao_conta_no_contador_certo(plc):
    _, points, process = plc
    process.apply_event(2, "inserir_produto")
    process.apply_event(2, "iniciar_teste")
    process.apply_event(2, "reprovar")

    assert points.read("total", 2) == 1
    assert points.read("rejected", 2) == 1
    assert points.read("approved", 2) == 0


def test_transicao_fora_de_ordem_e_recusada(plc):
    _, _, process = plc
    with pytest.raises(TransitionError, match="exige estado em"):
        process.apply_event(1, "aprovar")      # estacao esta em VAZIO


def test_retirar_produto_limpa_medicao_e_posicoes(plc):
    _, points, process = plc
    points.write("power", 900, 1)
    points.write("positions", 3, 1, index=0)
    process.apply_event(1, "inserir_produto")
    process.apply_event(1, "iniciar_teste")
    process.apply_event(1, "reprovar")
    process.apply_event(1, "retirar_produto")

    assert points.read("power", 1) == 0
    assert points.read("positions", 1) == [False] * 13
    assert points.read("total", 1) == 1        # o contador nao e apagado


def test_estacoes_sao_independentes(plc):
    _, points, process = plc
    for evento in ("inserir_produto", "iniciar_teste", "aprovar"):
        process.apply_event(3, evento)

    assert points.read("total", 3) == 1
    assert points.read("total", 1) == 0
    assert points.read("total", 4) == 0


def test_coil_de_reset_escrita_via_modbus_zera_contadores(plc, mapping):
    """O programa do CLP responde ao comando como o CLP real responderia."""
    memory, points, process = plc
    for evento in ("inserir_produto", "iniciar_teste", "aprovar"):
        process.apply_event(1, evento)
    assert points.read("total", 1) == 1

    coil = mapping.point("cmd_reset").base_address(1)
    memory.write(KIND_COIL, coil, [1], source="modbus")

    assert points.read("total", 1) == 0
    assert points.read("approved", 1) == 0
    # o CLP devolve a coil para 0 sozinho, como um pulso
    assert memory.read(KIND_COIL, coil, 1) == [0]


def test_reset_de_uma_estacao_nao_afeta_as_outras(plc, mapping):
    memory, points, process = plc
    for estacao in (1, 2):
        for evento in ("inserir_produto", "iniciar_teste", "aprovar"):
            process.apply_event(estacao, evento)

    memory.write(KIND_COIL, mapping.point("cmd_reset").base_address(1), [1], source="modbus")

    assert points.read("total", 1) == 0
    assert points.read("total", 2) == 1


def test_escala_do_mapa_e_aplicada_na_memoria(plc, mapping):
    memory, points, _ = plc
    points.write("voltage", 127.5)
    assert memory.read(KIND_HOLDING, 0, 1) == [1275]      # escala 0.1
    assert points.read("voltage") == 127.5
