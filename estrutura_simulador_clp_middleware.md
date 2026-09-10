# Projeto: Simulador de CLP + Middleware de Integração + Aplicação

## Objetivo

Desenvolver uma estrutura de software para desenvolvimento e testes de uma aplicação industrial que recebe eventos via HTTP a partir de dados originalmente fornecidos por um CLP.

A solução deve permitir desenvolver e testar o middleware sem depender inicialmente de um CLP físico ou da bancada real.

A arquitetura será composta por três aplicações independentes:

```text
┌──────────────────────────────┐
│  1. SIMULADOR DE CLP         │
│                              │
│  Interface Web + Modbus TCP  │
└──────────────┬───────────────┘
               │
               │ Modbus TCP
               ▼
┌──────────────────────────────┐
│  2. MIDDLEWARE               │
│                              │
│  Modbus → Estado → HTTP      │
└──────────────┬───────────────┘
               │
               │ HTTP
               ▼
┌──────────────────────────────┐
│  3. APLICAÇÃO                │
│                              │
│  Backend real                │
└──────────────────────────────┘
```

O objetivo inicial é implementar principalmente os componentes 1 e 2 e permitir que o middleware seja testado contra o simulador de CLP e contra a aplicação real.

---

# 1. Contexto do projeto

Existe um projeto anterior desenvolvido pela equipe utilizando Node-RED como ponte entre um CLP e uma aplicação.

Nesse projeto anterior, o Node-RED:

- realiza leituras periódicas do CLP via Modbus TCP;
- possui um ciclo de aproximadamente 1 segundo para consultar o CLP;
- interpreta Coils e Holding Registers;
- mantém o estado anterior dos dados;
- compara a leitura atual com a anterior;
- evita enviar continuamente os mesmos dados para a aplicação;
- gera eventos quando identifica mudanças relevantes;
- envia esses eventos para a aplicação por HTTP POST;
- também pode receber comandos HTTP da aplicação e convertê-los em escritas Modbus no CLP.

O novo projeto deverá aplicar o mesmo conceito a outro processo industrial: testes de liquidificadores.

O CLP real utilizado no novo processo é da mesma família do CLP utilizado no projeto anterior, mas o mapa Modbus do novo processo ainda precisa ser confirmado.

Não assumir que os endereços Modbus do projeto anterior são válidos para o novo projeto.

---

# 2. Processo que será simulado

As imagens fornecidas como material adicional mostram uma IHM real utilizada no teste de liquidificadores.

As imagens devem ser utilizadas como referência visual e funcional para o simulador.

## Tela principal observada

A primeira IHM apresenta:

- título relacionado ao teste de liquidificador;
- relógio;
- Estação 01;
- Estação 02;
- medição de potência em W;
- tensão em V;
- estado da estação, atualmente apresentado como "VAZIO";
- indicação "P";
- posições V1 até V12.

A imagem mostra duas estações nessa tela.

## Tela histórica observada

A segunda IHM apresenta:

- Estação 01;
- Estação 02;
- Estação 03;
- Estação 04;
- TOTAL;
- APROVADO;
- REPROVADO;
- ÍNDICE REP.;
- botões RESET 01;
- RESET 02;
- RESET 03;
- RESET 04;
- navegação para início e próxima tela.

Essa tela deve ser usada como referência para os dados e controles disponíveis no processo.

Importante: as imagens mostram a interface de operação, mas não fornecem os endereços Modbus. Portanto, os endereços e tipos exatos das variáveis devem ser definidos em uma camada de configuração do simulador, e não deduzidos arbitrariamente das imagens.

---

# 3. Arquitetura geral

## Componente 1: Simulador de CLP

Aplicação responsável por simular a planta/CLP.

Deve possuir:

1. Interface Web semelhante à IHM real;
2. Estado interno representando a memória do CLP;
3. Servidor Modbus TCP;
4. Mecanismo para alterar os valores do CLP através da interface Web;
5. Visualização dos estados atuais;
6. Possibilidade de simular eventos do processo.

A aplicação Web não deve conversar diretamente com o middleware.

O fluxo deve ser:

```text
Usuário
   ↓
Interface Web do simulador
   ↓
Estado interno do CLP virtual
   ↓
Servidor Modbus TCP
   ↓
Middleware
```

Isso é importante porque o middleware deve enxergar o simulador exatamente como enxergaria um CLP real.

---

# 4. Simulador de CLP: modelo de dados

Criar uma camada clara para representar a memória Modbus.

Separar, conceitualmente:

```text
Coils
Holding Registers
Input Registers
Discrete Inputs
```

Entretanto, somente utilizar os tipos realmente necessários quando o mapa Modbus for definido.

