"""Data Mapper e State Manager: leitura, decodificacao e comparacao."""

from __future__ import annotations

from middleware.app.mapper import build_read_plan, value_of
from middleware.app.state import StateManager, is_significant


async def ler(middleware) -> dict:
    raw = await middleware["reader"].read_plan(middleware["mapper"].read_plan)
    return middleware["mapper"].decode(raw)


def test_plano_de_leitura_agrupa_enderecos_contiguos(mapping):
    plano = build_read_plan(mapping)
    coils = [b for b in plano if b.kind == "coil"]
    assert len(coils) == 1                    # as 4 estacoes cabem em um bloco
    assert coils[0].address == 0 and coils[0].count == 61

    registradores = [b for b in plano if b.kind == "holding_register"]
    assert len(registradores) == 5            # tensao + 4 blocos de estacao
    assert all(b.count <= 125 for b in plano if b.kind.endswith("register"))


def test_plano_de_leitura_ignora_pontos_de_escrita(mapping):
    """cmd_reset (access: w) nao pode entrar no ciclo de leitura."""
    enderecos = {
        endereco
        for bloco in build_read_plan(mapping)
        if bloco.kind == "coil"
        for endereco in range(bloco.address, bloco.address + bloco.count)
    }
    assert 200 not in enderecos


async def test_decodificacao_respeita_tipo_escala_e_enum(middleware, plc):
    _, points, process = plc
    points.write("power", 850, 1)
    points.write("voltage", 121.0)
    process.apply_event(1, "inserir_produto")

    snapshot = await ler(middleware)

    assert value_of(snapshot, "power", 1) == 850
    assert value_of(snapshot, "voltage") == 121.0
    assert snapshot[("status", 1)].label == "PRODUTO_INSERIDO"
    assert len(value_of(snapshot, "positions", 1)) == 13


async def test_sem_mudanca_nao_ha_diferenca(middleware):
    state: StateManager = middleware["state"]
    primeiro = await ler(middleware)
    state.commit(primeiro, state.diff(primeiro))

    segundo = await ler(middleware)
    assert state.diff(segundo) == []


async def test_mudanca_de_valor_e_detectada_uma_unica_vez(middleware, plc):
    _, points, _ = plc
    state: StateManager = middleware["state"]
    state.commit(await ler(middleware))

    points.write("power", 900, 1)
    mudancas = state.diff(await ler(middleware))
    assert [(c.point.name, c.previous, c.current) for c in mudancas] == [("power", 0, 900)]

    state.commit(await ler(middleware), mudancas)
    assert state.diff(await ler(middleware)) == []      # nao repete no ciclo seguinte


def test_deadband_ignora_ruido_mas_nao_a_mudanca_real(mapping):
    power = mapping.point("power")           # deadband 5 W
    assert is_significant(power, 850, 853) is False
    assert is_significant(power, 850, 856) is True

    status = mapping.point("status")         # sem deadband: qualquer mudanca vale
    assert is_significant(status, 0, 1) is True


async def test_deriva_dentro_do_deadband_acaba_gerando_evento(middleware, plc):
    """850 -> 853 -> 856: a referencia nao pode acompanhar a deriva."""
    _, points, _ = plc
    state: StateManager = middleware["state"]
    points.write("power", 850, 1)
    state.commit(await ler(middleware))

    points.write("power", 853, 1)
    mudancas = state.diff(await ler(middleware))
    assert mudancas == []
    state.commit(await ler(middleware), mudancas)

    points.write("power", 856, 1)
    mudancas = state.diff(await ler(middleware))
    assert [(c.previous, c.current) for c in mudancas] == [(850, 856)]


async def test_reset_apos_queda_evita_eventos_falsos(middleware, plc):
    _, points, _ = plc
    state: StateManager = middleware["state"]
    state.commit(await ler(middleware))

    state.reset()                            # o middleware ficou cego
    points.write("power", 900, 1)
    assert state.diff(await ler(middleware)) == []
    assert state.has_baseline is False
