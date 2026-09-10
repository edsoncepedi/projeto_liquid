"""A configuracao documentada tem de bater com a que o codigo le.

Estes testes existem porque .env.example e docker-compose.yml ja ficaram para
tras de uma renomeacao de variavel - o erro e silencioso: a variavel errada e
simplesmente ignorada e o servico sobe com o valor padrao.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from middleware.app.config import MiddlewareSettings
from simulator.app.config import SimulatorSettings

RAIZ = Path(__file__).resolve().parents[1]


def aliases(classe) -> set[str]:
    """Nomes de variavel de ambiente que a classe de settings realmente le."""
    nomes = set()
    for campo in classe.model_fields.values():
        alias = campo.validation_alias
        if alias:
            nomes.add(str(alias))
    return nomes


def variaveis_do_env_example() -> set[str]:
    texto = (RAIZ / ".env.example").read_text(encoding="utf-8")
    return {
        linha.split("=", 1)[0].strip()
        for linha in texto.splitlines()
        if "=" in linha and not linha.strip().startswith("#")
    }


def ambiente_dos_servicos() -> dict[str, dict[str, str]]:
    compose = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
    return {
        nome: {k: str(v) for k, v in (servico.get("environment") or {}).items()}
        for nome, servico in compose["services"].items()
    }


def test_env_example_so_cita_variaveis_que_existem():
    conhecidas = aliases(SimulatorSettings) | aliases(MiddlewareSettings)
    desconhecidas = variaveis_do_env_example() - conhecidas
    assert not desconhecidas, (
        f".env.example define variaveis que nenhum servico le: {sorted(desconhecidas)}"
    )


def test_env_example_cobre_todas_as_variaveis():
    faltando = (aliases(SimulatorSettings) | aliases(MiddlewareSettings)) - variaveis_do_env_example()
    assert not faltando, f"variaveis nao documentadas em .env.example: {sorted(faltando)}"


def test_compose_so_define_variaveis_que_existem():
    servicos = ambiente_dos_servicos()
    validas = {
        "simulador": aliases(SimulatorSettings),
        "middleware": aliases(MiddlewareSettings),
    }
    for nome, conhecidas in validas.items():
        desconhecidas = set(servicos[nome]) - conhecidas
        assert not desconhecidas, (
            f"docker-compose.yml define no servico {nome} variaveis que ele nao le: "
            f"{sorted(desconhecidas)}"
        )


def test_middleware_no_compose_aponta_para_o_simulador():
    """No Docker, 127.0.0.1 seria o proprio container do middleware."""
    ambiente = ambiente_dos_servicos()["middleware"]
    assert ambiente["MODBUS_HOST"] == "simulador"
    assert ambiente["MODBUS_PORT"] == "5020"
    assert "localhost" not in ambiente["APPLICATION_BASE_URL"]


def test_simulador_no_compose_escuta_em_todas_as_interfaces():
    """0.0.0.0 e obrigatorio: em 127.0.0.1 o container nao aceitaria conexao externa."""
    ambiente = ambiente_dos_servicos()["simulador"]
    assert ambiente["SIMULATOR_MODBUS_HOST"] == "0.0.0.0"
    assert ambiente["WEB_HOST"] == "0.0.0.0"


def test_portas_publicadas_batem_com_as_configuradas():
    compose = yaml.safe_load((RAIZ / "docker-compose.yml").read_text(encoding="utf-8"))
    servicos = compose["services"]
    publicadas = {
        nome: {p.split(":")[1].split("/")[0] for p in (s.get("ports") or [])}
        for nome, s in servicos.items()
    }
    ambiente = ambiente_dos_servicos()
    assert ambiente["simulador"]["WEB_PORT"] in publicadas["simulador"]
    assert ambiente["simulador"]["SIMULATOR_MODBUS_PORT"] in publicadas["simulador"]
    assert ambiente["middleware"]["MIDDLEWARE_API_PORT"] in publicadas["middleware"]
