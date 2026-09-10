"""Event Detector: os cenarios descritos na especificacao (secao 17)."""

from __future__ import annotations

import pytest

from middleware.app.events import render_payload


@pytest.fixture
def cenario(poller, middleware, plc):
    """Poller com a linha de base ja registrada e o publisher limpo."""

    async def _ciclo():
        return await poller.run_cycle()

    return poller, middleware["publisher"], plc, _ciclo


async def test_sem_mudanca_nenhum_http(cenario):
    _, publisher, _, ciclo = cenario
    await ciclo()                      # linha de base
    await ciclo()
    await ciclo()
    assert publisher.events == []


async def test_primeiro_ciclo_nao_envia_estado_inicial(cenario):
    _, publisher, _, ciclo = cenario
    assert await ciclo() == []
    assert publisher.sent == 0


async def test_mudanca_de_estado_gera_status_changed(cenario):
    _, publisher, plc, ciclo = cenario
    _, _, process = plc
    await ciclo()

    process.apply_event(1, "inserir_produto")
    process.apply_event(1, "iniciar_teste")
    await ciclo()

    evento = next(e for e in publisher.events if e.name == "status_changed")
    assert evento.endpoint == "/status"
    assert evento.payload["from"] == "VAZIO"
    assert evento.payload["to"] == "TESTANDO"
    assert evento.payload["station"] == 1


async def test_aprovacao_gera_evento_approved_com_o_incremento(cenario):
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    points.write("approved", 10, 1)
    points.write("total", 10, 1)
    await ciclo()

    points.write("approved", 11, 1)
    points.write("total", 11, 1)
    await ciclo()

    evento = next(e for e in publisher.events if e.name == "approved")
    assert evento.endpoint == "/approved"
    assert evento.payload == {
        "event": "approved",
        "station": 1,
        "count": 1,
        "total_approved": 11,
        "timestamp": evento.payload["timestamp"],
    }


async def test_reprovacao_gera_evento_rejected(cenario):
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    points.write("rejected", 3, 2)
    await ciclo()

    points.write("rejected", 4, 2)
    await ciclo()

    evento = next(e for e in publisher.events if e.name == "rejected")
    assert evento.station == 2
    assert evento.payload["count"] == 1
    assert evento.payload["total_rejected"] == 4


async def test_mudanca_de_medicao_gera_measurement_changed(cenario):
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    points.write("power", 850, 1)
    await ciclo()

    points.write("power", 900, 1)
    await ciclo()

    evento = next(e for e in publisher.events if e.name == "measurement_changed")
    assert evento.payload["power"] == 900
    assert evento.payload["voltage"] == 121.0


async def test_medicao_dentro_do_deadband_nao_gera_evento(cenario):
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    points.write("power", 850, 1)
    await ciclo()
    publisher.clear()

    points.write("power", 853, 1)
    await ciclo()
    assert publisher.events == []


async def test_zerar_contador_nao_vira_aprovacao(cenario):
    """Reset leva approved de 5 para 0: e counter_changed, nunca approved."""
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    points.write("approved", 5, 1)
    points.write("total", 5, 1)
    await ciclo()
    publisher.clear()

    points.write("approved", 0, 1)
    points.write("total", 0, 1)
    await ciclo()

    assert "approved" not in publisher.names()
    assert "counter_changed" in publisher.names()


async def test_mudanca_global_afeta_todas_as_estacoes(cenario, mapping):
    _, publisher, plc, ciclo = cenario
    _, points, _ = plc
    await ciclo()

    points.write("voltage", 127.0)
    await ciclo()

    medicoes = [e for e in publisher.events if e.name == "measurement_changed"]
    assert sorted(e.station for e in medicoes) == list(mapping.station_ids)
    assert all(e.payload["voltage"] == 127.0 for e in medicoes)


async def test_estacoes_nao_afetadas_nao_geram_evento(cenario):
    _, publisher, plc, ciclo = cenario
    _, _, process = plc
    await ciclo()

    process.apply_event(2, "inserir_produto")
    await ciclo()

    estacoes = {e.station for e in publisher.events if e.name == "status_changed"}
    assert estacoes == {2}


def test_payload_preserva_tipos_e_texto():
    contexto = {"station": 2, "value": 900, "value_label": "TESTANDO", "delta": 1}
    template = {
        "station": "{station}",
        "power": "{value}",
        "texto": "estacao {station} em {value_label}",
        "fixo": "sem placeholder",
        "aninhado": {"delta": "{delta}"},
        "lista": ["{station}", 7],
    }
    assert render_payload(template, contexto) == {
        "station": 2,
        "power": 900,
        "texto": "estacao 2 em TESTANDO",
        "fixo": "sem placeholder",
        "aninhado": {"delta": 1},
        "lista": [2, 7],
    }


def test_payload_com_placeholder_desconhecido_nao_quebra():
    assert render_payload({"a": "{inexistente}"}, {"x": 1}) == {"a": None}