O mapa deve ser configurável.

Exemplo conceitual:

```text
COILS

0  → estação 1 ocupada
1  → estação 1 aprovada
2  → estação 1 reprovada
3  → reset estação 1

...

HOLDING REGISTERS

0  → potência estação 1
1  → tensão estação 1
2  → contador aprovado estação 1
3  → contador reprovado estação 1

...
```

Esses endereços são apenas exemplos.

Não utilizar esses endereços como se fossem os endereços reais.

Criar uma estrutura de configuração para que o mapa possa ser alterado facilmente quando o mapa real do CLP for obtido.

---

# 5. Interface Web do simulador

A interface deve se inspirar nas duas imagens fornecidas.

Não é necessário copiar exatamente o design da IHM. O objetivo é criar uma interface de teste funcional e visualmente semelhante.

## Tela de operação

Para cada estação, permitir visualizar e alterar:

- estado;
- potência;
- tensão;
- entradas V1 até V12;
- indicação P;
- demais variáveis relevantes definidas no mapa.

Organizar as estações em painéis.

Exemplo:

```text
┌─────────────────────────────────────────────┐
│           TESTE LIQUIDIFICADOR              │
├─────────────────────┬───────────────────────┤
│     ESTAÇÃO 01      │      ESTAÇÃO 02       │
│                     │                       │
│ Potência: 0 W       │ Potência: 0 W         │
│ Tensão: 121 V       │ Tensão: 121 V         │
│ Estado: VAZIO       │ Estado: VAZIO         │
│                     │                       │
│ P V1 ... V12        │ P V1 ... V12           │
└─────────────────────┴───────────────────────┘
```

Os valores devem poder ser alterados manualmente para simular a planta.

---

# 6. Tela histórica

Criar uma tela semelhante à segunda IHM.

Para cada estação:

```text
TOTAL
APROVADO
REPROVADO
ÍNDICE REP.
```

Adicionar:

```text
RESET 01
RESET 02
RESET 03
RESET 04
```

Os botões de reset devem alterar a memória do CLP virtual da mesma forma que um comando equivalente faria no CLP real.

---

# 7. Simulação de eventos

A interface deve permitir provocar eventos manualmente.

Exemplos:

## Produto inserido

```text
VAZIO
↓
PRODUTO INSERIDO
```

## Início do teste

```text
PRODUTO INSERIDO
↓
TESTANDO
```

## Aprovação

```text
TESTANDO
↓
APROVADO
```

e incrementar:

```text
TOTAL
APROVADO
```

## Reprovação

```text
TESTANDO
↓
REPROVADO
```

e incrementar:

```text
TOTAL
REPROVADO
```

## Alteração de medição

Permitir modificar valores como:

```text
potência
tensão
```

para verificar como o middleware reage às mudanças.

A lógica de processo pode inicialmente ser manual. Não é necessário implementar uma simulação física real do liquidificador.

---

# 8. Visualização da memória Modbus

Adicionar uma área de diagnóstico no simulador.

Ela deve permitir visualizar o estado atual da memória Modbus:

```text
Coils

0000 = 0
0001 = 1
0002 = 0
...

Holding Registers

0000 = 121
0001 = 850
0002 = 10
...
```

Isso será importante para depuração.

O desenvolvedor deve conseguir acompanhar:

```text
Interface Web
      ↓
Memória virtual
      ↓
Modbus TCP
```

---

# 9. Componente 2: Middleware

Criar uma aplicação independente responsável pela integração entre Modbus e HTTP.

Responsabilidades:

1. conectar ao servidor Modbus;
2. realizar polling periódico;
3. ler os dados definidos no mapa;
4. interpretar os valores;
5. manter o estado anterior;
6. comparar estado atual e anterior;
7. identificar mudanças relevantes;
8. gerar eventos;
9. enviar eventos para a aplicação via HTTP;
10. receber comandos HTTP da aplicação;
11. quando necessário, escrever comandos no CLP via Modbus.

Arquitetura:

```text
          Modbus TCP
              ↑
              |
      ┌───────┴────────┐
      │   Middleware   │
      │                │
      │ Polling        │
      │ Parser         │
      │ State Manager  │
      │ Event Detector │
      │ HTTP Client    │
      └───────┬────────┘
              |
             HTTP
              |
              ↓
          Aplicação
```

---

# 10. Polling de 1 segundo

O middleware deve possuir polling configurável.

Valor inicial:

```text
1 segundo
```

A lógica deve ser:

