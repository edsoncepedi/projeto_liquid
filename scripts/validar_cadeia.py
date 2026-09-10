"""Validacao das etapas 3 a 6: simulador -> Modbus -> middleware -> HTTP -> aplicacao.

Uso (com os tres servicos em execucao):
    python scripts/validar_cadeia.py

Enderecos: por padrao a maquina local nas portas padrao. Para outra maquina ou
portas trocadas (as mesmas variaveis usadas pelo docker-compose.yml):

    HOST=192.168.0.50 python3 scripts/validar_cadeia.py
    HOST_PORT_APLICACAO=8001 python3 scripts/validar_cadeia.py
"""
import json, os, time, urllib.request

HOST = os.environ.get("HOST", "127.0.0.1")
SIM = f"http://{HOST}:{os.environ.get('HOST_PORT_WEB', '8080')}"
MID = f"http://{HOST}:{os.environ.get('HOST_PORT_MIDDLEWARE', '8090')}"
APP = f"http://{HOST}:{os.environ.get('HOST_PORT_APLICACAO', '8000')}"

print("simulador: ", SIM)
print("middleware:", MID)
print("aplicacao: ", APP)

def call(base, path, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method=method or ("POST" if data else "GET"))
    return json.load(urllib.request.urlopen(req))

def passo(titulo):
    print("\n=== " + titulo + " ===")

passo("0) preparando: deixando a estacao 1 em VAZIO")
estado = call(SIM, "/api/state")["stations"]["1"]["status_label"]
if estado in ("APROVADO", "REPROVADO"):
    call(SIM, "/api/stations/1/event", {"event": "retirar_produto"})
elif estado != "VAZIO":
    call(SIM, "/api/stations/1/event", {"event": "retirar_produto", "force": True})
call(SIM, "/api/stations/1/reset", method="POST")
time.sleep(1.5)
print("   estado:", call(SIM, "/api/state")["stations"]["1"]["status_label"])

passo("A) tres segundos sem mudanca nenhuma")
antes = call(APP, "/events")["total"]
time.sleep(3)
print("   eventos recebidos pela aplicacao:", call(APP, "/events")["total"] - antes, "(esperado 0)")

passo("B) estacao 1: VAZIO -> PRODUTO_INSERIDO -> TESTANDO")
call(SIM, "/api/stations/1/event", {"event": "inserir_produto"})
time.sleep(1.3)
call(SIM, "/api/stations/1/event", {"event": "iniciar_teste"})
time.sleep(1.3)

passo("C) potencia 0 -> 850 W")
call(SIM, "/api/points/power", {"value": 850, "station": 1})
time.sleep(1.3)

passo("D) potencia 850 -> 853 W (dentro do deadband de 5 W)")
call(SIM, "/api/points/power", {"value": 853, "station": 1})
time.sleep(1.3)

passo("E) aprovar peca na estacao 1")
call(SIM, "/api/stations/1/event", {"event": "aprovar"})
time.sleep(1.5)

passo("F) comando reset vindo da aplicacao (HTTP -> Modbus -> CLP)")
print("   ", call(MID, "/commands", {"command": "reset", "station": 1}))
time.sleep(1.5)
print("   contadores no simulador:", {k: v["value"] for k, v in
      call(SIM, "/api/state")["stations"]["1"].items() if k in ("total", "approved", "rejected")})

passo("G) eventos recebidos pela aplicacao")
for item in call(APP, "/events")["events"]:
    print(f"   {item['at']}  {item['path']:<14} {json.dumps(item['payload'], ensure_ascii=False)}")

passo("H) status do middleware")
s = call(MID, "/status")
print("   ", {k: s[k] for k in ("cycles", "events_detected", "events_sent", "events_failed", "connected")})
