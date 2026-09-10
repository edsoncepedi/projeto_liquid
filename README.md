# Simulador de CLP + Middleware de Integracao

Estrutura para desenvolver e testar a integracao do teste de liquidificadores
**sem depender do CLP fisico nem da bancada real**.

```text
┌──────────────────────────────┐
│  1. SIMULADOR DE CLP         │   interface Web + memoria + servidor Modbus
│     :8080  Web               │
│     :5020  Modbus TCP        │
└──────────────┬───────────────┘
               │ Modbus TCP
               ▼
┌──────────────────────────────┐
│  2. MIDDLEWARE               │   polling, estado, eventos, HTTP
│     :8090  API de comandos   │
└──────────────┬───────────────┘
               │ HTTP
               ▼
┌──────────────────────────────┐
│  3. APLICACAO                │   backend real (fora deste repositorio);
│     :8000  dublê de teste    │   incluido aqui apenas um dublê
└──────────────────────────────┘
```

O middleware enxerga o simulador exatamente como enxergaria o CLP real: a
interface Web **nunca** fala com ele, apenas escreve na memoria do CLP virtual.

---

## ⚠ O mapa Modbus ainda e virtual

O mapa real do teste de liquidificadores **ainda nao foi fornecido**. Os
enderecos em [`config/modbus_map.yaml`](config/modbus_map.yaml) foram escolhidos
apenas para permitir o desenvolvimento e **nao devem ser tratados como reais**.
As imagens da IHM mostram a interface de operacao, nao os enderecos.