```text
A cada 1 segundo

    ↓

Ler CLP

    ↓

Interpretar dados

    ↓

Comparar com estado anterior

    ↓

Atualizar estado interno

    ↓

Se houve mudança relevante
        ↓
    gerar evento
        ↓
    HTTP POST
```

Importante:

O intervalo de 1 segundo é uma decisão da implementação e deve ser configurável.

Não tratar 1 segundo como requisito do protocolo Modbus.

---

# 11. Detecção de mudanças

O middleware não deve enviar o estado completo para a aplicação a cada polling.

Exemplo:

```text
t=0
Potência = 850 W

t=1 s
Potência = 850 W

t=2 s
Potência = 850 W

t=3 s
Potência = 900 W
```

O middleware deve realizar:

```text
850 → 850
não enviar

850 → 850
não enviar

850 → 900
houve mudança
enviar evento
```

Isso deve ser implementado através de um gerenciador de estado anterior.

---

# 12. Eventos

Criar uma camada explícita de eventos.

Exemplos iniciais:

```text
status_changed
approved
rejected
measurement_changed
counter_changed
```

O conjunto final deve ser configurável conforme os requisitos da aplicação.

Exemplo:

```json
{
  "event": "approved",
  "station": 2,
  "timestamp": "2026-01-01T12:00:00"
}
```

Para uma medição:

```json
{
  "event": "measurement_changed",
  "station": 1,
  "power": 850,
  "voltage": 121
}
```

Os payloads finais devem ser definidos de acordo com os endpoints reais da aplicação.

Não inventar endpoints ou contratos HTTP sem configuração.

---

# 13. Comunicação HTTP

O middleware deve possuir um cliente HTTP configurável.

Configurar:

```text
APPLICATION_BASE_URL
STATUS_ENDPOINT
APPROVED_ENDPOINT
REJECTED_ENDPOINT
...
```

Exemplo conceitual:

```text
Middleware
    |
    +---- POST /status
    |
    +---- POST /approved
    |
    +---- POST /rejected
    |
    +---- POST /measurement
```

Os endpoints devem ser configuráveis por ambiente.

---

# 14. Fluxo de escrita: aplicação → middleware → CLP

Também deve existir o caminho inverso.

Exemplo:

```text
Aplicação
    |
    | HTTP
    v
Middleware
    |
    | Modbus TCP
    v
CLP virtual
```

Exemplo de comando:

```json
{
  "station": 1,
  "command": "reset"
}
```

O middleware interpreta o comando e escreve no endereço Modbus correspondente.

Esse mecanismo deve ser preparado para funcionar tanto com o CLP virtual quanto posteriormente com o CLP real.

---

# 15. Separação entre lógica e infraestrutura

O middleware deve ser organizado para que as seguintes partes sejam independentes:

```text
Modbus Client
      ↓
Data Mapper
      ↓
State Manager
      ↓
Event Detector
      ↓
HTTP Client
```

Evitar colocar toda a lógica em um único arquivo.

A ideia é poder testar cada camada separadamente.

---

# 16. Configuração

Utilizar variáveis de ambiente para parâmetros que mudam entre ambientes.

Exemplo:

```text
MODBUS_HOST=127.0.0.1
MODBUS_PORT=5020
MODBUS_UNIT_ID=1
POLL_INTERVAL=1.0

APPLICATION_BASE_URL=http://localhost:8000
```

Para produção:

```text
MODBUS_HOST=<IP_DO_CLP_REAL>
MODBUS_PORT=502
MODBUS_UNIT_ID=<UNIT_ID>
```

O middleware não deve precisar ser reescrito para trocar o CLP virtual pelo CLP real.

---

# 17. Testes

O principal objetivo dessa arquitetura é facilitar testes.

Criar testes para situações como:

### Sem mudança

```text
CLP → mesmo estado
Middleware → nenhum HTTP
```

### Mudança de estado

```text
VAZIO → TESTANDO

Middleware → HTTP
```

### Aprovação

```text
contador aprovado: 10 → 11

Middleware → evento approved
```

### Reprovação

```text
contador reprovado: 3 → 4

Middleware → evento rejected
```

### Mudança de medição

```text
850 W → 900 W

Middleware → evento measurement_changed
```

### Reset

```text
Aplicação
    ↓ HTTP
Middleware
    ↓ Modbus
CLP virtual
    ↓
contador resetado
```

---

# 18. Logs

O middleware deve possuir logs claros.

Exemplo:

```text
[INFO] Conectado ao Modbus 127.0.0.1:5020
[INFO] Polling iniciado: 1.0s
[INFO] Estação 1: status alterado VAZIO -> TESTANDO
[INFO] Evento enviado: status_changed
[INFO] Estação 1: novo aprovado
[INFO] Evento enviado: approved
```

