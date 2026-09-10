"""Aplicacao de EXEMPLO para testes - nao e a aplicacao real.

Aceita qualquer POST, registra no log e guarda os ultimos eventos, para que a
cadeia completa possa ser observada antes de a aplicacao real existir:

    Simulador -> Modbus -> Middleware -> HTTP -> (aqui)

Os endpoints atendidos sao os que estiverem em config/integration.yaml; este
dublê nao define contrato nenhum.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from common.logging_setup import configure_logging

configure_logging("INFO")
log = logging.getLogger("aplicacao-exemplo")

app = FastAPI(title="Aplicacao de exemplo (dublê de teste)", version="1.0.0")
recebidos: deque[dict[str, Any]] = deque(maxlen=200)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "recebidos": len(recebidos)}


@app.get("/events")
def listar() -> dict:
    return {"total": len(recebidos), "events": list(recebidos)}


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    linhas = "".join(
        f"<tr><td>{item['at']}</td><td>{item['path']}</td>"
        f"<td><code>{item['payload']}</code></td></tr>"
        for item in reversed(recebidos)
    )
    return f"""<!doctype html><meta charset="utf-8">
<title>Aplicacao de exemplo</title>
<meta http-equiv="refresh" content="2">
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f4f6fa}}
 h1{{font-size:18px}} table{{border-collapse:collapse;width:100%;background:#fff}}
 td,th{{border:1px solid #d7dbe5;padding:6px 10px;font-size:13px;text-align:left}}
 th{{background:#2f4f8f;color:#fff}} code{{font-size:12px}}
</style>
<h1>Aplicacao de exemplo - {len(recebidos)} evento(s) recebido(s)</h1>
<table><tr><th>Hora</th><th>Endpoint</th><th>Payload</th></tr>{linhas}</table>"""


@app.post("/{path:path}")
async def receber(path: str, request: Request) -> dict:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - corpo vazio ou nao-JSON
        payload = (await request.body()).decode(errors="replace")
    registro = {
        "at": datetime.now().strftime("%H:%M:%S"),
        "path": "/" + path,
        "payload": payload,
    }
    recebidos.append(registro)
    log.info("Recebido em /%s: %s", path, payload)
    return {"ok": True}
