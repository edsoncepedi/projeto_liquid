"""Validacao das etapas 1 e 2: interface Web -> memoria -> Modbus TCP.

Uso (com o simulador em execucao):
    python scripts/validar_simulador.py
"""
import asyncio, json, urllib.request
from pymodbus.client import AsyncModbusTcpClient

BASE = "http://127.0.0.1:8080"

def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    return json.load(urllib.request.urlopen(req))

def get(path):
    return json.load(urllib.request.urlopen(BASE + path))

async def main():
    print("1) escrevendo pela API Web (como faria o operador na IHM)")
    print("  ", post("/api/points/power", {"value": 850, "station": 1}))
    print("  ", post("/api/stations/1/event", {"event": "inserir_produto"}))
    print("  ", post("/api/stations/1/event", {"event": "iniciar_teste"}))
    print("  ", post("/api/stations/1/event", {"event": "aprovar"}))
    print("  ", post("/api/points/positions", {"value": True, "station": 2, "index": 3}))

    print("2) lendo pelo Modbus TCP (como fara o middleware)")
    client = AsyncModbusTcpClient("127.0.0.1", port=5020)
    await client.connect()
    hr = await client.read_holding_registers(0, count=1, slave=1)
    print("   tensao   HR0      =", hr.registers, "-> V:", hr.registers[0] * 0.1)
    hr = await client.read_holding_registers(100, count=8, slave=1)
    print("   estacao1 HR100-107=", hr.registers)
    co = await client.read_coils(16, count=13, slave=1)
    print("   estacao2 coils 16+ =", [int(b) for b in co.bits[:13]])

    print("3) escrevendo pelo Modbus (como fara o middleware no comando reset)")
    await client.write_coil(200, True, slave=1)
    await asyncio.sleep(0.2)
    hr = await client.read_holding_registers(100, count=8, slave=1)
    print("   estacao1 apos reset=", hr.registers)
    co = await client.read_coils(200, count=1, slave=1)
    print("   coil 200 devolvida pelo CLP =", int(co.bits[0]))
    client.close()

    print("4) estado visto pela interface Web")
    st = get("/api/state")["stations"]["1"]
    print("   ", {k: v for k, v in st.items() if k != "allowed_events"})

asyncio.run(main())
