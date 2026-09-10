// Interface Web do simulador de CLP.
//
// A tela inteira e montada a partir de /api/map: nenhum endereco Modbus e
// nome de estacao aparece aqui. Trocar o mapa YAML muda a interface sozinho.
//
// Fluxo: clique -> POST na API -> memoria do CLP virtual -> Modbus TCP.

const POLL_MS = 500;

const state = {
  map: null,
  byName: {},
  stations: [],
  lastRevision: -1,
  tab: "operacao",
};

const EVENT_LABELS = {
  inserir_produto: "INSERIR PRODUTO",
  iniciar_teste: "INICIAR TESTE",
  aprovar: "APROVAR",
  reprovar: "REPROVAR",
  retirar_produto: "RETIRAR",
};

const EVENT_CLASS = { aprovar: "aprovar", reprovar: "reprovar" };

// --- acesso a API -----------------------------------------------------------

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = (await response.json()).detail || detail;
    } catch (_) { /* resposta sem corpo JSON */ }
    throw new Error(detail);
  }
  return response.json();
}

function setConnected(ok, message) {
  const el = document.getElementById("conn");
  el.classList.toggle("ok", ok);
  el.textContent = ok ? "simulador conectado" : "sem conexao: " + (message || "");
}

function announce(text) {
  document.getElementById("last-action").textContent = text;
}