Trocar o mapa e uma edicao de YAML: endereco, tipo de dado, escala, unidade,
estacao e descricao. Nenhuma logica do simulador ou do middleware muda.
Ver [Quando o mapa real chegar](#quando-o-mapa-real-chegar).

O mesmo vale para os endpoints HTTP em
[`config/integration.yaml`](config/integration.yaml): sao configuracao, nao
contrato confirmado com a aplicacao.

---

## Como executar

### Com Docker (recomendado)

```bash
docker compose up
```

| Servico | URL | O que e |
|---|---|---|
| Simulador | http://localhost:8080 | interface parecida com a IHM |
| Middleware | http://localhost:8090/status | situacao do polling e dos eventos |
| Aplicacao (dublê) | http://localhost:8000 | lista os eventos recebidos |

Para usar a aplicacao **real**, suba so os dois primeiros e aponte a URL:

```bash
APPLICATION_BASE_URL=http://host.docker.internal:8000 docker compose up simulador middleware
```

### Sem Docker - Ubuntu / Linux

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip     # normalmente falta em servidor novo

git clone <URL_DO_REPOSITORIO> projeto_liquid
cd projeto_liquid

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python run_simulator.py           # terminal 1  -> :8080 (Web) e :5020 (Modbus)
python run_middleware.py          # terminal 2  -> :8090
python run_mock_app.py            # terminal 3  -> :8000 (opcional)
```

Requer Python 3.10 ou superior (`python3 --version`). Ubuntu 22.04 traz 3.10 e
Ubuntu 24.04 traz 3.12 - ambos servem.

Para acessar a interface de outra maquina da rede, libere as portas:

```bash
sudo ufw allow 8080/tcp    # interface Web do simulador
sudo ufw allow 5020/tcp    # Modbus TCP (so se o middleware rodar em outra maquina)
sudo ufw allow 8090/tcp    # API de comandos do middleware
```

### Sem Docker - Windows

```powershell
python -m venv .venv
.venv\Scriptsctivate
pip install -r requirements.txt

python run_simulator.py
python run_middleware.py
python run_mock_app.py
```

---

## A interface do simulador

Tres abas, em http://localhost:8080:

- **OPERACAO** - uma estacao por painel: medidor de potencia, estado, tensao da
  bancada, sinalizadores `P` e `V1..V12` (clicaveis) e os botoes de evento
  (`INSERIR PRODUTO`, `INICIAR TESTE`, `APROVAR`, `REPROVAR`, `RETIRAR`).
  Os botoes so ficam ativos nas transicoes validas do ciclo.
- **HISTORICO** - `TOTAL`, `APROVADO`, `REPROVADO`, `INDICE REP.` e
  `RESET 01..04` por estacao.
- **MEMORIA MODBUS** - o dump da memoria do CLP virtual, com o nome do ponto
  que ocupa cada endereco. E aqui que se acompanha
  `interface Web -> memoria virtual -> Modbus TCP`.

A tela inteira e montada a partir de `/api/map`: **nenhum endereco Modbus ou
nome de estacao esta escrito na interface**. Mudar o YAML muda a tela.

---

## Como validar o comportamento

### Roteiro manual (o que a especificacao pede como resultado)

Com os tres servicos no ar, abra o simulador e o log do middleware lado a lado.

| Passo | O que fazer no simulador | O que deve aparecer no log do middleware |
|---|---|---|
| 1 | nao mexer em nada por 10 s | **nada** - sem mudanca nao ha HTTP |
| 2 | `INSERIR PRODUTO` na estacao 01 | `status alterado VAZIO -> PRODUTO_INSERIDO` + `Evento enviado: status_changed` |
| 3 | arrastar a potencia para 850 W | `power alterado 0 -> 850` + `measurement_changed` |
| 4 | mudar a potencia para 853 W | **nada** - dentro do deadband de 5 W do mapa |
| 5 | `INICIAR TESTE` e `APROVAR` | `status_changed`, `approved`, `counter_changed` |
| 6 | aba HISTORICO, `RESET 01` | `counter_changed` com os contadores zerados, **sem** `approved` |
| 7 | parar o simulador (`Ctrl+C`) | `Falha de conexao Modbus ... nova tentativa em 3.0s` |
| 8 | subir o simulador de novo | `Conectado ao Modbus ...` e o ciclo continua |

O passo 6 tambem funciona no sentido inverso, partindo da aplicacao:

```bash
curl -X POST http://localhost:8090/commands \
     -H "Content-Type: application/json" \
     -d '{"station": 1, "command": "reset"}'
```

`aplicacao -> HTTP -> middleware -> Modbus -> CLP virtual -> contador zerado`.

### Scripts de validacao

```bash
python scripts/validar_simulador.py   # etapas 1 e 2: Web -> memoria -> Modbus TCP
python scripts/validar_cadeia.py      # etapas 3 a 6: cadeia completa ate a aplicacao
```

O segundo percorre o roteiro acima sozinho e imprime os eventos que chegaram na
aplicacao, inclusive mostrando que nada e enviado quando nada muda.

### Testes automatizados

```bash
python -m pytest
```

54 testes, cobrindo os cenarios da especificacao:

| Arquivo | O que cobre |
|---|---|
| `tests/test_modbus_map.py` | enderecamento por estacao, `uint32`, escala, `int16`, ordem de palavras, mapas invalidos (enderecos sobrepostos, fora da area, escrita em area de leitura) |
| `tests/test_simulator.py` | ciclo das estacoes, contadores, independencia entre estacoes, reset chegando pela coil |
| `tests/test_state_and_mapper.py` | plano de leitura, decodificacao, sem-mudanca, deadband e deriva dentro do deadband |
| `tests/test_events.py` | os cinco cenarios da secao 17, payloads e o caso "zerar contador nao e aprovacao" |
| `tests/test_commands.py` | comandos da aplicacao, pulso, validacoes e perda de conexao |
| `tests/test_end_to_end.py` | **Modbus TCP real** entre simulador e middleware, incluindo reconexao |

Os testes rapidos ligam o middleware direto na memoria do CLP virtual por um
leitor falso com a mesma interface do real; so o ultimo arquivo abre socket.

---

## Como o middleware funciona

```text
ModbusReader  ->  DataMapper  ->  StateManager  ->  EventDetector  ->  EventPublisher
 (pymodbus)      (mapa/escala)   (estado anterior)   (regras YAML)        (HTTP)
```

Cada camada e um modulo com uma responsabilidade e pode ser testada sozinha.

**A cada `POLL_INTERVAL` (1 s por padrao):** le os blocos do plano de leitura,
decodifica, compara com o ciclo anterior, e **so entao** gera e envia eventos.

Detalhes que valem conhecer:

- **Nao envia o estado completo a cada ciclo.** `850 -> 850 -> 850 -> 900` gera
  um unico evento, no ultimo ciclo.
- **Deadband por ponto** (`deadband:` no mapa): ruido de medicao nao vira
  evento. A referencia guardada e o *ultimo valor reportado*, nao o ultimo
  lido - sem isso, uma deriva de 850 → 853 → 856 nunca ultrapassaria o
  deadband e o evento jamais sairia.
- **Contador que zera nao e aprovacao.** `counter_increase` so dispara quando o
  contador sobe; um reset aparece como `counter_changed`.
- **Primeiro ciclo nao envia nada** (so registra a linha de base). Para receber
  o estado completo ao conectar, use `initial_snapshot: true`.
- **Ao perder o CLP, a linha de base e descartada.** Enquanto esteve cego, o CLP
  pode ter mudado varias vezes; comparar com um estado velho geraria eventos
  falsos. Apos reconectar, o primeiro ciclo so recompoe a referencia.
- **Log silencioso em regime.** Nada e registrado nos ciclos sem mudanca.
- **Plano de leitura** enderecos contiguos viram uma unica requisicao Modbus
  (o mapa atual gera 6 requisicoes por ciclo). Consulte em
  `GET /config` → `map.read_requests_per_cycle`.

### Regras de evento disponiveis

Configuradas em `config/integration.yaml`, campo `rule`:

| Regra | Dispara quando | Usada por |
|---|---|---|
| `enum_change` | um ponto com enum muda de valor | `status_changed` |
| `counter_increase` | um contador **aumenta** (ignora quedas) | `approved`, `rejected` |
| `value_change` | qualquer ponto do grupo muda alem do deadband | `measurement_changed`, `counter_changed` |

Um ponto **global** dentro de um grupo por estacao (a tensao da bancada, por
exemplo) gera um evento para cada estacao, porque afeta todas elas.

---

## Endpoints

### Simulador (`:8080`)

| Metodo | Rota | Para que serve |
|---|---|---|
| GET | `/api/map` | mapa resolvido (a interface se monta a partir daqui) |
| GET | `/api/state` | estado de todos os pontos e transicoes permitidas |
| POST | `/api/points/{nome}` | escreve um ponto: `{"value": 850, "station": 1}` |
| POST | `/api/stations/{n}/event` | evento de processo: `{"event": "aprovar"}` |
| POST | `/api/stations/{n}/reset` | zera os contadores da estacao |
| GET | `/api/memory` | dump da memoria Modbus, com o dono de cada endereco |
| POST | `/api/memory` | escrita crua, para reproduzir um estado especifico |

### Middleware (`:8090`)

| Metodo | Rota | Para que serve |
|---|---|---|
| GET | `/status` | ciclos, ultimo erro, eventos detectados/enviados/falhados |
| GET | `/state` | ultimo estado lido do CLP |
| GET | `/config` | mapa, endpoints e eventos ativos no ambiente |
| GET | `/commands` | comandos disponiveis e o que cada um exige |
| POST | `/commands` | `{"station": 1, "command": "reset"}` |

---

## Configuracao

Tudo por variavel de ambiente (ver [`.env.example`](.env.example)).

### Simulador

| Variavel | Padrao | O que e |
|---|---|---|
| `SIMULATOR_MODBUS_HOST` / `SIMULATOR_MODBUS_PORT` | `0.0.0.0` / `5020` | onde o servidor Modbus escuta |
| `WEB_HOST` / `WEB_PORT` | `0.0.0.0` / `8080` | interface Web |
| `SIMULATOR_TITLE` | `TESTE LIQUIDIFICADOR` | titulo no topo da tela |
| `INITIAL_VOLTAGE` | `121.0` | tensao inicial da bancada |

### Middleware

| Variavel | Padrao | O que e |
|---|---|---|
| `MODBUS_HOST` | `127.0.0.1` | **CLP alvo** (virtual ou real) |
| `MODBUS_PORT` | `5020` | `502` no CLP real |
| `MODBUS_UNIT_ID` | `1` | unit id do CLP |
| `POLL_INTERVAL` | `1.0` | segundos entre ciclos |
| `RECONNECT_DELAY` | `3.0` | espera antes de tentar reconectar |
| `APPLICATION_BASE_URL` | `http://localhost:8000` | aplicacao de destino |
| `MIDDLEWARE_API_PORT` | `8090` | API de comandos |

### Comuns

| Variavel | Padrao |
|---|---|
| `MODBUS_MAP_PATH` | `config/modbus_map.yaml` |
| `INTEGRATION_CONFIG_PATH` | `config/integration.yaml` |
| `LOG_LEVEL` | `INFO` |

O intervalo de 1 segundo e **decisao desta implementacao**, nao exigencia do
protocolo Modbus.

---

## Quando o mapa real chegar

1. Edite `config/modbus_map.yaml`: para cada ponto, ajuste `address`, `stride`,
   `kind`, `data_type`, `scale`, `unit`, `deadband` e `description`.
   Ajuste tambem `stations.ids` se o numero de estacoes for outro.
2. Rode `python -m pytest tests/test_modbus_map.py`. O carregamento recusa
   enderecos sobrepostos, enderecos fora da area e escrita em area de leitura.
3. Suba o simulador: a interface se remonta sozinha a partir do mapa novo.
4. Se algum nome de ponto mudar, ajuste as listas `points:` de
   `config/integration.yaml` - o middleware avisa na inicializacao se um evento
   citar um ponto inexistente.

Tipos suportados: `bool` (coil / discrete input), `uint16`, `int16`, `uint32`,
`int32`, com `scale` e `word_order` (`big`/`little`) configuraveis.

## Quando o CLP real entrar

```bash
MODBUS_HOST=<IP_DO_CLP_REAL>
MODBUS_PORT=502
MODBUS_UNIT_ID=<UNIT_ID>
```

Nada mais muda: o middleware nao distingue o CLP virtual do real.
Comece com os pontos de leitura, confirme os valores em `GET /state` e so
depois habilite os comandos de escrita.

O mesmo vale se simulador e middleware ficarem em **maquinas diferentes**:
aponte `MODBUS_HOST` para o IP da maquina do simulador (que ja escuta em
`0.0.0.0`) e `APPLICATION_BASE_URL` para o IP da aplicacao.

---

## Estrutura

```text
config/
  modbus_map.yaml        # ⚠ mapa VIRTUAL - a peca a ser trocada
  integration.yaml       # eventos, endpoints, payloads e comandos
common/
  modbus_map.py          # modelo do mapa (compartilhado)
  codec.py               # tipo de dado, escala e ordem de palavras
simulator/app/
  memory.py              # memoria do CLP virtual (fonte unica de verdade)
  points.py              # acesso por nome de ponto, nao por endereco
  process.py             # "programa do CLP": ciclo das estacoes e reset
  datastore.py           # ponte pymodbus -> memoria (sem copia de estado)
  modbus_server.py       # servidor Modbus TCP
  api.py / main.py       # API e aplicacao Web
  static/                # interface (montada a partir de /api/map)
middleware/app/
  modbus_client.py       # infraestrutura: unica camada que conhece pymodbus
  mapper.py              # plano de leitura + decodificacao
  state.py               # estado anterior e comparacao
  events.py              # regras de evento e payloads
  http_client.py         # entrega com retentativa
  commands.py            # aplicacao -> Modbus
  poller.py              # o ciclo
  api.py / main.py       # API de entrada e montagem das camadas
mock_app/                # dublê da aplicacao (apenas para teste)
scripts/                 # validacao manual das etapas
tests/                   # 54 testes
```
