const state = {};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[char]);

const loadJson = async (path) => {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
  return response.json();
};

function operationEntries(spec) {
  const methods = new Set(["get", "post", "put", "patch", "delete", "head", "options"]);
  return Object.entries(spec.paths).flatMap(([path, pathItem]) =>
    Object.entries(pathItem)
      .filter(([method]) => methods.has(method))
      .map(([method, operation]) => ({ path, method, operation }))
  );
}

function renderMetrics(summary) {
  const metrics = [
    [summary.alpacaOperations, "Alpaca operations"],
    [summary.websocketCommands, "WebSocket codes"],
    [summary.responseCodes, "Response codes"],
    [summary.deviceHttpOperations, "Device HTTP registrations"],
    [summary.cloudHttpOperations, "Cloud HTTP registrations"],
    [summary.bleCommands, "BLE commands"],
  ];
  document.querySelector("#metrics").innerHTML = metrics.map(([value, label]) =>
    `<div class="metric"><strong>${value}</strong><span>${label}</span></div>`
  ).join("");
  document.querySelector("#ws-count").textContent = `${summary.websocketCommands} registered codes`;
}

function endpointHtml(entry) {
  const { method, path, operation } = entry;
  const tags = (operation.tags || []).join(", ");
  const details = operation.description || "No additional description is available.";
  const parameters = operation.parameters || [];
  const parameterText = parameters.length
    ? `<p><strong>Parameters:</strong> ${parameters.map((item) => `<code>${escapeHtml(item.name)}</code> (${escapeHtml(item.in)})`).join(", ")}</p>`
    : "";
  const body = operation.requestBody ? "<p><strong>Request body:</strong> JSON payload</p>" : "";
  return `<details class="endpoint">
    <summary><span class="method ${method}">${method.toUpperCase()}</span><span class="path">${escapeHtml(path)}</span><span class="summary">${escapeHtml(operation.summary || operation.operationId || tags)}</span></summary>
    <div class="endpoint-body"><p>${escapeHtml(details)}</p>${parameterText}${body}<p class="evidence">Operation ID: <code>${escapeHtml(operation.operationId || "unassigned")}</code>${tags ? ` · ${escapeHtml(tags)}` : ""}</p></div>
  </details>`;
}

function filterOperations(kind) {
  const entries = state[`${kind}Entries`];
  const query = document.querySelector(`#${kind}-search`).value.trim().toLowerCase();
  const tag = kind === "alpaca" ? document.querySelector("#alpaca-tag").value : "";
  const filtered = entries.filter(({ path, method, operation }) => {
    const haystack = `${path} ${method} ${operation.summary || ""} ${operation.operationId || ""} ${(operation.tags || []).join(" ")}`.toLowerCase();
    return (!query || haystack.includes(query)) && (!tag || (operation.tags || []).includes(tag));
  });
  document.querySelector(`#${kind}-list`).innerHTML = filtered.length
    ? filtered.map(endpointHtml).join("")
    : '<p class="empty">No matching operations.</p>';
}

function commandEvidence(command) {
  const wrappers = command.request_wrappers || [];
  const handlers = command.notification_handlers || [];
  const requestMessages = wrappers.flatMap((item) => item.protobuf_messages || []);
  const responseMessages = wrappers.flatMap((item) => item.response_messages || []);
  const notificationMessages = handlers.map((item) => item.protobuf_message);
  return [...new Set([...requestMessages, ...responseMessages, ...notificationMessages])];
}

function renderCommands() {
  const query = document.querySelector("#ws-search").value.trim().toLowerCase();
  const direction = document.querySelector("#ws-direction").value;
  const evidenceFilter = document.querySelector("#ws-evidence").value;
  const filtered = state.inventory.commands.filter((command) => {
    const evidence = commandEvidence(command);
    const haystack = `${command.command_id} ${command.name} ${evidence.join(" ")}`.toLowerCase();
    return (!query || haystack.includes(query))
      && (!direction || command.direction === direction)
      && (!evidenceFilter || (evidenceFilter === "payload" ? evidence.length : !evidence.length));
  });
  document.querySelector("#ws-table").innerHTML = filtered.map((command) => {
    const evidence = commandEvidence(command);
    return `<tr><td>${escapeHtml(command.command_id ?? command.raw_value_expression)}</td><td><code>${escapeHtml(command.name)}</code></td><td>${escapeHtml(command.direction)}</td><td>${evidence.length ? evidence.map((item) => `<code>${escapeHtml(item)}</code>`).join("<br>") : '<span class="evidence">Schema unresolved</span>'}</td></tr>`;
  }).join("");
}