Em caso de erro:

```text
[ERROR] Falha de conexão Modbus
[ERROR] Falha ao enviar evento HTTP
```

Não gerar logs excessivos a cada segundo quando nada mudou.

---

# 19. Reconexão

O middleware deve suportar perda temporária de conexão.

Exemplo:

```text
Modbus conectado
      ↓
CLP desligado
      ↓
middleware detecta erro
      ↓
tenta reconectar
      ↓
CLP volta
      ↓
middleware reconecta
```

O mesmo conceito deve ser aplicado à aplicação HTTP quando apropriado.

---

# 20. Docker

Preferencialmente preparar os projetos para execução via Docker Compose.

Estrutura conceitual:

```text
projeto/
├── simulator/
│   ├── ...
│   └── Dockerfile
│
├── middleware/
│   ├── ...
│   └── Dockerfile
│
├── docker-compose.yml
└── README.md
```

O ambiente de desenvolvimento deve permitir:

```bash
docker compose up
```

e iniciar o simulador e o middleware.

A aplicação real poderá ser executada separadamente.

---

# 21. Desenvolvimento em etapas

Não tentar implementar todo o processo de uma vez.

## Etapa 1

Criar o servidor Modbus virtual.

Objetivo:

```text
Modbus Client → Servidor Modbus virtual
```

## Etapa 2

Criar a interface Web do simulador.

Objetivo:

```text
Interface Web → Memória Modbus virtual
```

## Etapa 3

Criar o middleware com leitura Modbus.

Objetivo:

```text
Simulador → Modbus → Middleware
```

## Etapa 4

Implementar comparação de estado.

Objetivo:

```text
Polling
   ↓
Estado atual
   ↓
Estado anterior
   ↓
Mudança
```

## Etapa 5

Implementar HTTP.

Objetivo:

```text
Simulador
   ↓
Modbus
   ↓
Middleware
   ↓
HTTP
   ↓
Aplicação
```

## Etapa 6

Implementar comandos no sentido inverso.

```text
Aplicação
   ↓
HTTP
   ↓
Middleware
   ↓
Modbus
   ↓
Simulador
```

## Etapa 7

Criar testes automatizados.

---

# 22. Requisitos de qualidade

O código deve priorizar:

- separação de responsabilidades;
- configuração por ambiente;
- código testável;
- logs claros;
- tratamento de erros;
- reconexão;
- mapa Modbus configurável;
- baixo acoplamento;
- documentação;
- facilidade de substituir o CLP virtual pelo CLP real.

Não criar dependências desnecessárias.

Não assumir informações do CLP que não estejam definidas.

---

# 23. Ponto importante sobre o mapa Modbus

O mapa Modbus real do teste de liquidificadores ainda não foi fornecido.

Portanto, implementar inicialmente um mapa virtual claramente documentado e facilmente substituível.

Quando o mapa real for disponibilizado, deve ser possível alterar:

```text
endereço
tipo de dado
escala
unidade
estação
descrição
```

sem modificar a lógica principal do middleware.

---

# 24. Resultado esperado

Ao final da primeira versão, deve ser possível executar:

```text
                    SIMULADOR
                ┌───────────────┐
                │ Interface Web │
                │      ↓        │
                │ Memória CLP  │
                │      ↓        │
                │ Modbus TCP    │
                └───────┬───────┘
                        │
                        ▼
                   MIDDLEWARE
                ┌───────────────┐
                │ Polling 1 s   │
                │      ↓        │
                │ Comparação    │
                │      ↓        │
                │ Eventos       │
                │      ↓        │
                │ HTTP          │
                └───────┬───────┘
                        │
                        ▼
                    APLICAÇÃO
```

O desenvolvedor deve conseguir abrir o simulador no navegador, alterar manualmente os estados das estações, observar as alterações na memória Modbus e verificar nos logs do middleware quais eventos foram detectados e enviados para a aplicação.

---

# 25. Diretriz para implementação

Implemente a solução de forma incremental.

Antes de criar uma interface sofisticada, faça o caminho mínimo funcionar:

```text
Servidor Modbus virtual
        ↓
Middleware
        ↓
Detecção de mudança
        ↓
HTTP
```

Depois adicione a interface semelhante à IHM.

A interface visual é importante para facilitar os testes, mas o principal objetivo técnico é criar uma representação confiável do CLP para validar o middleware.

As imagens fornecidas pelo usuário devem ser consideradas referência visual do processo e da organização das informações, mas não devem ser utilizadas para inventar endereços ou tipos Modbus.

Ao finalizar cada etapa, documente como executar, testar e validar o comportamento.
