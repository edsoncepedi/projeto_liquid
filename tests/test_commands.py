"""Caminho inverso e resiliencia: aplicacao -> middleware -> CLP."""

from __future__ import annotations

import pytest

from common.modbus_map import KIND_COIL
from middleware.app.commands import CommandError
from middleware.app.modbus_client import ModbusError


async def test_comando_reset_zera_os_contadores_do_clp(middleware, plc):
    _, points, process = plc
    for evento in ("inserir_produto", "iniciar_teste", "aprovar"):
        process.apply_event(1, evento)
    assert points.read("total", 1) == 1

    resultado = await middleware["commands"].execute("reset", station=1)

    assert resultado["point"] == "cmd_reset"
    assert resultado["mode"] == "pulse"
    assert points.read("total", 1) == 0
    assert points.read("approved", 1) == 0


async def test_pulso_liga_e_desliga_a_coil(middleware, plc, mapping):
    memory, _, _ = plc
    await middleware["commands"].execute("reset", station=2)

    escritas = [w for w in middleware["reader"].writes if w[0] == "cmd_reset"]
    assert [valor for _, _, valor in escritas] == [1, 0]
    assert memory.read(KIND_COIL, mapping.point("cmd_reset").base_address(2), 1) == [0]


async def test_comando_set_escreve_valor_com_escala(middleware, plc):
    _, points, _ = plc
    await middleware["commands"].execute("set_voltage", value=127.0)
    assert points.read("voltage") == 127.0


async def test_comando_set_aceita_rotulo_de_enum(middleware, plc):
    _, _, process = plc
    await middleware["commands"].execute("set_status", station=3, value="TESTANDO")
    assert process.status_label(3) == "TESTANDO"


async def test_comando_por_estacao_exige_estacao(middleware):
    with pytest.raises(CommandError, match="exige a estacao"):
        await middleware["commands"].execute("reset")


async def test_estacao_inexistente_e_recusada(middleware):
    with pytest.raises(CommandError, match="nao existe no mapa"):
        await middleware["commands"].execute("reset", station=99)


async def test_comando_desconhecido_e_recusado(middleware):
    with pytest.raises(CommandError, match="comando desconhecido"):
        await middleware["commands"].execute("desligar_tudo", station=1)


async def test_comando_sem_conexao_falha_de_forma_clara(middleware):
    middleware["reader"].connected = False
    with pytest.raises(CommandError, match="sem conexao"):
        await middleware["commands"].execute("reset", station=1)


def test_lista_de_comandos_descreve_o_que_a_aplicacao_precisa_enviar(middleware):
    disponiveis = {c["command"]: c for c in middleware["commands"].available()}
    assert disponiveis["reset"]["requires_station"] is True
    assert disponiveis["reset"]["requires_value"] is False
    assert disponiveis["set_voltage"]["requires_station"] is False
    assert disponiveis["set_voltage"]["requires_value"] is True


async def test_falha_de_leitura_descarta_a_linha_de_base(poller, middleware, plc):
    """Depois de ficar cego, o middleware nao pode inventar eventos."""
    _, points, _ = plc
    await poller.run_cycle()
    assert middleware["state"].has_baseline is True

    middleware["reader"].fail_next = True
    with pytest.raises(ModbusError):
        await poller.run_cycle()

    await poller._handle_failure("falha simulada")
    assert middleware["state"].has_baseline is False

    points.write("power", 900, 1)
    await poller.run_cycle()                 # apenas registra a nova base
    assert middleware["publisher"].events == []

    points.write("power", 950, 1)
    await poller.run_cycle()
    assert "measurement_changed" in middleware["publisher"].names()