function renderCloud() {
  const query = document.querySelector("#cloud-search").value.trim().toLowerCase();
  const endpoints = state.inventory.http_endpoints.filter((item) => item.scope !== "device");
  const filtered = endpoints.filter((item) =>
    `${item.scope} ${item.method} ${item.path} ${item.operation}`.toLowerCase().includes(query)
  );
  document.querySelector("#cloud-table").innerHTML = filtered.map((item) =>
    `<tr><td>${escapeHtml(item.scope)}</td><td><span class="method ${item.method.toLowerCase()}">${escapeHtml(item.method)}</span></td><td><code>${escapeHtml(item.path)}</code></td><td><code>${escapeHtml(item.operation)}</code></td></tr>`
  ).join("");
}

function renderErrors() {
  const query = document.querySelector("#error-search").value.trim().toLowerCase();
  const filtered = state.inventory.response_codes.filter((item) => `${item.code} ${item.name}`.toLowerCase().includes(query));
  document.querySelector("#error-table").innerHTML = filtered.map((item) => `<tr><td>${item.code}</td><td><code>${escapeHtml(item.name)}</code></td></tr>`).join("");
}

function renderBle() {
  const ble = state.inventory.ble;
  document.querySelector("#ble-content").innerHTML = `
    <div>${ble.commands.map((item) => `<div class="ble-command"><b>${item.id}</b><div><code>${escapeHtml(item.request)}</code><br><span class="evidence">Response: ${escapeHtml(item.response)}</span></div></div>`).join("")}</div>
    <div class="uuid-list"><p class="eyebrow">Registered UUIDs</p>${ble.uuids.map((item) => `<code>${escapeHtml(item.uuid)}</code>`).join("")}</div>`;
}

function renderUnknowns() {
  const unknowns = state.inventory.commands.filter((command) => commandEvidence(command).length === 0);
  document.querySelector("#unknown-list").innerHTML = unknowns.map((command) => `<div class="unknown-item"><b>${escapeHtml(command.command_id)} · ${escapeHtml(command.name)}</b><span>${escapeHtml(command.direction)} · registered, payload schema unresolved</span></div>`).join("");
}

async function init() {
  try {
    const [summary, alpaca, device, inventory] = await Promise.all([
      loadJson("summary.json"), loadJson("openapi.json"), loadJson("device-openapi.json"), loadJson("protocol-inventory.json"),
    ]);
    Object.assign(state, { summary, alpaca, device, inventory });
    state.alpacaEntries = operationEntries(alpaca);
    state.httpEntries = operationEntries(device);
    renderMetrics(summary);
    const tags = [...new Set(state.alpacaEntries.flatMap((entry) => entry.operation.tags || []))].sort();
    document.querySelector("#alpaca-tag").insertAdjacentHTML("beforeend", tags.map((tag) => `<option value="${escapeHtml(tag)}">${escapeHtml(tag)}</option>`).join(""));
    filterOperations("alpaca"); filterOperations("http"); renderCloud(); renderCommands(); renderErrors(); renderBle(); renderUnknowns();
    ["alpaca-search", "alpaca-tag"].forEach((id) => document.querySelector(`#${id}`).addEventListener("input", () => filterOperations("alpaca")));
    document.querySelector("#http-search").addEventListener("input", () => filterOperations("http"));
    document.querySelector("#cloud-search").addEventListener("input", renderCloud);
    ["ws-search", "ws-direction", "ws-evidence"].forEach((id) => document.querySelector(`#${id}`).addEventListener("input", renderCommands));
    document.querySelector("#error-search").addEventListener("input", renderErrors);
  } catch (error) {
    document.querySelector("main").innerHTML = `<section class="panel"><h2>Documentation data could not be loaded</h2><p>${escapeHtml(error.message)}</p><p>Serve this directory over HTTP instead of opening index.html directly.</p></section>`;
  }
}

init();
