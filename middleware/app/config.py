"""Configuracao do middleware.

Trocar o CLP virtual pelo CLP real e so trocar MODBUS_HOST / MODBUS_PORT /
MODBUS_UNIT_ID. Nada no codigo distingue um do outro.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MiddlewareSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )

    # --- CLP (virtual em desenvolvimento, real em producao) -----------------
    modbus_host: str = Field("127.0.0.1", validation_alias="MODBUS_HOST")
    modbus_port: int = Field(5020, validation_alias="MODBUS_PORT")
    modbus_unit_id: int = Field(1, validation_alias="MODBUS_UNIT_ID")
    modbus_timeout: float = Field(3.0, validation_alias="MODBUS_TIMEOUT")

    # --- ciclo de leitura ----------------------------------------------------
    # 1 segundo e decisao de implementacao, nao requisito do protocolo Modbus.
    poll_interval: float = Field(1.0, validation_alias="POLL_INTERVAL")
    reconnect_delay: float = Field(3.0, validation_alias="RECONNECT_DELAY")

    # --- aplicacao de destino ------------------------------------------------
    application_base_url: str = Field("http://localhost:8000", validation_alias="APPLICATION_BASE_URL")

    # --- API de entrada (aplicacao -> middleware -> CLP) ---------------------
    api_host: str = Field("0.0.0.0", validation_alias="MIDDLEWARE_API_HOST")
    api_port: int = Field(8090, validation_alias="MIDDLEWARE_API_PORT")

    # --- configuracao declarativa -------------------------------------------
    modbus_map_path: Path = Field(Path("config/modbus_map.yaml"), validation_alias="MODBUS_MAP_PATH")
    integration_config_path: Path = Field(
        Path("config/integration.yaml"), validation_alias="INTEGRATION_CONFIG_PATH"
    )

    log_level: str = Field("INFO", validation_alias="LOG_LEVEL")


def get_settings() -> MiddlewareSettings:
    return MiddlewareSettings()