function point(name) {
  return state.byName[name];
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// --- medidor analogico ------------------------------------------------------

function polar(cx, cy, radius, fraction) {
  const angle = Math.PI * (1 - Math.min(Math.max(fraction, 0), 1));
  return [cx + radius * Math.cos(angle), cy - radius * Math.sin(angle)];
}

function buildGauge(maximum, unit) {
  const NS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("class", "gauge");
  svg.setAttribute("viewBox", "0 0 220 128");
  svg.setAttribute("width", "220");
  svg.setAttribute("height", "128");

  const cx = 110, cy = 112, r = 88;
  const [sx, sy] = polar(cx, cy, r, 0);
  const [ex, ey] = polar(cx, cy, r, 1);
  const arc = document.createElementNS(NS, "path");
  arc.setAttribute("class", "arco");
  arc.setAttribute("d", `M ${sx} ${sy} A ${r} ${r} 0 0 1 ${ex} ${ey}`);
  svg.appendChild(arc);

  const steps = 10;
  const divisor = maximum >= 1000 ? 100 : 1;
  for (let i = 0; i <= steps; i += 1) {
    const fraction = i / steps;
    const [x1, y1] = polar(cx, cy, r - 9, fraction);
    const [x2, y2] = polar(cx, cy, r - 1, fraction);
    const tick = document.createElementNS(NS, "line");
    tick.setAttribute("class", "marca");
    tick.setAttribute("x1", x1); tick.setAttribute("y1", y1);
    tick.setAttribute("x2", x2); tick.setAttribute("y2", y2);
    svg.appendChild(tick);

    const [lx, ly] = polar(cx, cy, r - 20, fraction);
    const label = document.createElementNS(NS, "text");
    label.setAttribute("class", "rotulo");
    label.setAttribute("x", lx);
    label.setAttribute("y", ly + 3);
    label.textContent = String(Math.round((maximum * fraction) / divisor));
    svg.appendChild(label);
  }

  const needle = document.createElementNS(NS, "line");
  needle.setAttribute("class", "ponteiro");
  needle.setAttribute("x1", cx); needle.setAttribute("y1", cy);
  const [nx, ny] = polar(cx, cy, r - 14, 0);
  needle.setAttribute("x2", nx); needle.setAttribute("y2", ny);
  svg.appendChild(needle);

  const hub = document.createElementNS(NS, "circle");
  hub.setAttribute("class", "eixo");
  hub.setAttribute("cx", cx); hub.setAttribute("cy", cy); hub.setAttribute("r", "5");
  svg.appendChild(hub);

  if (divisor > 1) {
    const escala = document.createElementNS(NS, "text");
    escala.setAttribute("class", "rotulo");
    escala.setAttribute("x", cx);
    escala.setAttribute("y", 14);
    escala.textContent = `x${divisor}${unit ? " " + unit : ""}`;
    svg.appendChild(escala);
  }

  svg.dataset.max = String(maximum);
  svg.needle = needle;
  return svg;
}

function updateGauge(svg, value) {
  const maximum = Number(svg.dataset.max) || 1;
  const [x, y] = polar(110, 112, 74, value / maximum);
  svg.needle.setAttribute("x2", x);
  svg.needle.setAttribute("y2", y);
}

// --- montagem da tela de operacao ------------------------------------------

async function writePoint(name, value, station, index) {
  const body = { value: value, station: station ?? null, index: index ?? null };
  await api(`/api/points/${name}`, { method: "POST", body: JSON.stringify(body) });
  const alvo = station ? `estacao ${station}` : "global";
  announce(`${name} (${alvo}) = ${value}`);
}

function numericControl(def, station) {
  const row = el("div", "controle");
  row.appendChild(el("label", null, def.label || def.name));

  const maximum = def.max ?? 1000;
  const minimum = def.min ?? 0;
  const step = def.decimals > 0 ? Math.pow(10, -def.decimals) : 1;

  const range = el("input");
  range.type = "range";
  range.min = minimum; range.max = maximum; range.step = step;

  const number = el("input");
  number.type = "number";
  number.min = minimum; number.max = maximum; number.step = step;

  const send = async (value) => {
    range.value = value;
    number.value = value;
    try {
      await writePoint(def.name, Number(value), station);
    } catch (error) {
      announce(`erro ao escrever ${def.name}: ${error.message}`);
    }
  };

  range.addEventListener("input", () => { number.value = range.value; });
  range.addEventListener("change", () => send(range.value));
  number.addEventListener("change", () => send(number.value));

  row.appendChild(range);
  row.appendChild(number);
  if (def.unit) row.appendChild(el("span", "hint", def.unit));

  row.inputs = { range, number };
  return row;
}

function lampRow(def, station) {
  const row = el("div", "lamps");
  row.lamps = [];
  for (let i = 0; i < def.count; i += 1) {
    const lamp = el("div", "lamp");
    lamp.appendChild(el("div", "bulb"));
    lamp.appendChild(el("span", null, def.item_labels[i] || `${i}`));
    lamp.addEventListener("click", async () => {
      const ligado = lamp.classList.contains("on");
      try {
        await writePoint(def.name, !ligado, station, i);
      } catch (error) {
        announce(`erro na posicao ${i}: ${error.message}`);
      }
    });
    row.appendChild(lamp);
    row.lamps.push(lamp);
  }
  return row;
}

function eventButtons(station) {
  const row = el("div", "eventos");
  row.buttons = {};
  for (const [name, label] of Object.entries(EVENT_LABELS)) {
    const button = el("button", EVENT_CLASS[name] || null, label);
    button.type = "button";
    button.addEventListener("click", async () => {
      try {
        const result = await api(`/api/stations/${station}/event`, {
          method: "POST",
          body: JSON.stringify({ event: name }),
        });
        announce(`estacao ${station}: ${result.from} -> ${result.to}`);
        refresh();
      } catch (error) {
        announce(`estacao ${station}: ${error.message}`);
      }
    });
    row.appendChild(button);
    row.buttons[name] = button;
  }
  return row;
}

function buildStationCard(station) {
  const card = el("div", "card");
  card.appendChild(el("h2", null, station.label));
  const widgets = { station: station.id };

  const power = point("power");
  if (power) {
    const gauge = buildGauge(power.max ?? 1000, power.unit);
    card.appendChild(gauge);
    const leitura = el("div", "leitura", "0 W");
    card.appendChild(leitura);
    widgets.gauge = gauge;
    widgets.leitura = leitura;
  }

  const estado = el("div", "estado", "VAZIO");
  card.appendChild(estado);
  widgets.estado = estado;

  const positions = point("positions");
  if (positions) {
    const lamps = lampRow(positions, station.id);
    card.appendChild(lamps);
    widgets.lamps = lamps;
  }

  if (power) {
    const control = numericControl(power, station.id);
    card.appendChild(control);
    widgets.powerControl = control;
  }

  const events = eventButtons(station.id);
  card.appendChild(events);
  widgets.events = events;

  return { card, widgets };
}

function buildHistoryCard(station) {
  const card = el("div", "card");
  card.appendChild(el("h2", null, station.label));
  const widgets = {};

  const counters = [
    ["total", "TOTAL", ""],
    ["approved", "APROVADO", "aprovado"],
    ["rejected", "REPROVADO", "reprovado"],
  ];
  for (const [name, label, css] of counters) {
    if (!point(name)) continue;
    const box = el("div", `contador ${css}`.trim());
    box.appendChild(el("label", null, label));
    const valor = el("div", "valor", "0");
    box.appendChild(valor);
    card.appendChild(box);
    widgets[name] = valor;
  }

  const indice = el("div", "contador");
  indice.appendChild(el("label", null, "INDICE REP."));
  const indiceValor = el("div", "valor", "0.00 %");
  indice.appendChild(indiceValor);
  card.appendChild(indice);
  widgets.indice = indiceValor;

  const reset = el("button", "btn", `RESET ${String(station.id).padStart(2, "0")}`);
  reset.type = "button";
  reset.addEventListener("click", async () => {
    try {
      await api(`/api/stations/${station.id}/reset`, { method: "POST" });
      announce(`estacao ${station.id}: contadores zerados pela IHM`);
      refresh();
    } catch (error) {
      announce(`erro no reset: ${error.message}`);
    }
  });
  card.appendChild(reset);

  return { card, widgets };
}

function buildGlobals() {
  const bar = document.getElementById("global-bar");
  bar.innerHTML = "";
  state.globals = {};
  for (const def of state.map.points) {
    if (def.scope !== "global") continue;
    const item = el("div", "global-item");
    item.appendChild(el("label", null, (def.label || def.name).toUpperCase()));
    const output = el("output", null, "-");
    item.appendChild(output);
    if (def.access.includes("w") && def.kind.includes("register")) {
      const control = numericControl(def, null);
      control.querySelector("label").remove();
      item.appendChild(control);
      state.globals[def.name] = { output, control };
    } else {
      state.globals[def.name] = { output };
    }
    bar.appendChild(item);
  }
}

// --- atualizacao ------------------------------------------------------------

function formatValue(def, value) {
  if (value === null || value === undefined) return "-";
  const text = Number(value).toFixed(def.decimals || 0);
  return def.unit ? `${text} ${def.unit}` : text;
}

function syncInput(control, value) {
  if (!control) return;
  const { range, number } = control.inputs;
  if (document.activeElement !== range) range.value = value;
  if (document.activeElement !== number) number.value = value;
}

function updateOperation(data) {
  for (const [name, widgets] of Object.entries(state.globals)) {
    const entry = data.globals[name];
    if (!entry) continue;
    widgets.output.textContent = formatValue(point(name), entry.value);
    syncInput(widgets.control, entry.value);
  }

  for (const widgets of state.stationWidgets) {
    const values = data.stations[String(widgets.station)];
    if (!values) continue;

    if (widgets.gauge && values.power) {
      updateGauge(widgets.gauge, values.power.value);
      widgets.leitura.textContent = formatValue(point("power"), values.power.value);
      syncInput(widgets.powerControl, values.power.value);
    }

    widgets.estado.textContent = values.status_label || "-";
    widgets.estado.dataset.estado = values.status_label || "";

    if (widgets.lamps && values.positions) {
      values.positions.value.forEach((on, index) => {
        widgets.lamps.lamps[index].classList.toggle("on", Boolean(on));
      });
    }

    const allowed = values.allowed_events || [];
    for (const [name, button] of Object.entries(widgets.events.buttons)) {
      button.disabled = !allowed.includes(name);
    }
  }
}

function updateHistory(data) {
  for (const widgets of state.historyWidgets) {
    const values = data.stations[String(widgets.station)];
    if (!values) continue;
    let total = 0;
    let rejected = 0;
    for (const name of ["total", "approved", "rejected"]) {
      if (!widgets[name] || !values[name]) continue;
      widgets[name].textContent = String(values[name].value);
      if (name === "total") total = values[name].value;
      if (name === "rejected") rejected = values[name].value;
    }
    const indice = total > 0 ? (rejected / total) * 100 : 0;
    widgets.indice.textContent = `${indice.toFixed(2)} %`;
  }
}

async function refresh() {
  try {
    const data = await api("/api/state");
    setConnected(true);
    updateOperation(data);
    updateHistory(data);
    if (state.tab === "memoria") await refreshMemory();
  } catch (error) {
    setConnected(false, error.message);
  }
}

// --- aba de memoria ---------------------------------------------------------

async function refreshMemory() {
  const kind = document.getElementById("memory-kind").value;
  const limit = Number(document.getElementById("memory-limit").value);
  const mappedOnly = document.getElementById("memory-mapped-only").checked;
  const data = await api(`/api/memory?limit=${limit}`);
  const cells = data.areas[kind] || [];
  const container = document.getElementById("memory");
  const visiveis = mappedOnly ? cells.filter((c) => c.owner) : cells;

  container.innerHTML = "";
  for (const cell of visiveis) {
    const node = el("div", "mem-cell" + (cell.value ? " ativo" : ""));
    node.appendChild(el("span", "addr", String(cell.address).padStart(4, "0")));
    node.appendChild(el("span", "owner", cell.owner || ""));
    node.appendChild(el("span", "val", String(cell.value)));
    container.appendChild(node);
  }
  document.getElementById("memory-hint").textContent =
    `${visiveis.length} de ${cells.length} enderecos - revisao ${data.revision}`;
}

// --- abas, relogio e inicializacao ------------------------------------------

function bindTabs() {
  const buttons = document.querySelectorAll("#tabs button");
  buttons.forEach((button) => {
    button.addEventListener("click", () => {
      buttons.forEach((other) => other.classList.toggle("active", other === button));
      state.tab = button.dataset.tab;
      document.querySelectorAll(".tab").forEach((section) => {
        section.classList.toggle("hidden", section.id !== `tab-${state.tab}`);
      });
      refresh();
    });
  });

  ["memory-kind", "memory-limit", "memory-mapped-only"].forEach((id) => {
    document.getElementById(id).addEventListener("change", () => refreshMemory());
  });
}

function tickClock() {
  document.getElementById("clock").textContent =
    new Date().toLocaleTimeString("pt-BR", { hour12: false });
}

async function boot() {
  state.map = await api("/api/map");
  state.map.points.forEach((def) => { state.byName[def.name] = def; });

  document.getElementById("title").textContent = state.map.title;
  document.getElementById("map-info").textContent =
    `mapa: ${state.map.name} | fonte: ${state.map.source}`;

  buildGlobals();

  const stationsContainer = document.getElementById("stations");
  const historyContainer = document.getElementById("history");
  state.stationWidgets = [];
  state.historyWidgets = [];

  for (const station of state.map.stations) {
    const operation = buildStationCard(station);
    stationsContainer.appendChild(operation.card);
    state.stationWidgets.push(operation.widgets);

    const history = buildHistoryCard(station);
    historyContainer.appendChild(history.card);
    state.historyWidgets.push({ ...history.widgets, station: station.id });
  }

  bindTabs();
  tickClock();
  setInterval(tickClock, 1000);
  await refresh();
  setInterval(refresh, POLL_MS);
}

boot().catch((error) => {
  setConnected(false, error.message);
  announce(`falha ao iniciar a interface: ${error.message}`);
});
