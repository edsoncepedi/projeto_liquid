"""Configuracao do simulador (tudo por variavel de ambiente).

Os nomes de variavel do simulador levam o prefixo SIMULATOR_ nos pontos em que
poderiam colidir com as do middleware, para que os dois possam compartilhar o
mesmo arquivo .env em desenvolvimento. MODBUS_MAP_PATH e LOG_LEVEL sao
propositalmente comuns aos dois.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SimulatorSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # Servidor Modbus TCP exposto ao middleware (endereco de escuta)
    modbus_bind_host: str = Field("0.0.0.0", validation_alias="SIMULATOR_MODBUS_HOST")
    modbus_bind_port: int = Field(5020, validation_alias="SIMULATOR_MODBUS_PORT")

    # Interface Web
    web_host: str = Field("0.0.0.0", validation_alias="WEB_HOST")
    web_port: int = Field(8080, validation_alias="WEB_PORT")

    # Mapa Modbus: o MESMO arquivo lido pelo middleware
    modbus_map_path: Path = Field(Path("config/modbus_map.yaml"), validation_alias="MODBUS_MAP_PATH")

    title: str = Field("TESTE LIQUIDIFICADOR", validation_alias="SIMULATOR_TITLE")
    initial_voltage: float = Field(121.0, validation_alias="INITIAL_VOLTAGE")
    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")


def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
