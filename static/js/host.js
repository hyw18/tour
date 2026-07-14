const stateView = document.querySelector("#stateView");
const slotsEl = document.querySelector("#slots");
const hostBoardGrid = document.querySelector("#hostBoardGrid");
const rankingsEl = document.querySelector("#rankings");
const economyIndicators = document.querySelector("#economyIndicators");
const activeEventsEl = document.querySelector("#activeEvents");
const hostPhase = document.querySelector("#hostPhase");
const serverStatus = document.querySelector("#serverStatus");
const botMetrics = document.querySelector("#botMetrics");
const simProgress = document.querySelector("#simProgress");

let simulationRunning = false;
let simulationJobId = null;
let configLoaded = false;
let configDirty = false;
let hostPollTimer = null;
let requestInFlight = false;
let currentState = null;
let savedConfig = null;

function setHostAuthenticated(authenticated) {
  document.querySelector(".host-dashboard").dataset.authenticated = String(authenticated);
  document.querySelector("#hostAuthStatus").textContent = authenticated ? "호스트 인증 완료" : "호스트 인증이 필요합니다";
  document.querySelectorAll(".host-board-panel, .host-side > section:not(#hostAuthPanel), .host-log, .debug-tools")
    .forEach((element) => { element.hidden = !authenticated; });
}

function stopHostPolling() {
  if (hostPollTimer !== null) window.clearInterval(hostPollTimer);
  hostPollTimer = null;
}

function startHostPolling() {
  if (hostPollTimer !== null) return;
  hostPollTimer = window.setInterval(async () => {
    try {
      await refresh();
    } catch (error) {
      if (error.message === "host-auth-required") {
        stopHostPolling();
        setHostAuthenticated(false);
      } else {
        showError(error.message);
      }
    }
  }, 1000);
}

function showError(message) {
  const box = document.querySelector("#actionError");
  box.textContent = message;
  box.hidden = !message;
}

async function loadHostSession() {
  const response = await fetch("/api/host/session");
  const data = await response.json();
  window.hostCsrfToken = data.csrf_token || "";
  if (data.csrf_token) sessionStorage.setItem("hostCsrfToken", data.csrf_token);
  else sessionStorage.removeItem("hostCsrfToken");
  setHostAuthenticated(data.authenticated);
  return data.authenticated;
}

function money(value) {
  return new Intl.NumberFormat("ko-KR").format(Math.trunc(value || 0));
}

function boardCoord(index) {
  if (index <= 10) return { x: index + 1, y: 1 };
  if (index <= 20) return { x: 11, y: index - 9 };
  if (index <= 30) return { x: 31 - index, y: 11 };
  return { x: 1, y: 41 - index };
}

function cellName(cell) {
  return cell?.name || cell?.region_id || cell?.special_region_id || cell?.type || "";
}

async function getHostState() {
  const response = await fetch("/api/host/state");
  if (!response.ok) {
    if ([400, 401, 403].includes(response.status)) throw new Error("host-auth-required");
    throw new Error("호스트 상태를 불러오지 못했습니다");
  }
  return response.json();
}

function renderSlots(slotTypes, strategies) {
  const count = Number(document.querySelector("#totalSlots").value);
  const currentTypes = [...document.querySelectorAll("[data-slot-type]")].map((element) => element.value);
  const currentStrategies = [...document.querySelectorAll("[data-bot-strategy]")].map((element) => element.value);
  const types = slotTypes || currentTypes;
  const botStrategies = strategies || currentStrategies;
  slotsEl.innerHTML = "";
  for (let index = 0; index < count; index += 1) {
    const row = document.createElement("div");
    row.className = "slot-row";
    row.innerHTML = `
      <strong>${index + 1}</strong>
      <select data-slot-type="${index}">
        <option value="human">사람</option>
        <option value="bot">봇</option>
      </select>
      <select data-bot-strategy="${index}">
        <option value="balanced">balanced</option>
        <option value="aggressive">aggressive</option>
        <option value="conservative">conservative</option>
        <option value="random">random</option>
      </select>
    `;
    slotsEl.append(row);
    row.querySelector("[data-slot-type]").value = types[index] || "human";
    row.querySelector("[data-bot-strategy]").value = botStrategies[index] || "balanced";
  }
  syncSlotStrategyVisibility();
}

function renderConfig(config) {
  if (!config || (configDirty && configLoaded)) return;
  savedConfig = JSON.parse(JSON.stringify(config));
  document.querySelector("#totalSlots").value = String(config.total_slots);
  document.querySelector("#totalRounds").value = String(config.total_rounds);
  document.querySelector("#turnLimit").value = config.turn_limit_seconds == null ? "unlimited" : String(config.turn_limit_seconds);
  document.querySelector("#botDelay").value = String(config.bot_action_delay);
  document.querySelector("#fastSimulation").checked = Boolean(config.fast_simulation);
  renderSlots(config.slot_types, config.bot_strategies);
  configLoaded = true;
  configDirty = false;
  document.querySelector("#configDirty").hidden = true;
}

function updateControlsForPhase(state) {
  const phase = state.phase;
  const editable = ["setup", "lobby"].includes(phase) && !requestInFlight;
  document.querySelectorAll("#totalSlots,#totalRounds,#turnLimit,#botDelay,#fastSimulation,[data-slot-type]")
    .forEach((element) => { element.disabled = !editable; });
  document.querySelectorAll("[data-bot-strategy]").forEach((element) => {
    const type = element.closest(".slot-row")?.querySelector("[data-slot-type]")?.value;
    element.disabled = !editable || type !== "bot";
  });
  document.querySelector("#saveConfig").disabled = !editable || !configDirty;
  document.querySelector("#startGame").disabled = requestInFlight || !["setup", "lobby"].includes(phase) || configDirty;
  document.querySelector("#pauseGame").disabled = requestInFlight || phase !== "active";
  document.querySelector("#resumeGame").disabled = requestInFlight || phase !== "paused";
  document.querySelector("#finishGame").disabled = requestInFlight || !["active", "paused"].includes(phase);
  document.querySelector("#newGame").disabled = requestInFlight || phase !== "finished";
  document.querySelector("#resetAll").disabled = requestInFlight;

  const labels = { setup: "설정 중", lobby: "참가 대기", active: "진행 중", paused: "일시중지", finished: "종료됨", resetting: "초기화 중" };
  const nextActions = {
    setup: configDirty ? "설정 적용" : "게임 시작",
    lobby: configDirty ? "설정 적용" : "플레이어 확인 후 시작",
    active: "일시중지 또는 현재 게임 종료",
    paused: "재개 또는 현재 게임 종료",
    finished: "새 게임 준비",
    resetting: "초기화 완료 대기",
  };
  document.querySelector("#gameStatusText").textContent = labels[phase] || phase;
  document.querySelector("#configStatusText").textContent = configDirty ? "저장되지 않음" : (editable ? "저장됨" : "잠김");
  document.querySelector("#nextActionText").textContent = nextActions[phase] || "상태 확인";
  document.querySelector("#configDirty").hidden = !configDirty;
  document.querySelector("#saveConfig").classList.toggle("attention", configDirty);
}

function syncSlotStrategyVisibility() {
  document.querySelectorAll(".slot-row").forEach((row) => {
    const typeSelect = row.querySelector("[data-slot-type]");
    const strategySelect = row.querySelector("[data-bot-strategy]");
    if (!typeSelect || !strategySelect) return;
    strategySelect.hidden = typeSelect.value !== "bot";
    strategySelect.setAttribute("aria-hidden", String(typeSelect.value !== "bot"));
    typeSelect.addEventListener("change", () => {
      strategySelect.hidden = typeSelect.value !== "bot";
      strategySelect.setAttribute("aria-hidden", String(typeSelect.value !== "bot"));
      if (currentState) updateControlsForPhase(currentState);
    });
  });
}

function configPayload() {
  return {
    total_slots: Number(document.querySelector("#totalSlots").value),
    slot_types: [...document.querySelectorAll("[data-slot-type]")].map((el) => el.value),
    bot_strategies: [...document.querySelectorAll("[data-bot-strategy]")].map((el) => el.value),
    total_rounds: Number(document.querySelector("#totalRounds").value),
    turn_limit_seconds: document.querySelector("#turnLimit").value,
    bot_action_delay: Number(document.querySelector("#botDelay").value),
    fast_simulation: document.querySelector("#fastSimulation").checked
  };
}

function normalizedConfig(config) {
  return {
    total_slots: Number(config.total_slots),
    total_rounds: Number(config.total_rounds),
    slot_types: [...config.slot_types],
    bot_strategies: [...config.bot_strategies],
    turn_limit_seconds: ["unlimited", "none", ""].includes(String(config.turn_limit_seconds)) ? null : Number(config.turn_limit_seconds),
    bot_action_delay: Number(config.bot_action_delay),
    fast_simulation: Boolean(config.fast_simulation),
  };
}

function updateDirtyFromForm() {
  configDirty = !savedConfig || JSON.stringify(normalizedConfig(configPayload())) !== JSON.stringify(normalizedConfig(savedConfig));
  if (currentState) updateControlsForPhase(currentState);
}

function renderHostBoard(state) {
  hostBoardGrid.innerHTML = "";
  state.board.forEach((cell, index) => {
    const coord = boardCoord(index);
    const el = document.createElement("div");
    el.className = `board-cell host-cell cell-${cell.type || "plain"} ${index === 0 ? "start-cell" : ""}`;
    if (state.players.some((player) => player.position === index)) el.classList.add("current-cell");
    el.style.setProperty("--x", coord.x);
    el.style.setProperty("--y", coord.y);
    const buildings = state.buildings.filter((building) => building.region_id === cell.region_id).length;
    el.innerHTML = `
      <span class="cell-index">${index}</span>
      <strong>${cellName(cell)}</strong>
      <small>${buildings ? `건물 ${buildings}` : ""}</small>
      <div class="chip-stack"></div>
    `;
    const chips = el.querySelector(".chip-stack");
    state.players.filter((player) => player.position === index).forEach((player) => {
      const chip = document.createElement("span");
      chip.className = `chip ${player.is_bot ? "bot-chip" : ""}`;
      chip.textContent = player.nickname.slice(0, 2);
      chips.append(chip);
    });
    hostBoardGrid.append(el);
  });
}

function renderPublicPanels(state) {
  hostPhase.textContent = `${document.querySelector("#gameStatusText").textContent} · R${state.global_round}`;
  if (serverStatus) {
    serverStatus.textContent = state.server_status === "online" ? "서버 ON" : "서버 OFF";
    serverStatus.classList.toggle("on", state.server_status === "online");
    serverStatus.classList.toggle("off", state.server_status !== "online");
  }
  rankingsEl.innerHTML = (state.public_wealth?.players || [])
    .sort((a, b) => (a.rank || 999) - (b.rank || 999))
    .map((row) => `
      <div class="rank-row">
        <strong>${row.rank ?? "-"}</strong>
        <span>${row.nickname}</span>
        <em>${money(row.total_asset_won)}원</em>
      </div>
    `).join("");
  const rate = state.industrial_return_rate_bps || 0;
  economyIndicators.innerHTML = `
    <div class="metric sapphire"><span>산업 수익률</span><strong>${(rate / 100).toFixed(1)}%</strong></div>
    <div class="gauge host-gauge"><i style="left:50%"></i><b style="width:${Math.min(100, (rate / 2400) * 100)}%"></b></div>
    <div class="metric"><span>진행</span><strong>${state.ended ? "종료" : "진행 중"}</strong></div>
  `;
  activeEventsEl.innerHTML = (state.active_events || []).map((event) => `
    <div class="event-card">
      <strong>${event.id}</strong>
      <span>${event.age_rounds <= event.duration_rounds ? "활성" : "회복"}</span>
    </div>
  `).join("") || "<p>활성 이벤트 없음</p>";
}

function renderLog(state) {
  const lines = (state.game_log || []).slice(-80).map((entry) => {
    return `[R${entry.round}] ${entry.category} · ${entry.message}`;
  });
  stateView.textContent = lines.join("\n") || JSON.stringify(state, null, 2);
}

function renderBotMetrics(result) {
  if (!result) return;
  botMetrics.innerHTML = `
    <div class="metric emerald"><span>전략별 승률</span><strong>${JSON.stringify(result.strategy_win_rates || {})}</strong></div>
    <div class="metric ruby"><span>평균 파산 라운드</span><strong>${result.average_first_bankruptcy_round ?? "-"}</strong></div>
    <div class="metric sapphire"><span>대출률</span><strong>${result.loan_rate ?? "-"}</strong></div>
    <div class="metric"><span>건물별 수익</span><strong>${JSON.stringify(result.building_income_by_type || {})}</strong></div>
    <div class="metric"><span>자산 격차</span><strong>${money(result.average_top_asset_gap)}원</strong></div>
  `;
}

async function refresh(forceConfig = false) {
  const state = await getHostState();
  if (state.error) throw new Error(state.error);
  currentState = state;
  if (forceConfig) configDirty = false;
  renderConfig(state.config);
  updateControlsForPhase(state);
  renderHostBoard(state);
  renderPublicPanels(state);
  renderLog(state);
  renderBotMetrics(state.simulation_results);
}

document.querySelector("#totalSlots").addEventListener("change", () => renderSlots());
document.querySelector("#hostConfigPanel").addEventListener("input", (event) => {
  if (!event.target.matches("button")) {
    updateDirtyFromForm();
  }
});

async function runControl(buttonId, operation, successMessage) {
  if (requestInFlight) return;
  requestInFlight = true;
  const button = document.querySelector(buttonId);
  const originalText = button.textContent;
  button.textContent = "처리 중…";
  if (currentState) updateControlsForPhase(buttonId === "#resetAll" ? { ...currentState, phase: "resetting" } : currentState);
  try {
    await operation();
    await refresh(true);
    showError("");
    if (successMessage) stateView.textContent = successMessage;
  } catch (error) {
    await refresh(true).catch(() => {});
    showError(error.status === 409 ? "현재 상태에서는 실행할 수 없습니다" : error.message);
  } finally {
    requestInFlight = false;
    button.textContent = originalText;
    if (currentState) updateControlsForPhase(currentState);
  }
}
document.querySelector("#saveConfig").addEventListener("click", async () => {
  await runControl("#saveConfig", async () => {
    const saved = await postJson("/api/config", configPayload());
    configDirty = false;
    renderConfig(saved.config);
  }, "설정을 적용했습니다");
});
document.querySelector("#startGame").addEventListener("click", async () => {
  if (configDirty) { showError("설정을 먼저 적용하세요"); return; }
  await runControl("#startGame", () => postJson("/api/start"), "게임을 시작했습니다");
});
document.querySelector("#pauseGame").addEventListener("click", async () => {
  await runControl("#pauseGame", () => postJson("/api/pause"), "게임을 일시중지했습니다");
});
document.querySelector("#resumeGame").addEventListener("click", async () => {
  await runControl("#resumeGame", () => postJson("/api/resume"), "게임을 재개했습니다");
});
document.querySelector("#finishGame").addEventListener("click", async () => {
  if (!window.confirm("현재 게임 결과를 확정하고 종료할까요?")) return;
  await runControl("#finishGame", () => postJson("/api/host/finish"), "현재 게임을 종료했습니다");
});
document.querySelector("#newGame").addEventListener("click", async () => {
  await runControl("#newGame", () => postJson("/api/host/new-game", { keep_config: true }), "새 게임 설정을 변경할 수 있습니다");
});
document.querySelector("#resetAll").addEventListener("click", async () => {
  if (!window.confirm("게임 상태와 설정을 모두 초기화할까요?")) return;
  await runControl("#resetAll", () => postJson("/api/host/reset"), "전체 초기화를 완료했습니다");
});

document.querySelector("#hostLogin").addEventListener("click", async () => {
  const box = document.querySelector("#hostError");
  try {
    const result = await postJson("/api/host/login", { token: document.querySelector("#hostToken").value });
    window.hostCsrfToken = result.csrf_token;
    sessionStorage.setItem("hostCsrfToken", result.csrf_token);
    box.hidden = true;
    await loadHostSession();
    await refresh();
    startHostPolling();
  } catch (error) { box.textContent = error.message; box.hidden = false; }
});
document.querySelector("#hostLogout").addEventListener("click", async () => {
  try {
    await postJson("/api/host/logout");
    stopHostPolling();
    await loadHostSession();
  } catch (error) { showError(error.message); }
});

document.querySelector("#quick10").addEventListener("click", async () => {
  await postJson("/api/quick-game/configure", { preset: "fast_10" });
  await refresh();
});
document.querySelector("#quick30").addEventListener("click", async () => {
  await postJson("/api/quick-game/configure", { preset: "standard_30" });
  await refresh();
});
document.querySelector("#quick100").addEventListener("click", async () => {
  await postJson("/api/quick-game/configure", { preset: "long_100" });
  await refresh();
});
document.querySelector("#runSimulation").addEventListener("click", async () => {
  simulationRunning = true;
  simProgress.textContent = "실행 중";
  try {
    const job = await postJson("/api/bot-simulation", {
      players: Number(document.querySelector("#totalSlots").value),
      total_rounds: Number(document.querySelector("#totalRounds").value),
      events_enabled: document.querySelector("#simEvents").value === "true",
      event_frequency: Number(document.querySelector("#simFrequency").value),
      seed: Number(document.querySelector("#simSeed").value),
      runs: Number(document.querySelector("#simRuns").value)
    });
    simulationJobId = job.id;
    while (simulationRunning) {
      const response = await fetch(`/api/bot-simulation/${job.id}`);
      const status = await response.json();
      simProgress.textContent = `${status.completed_runs}/${status.total_runs} · ${status.status}`;
      if (["completed", "failed", "cancelled"].includes(status.status)) {
        simulationRunning = false;
        if (status.status === "completed") {
          const resultResponse = await fetch(`/api/bot-simulation/${job.id}/result`);
          const result = await resultResponse.json();
          renderBotMetrics(result.results.at(-1));
        }
        break;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 250));
    }
  } catch (error) {
    simProgress.textContent = error.message;
  }
});
document.querySelector("#stopSimulation").addEventListener("click", async () => {
  simulationRunning = false;
  simProgress.textContent = "중단 요청됨";
  if (simulationJobId) await postJson(`/api/bot-simulation/${simulationJobId}/cancel`);
});

document.querySelectorAll("[data-dev]").forEach((button) => {
  button.addEventListener("click", async () => {
    const action = button.dataset.dev;
    if (action === "force-end-turn") await postJson("/api/dev/force-end-turn");
    if (action === "bot-auto-start") await postJson("/api/dev/bot-auto", { enabled: true });
    if (action === "bot-auto-stop") await postJson("/api/dev/bot-auto", { enabled: false });
    if (action === "run-all-bot-max-speed") await postJson("/api/dev/run-all-bot-max-speed");
    if (action === "force-dice") await postJson("/api/dev/force-dice", { dice: Number(document.querySelector("#forcedDice").value) });
    if (action === "set-position") await postJson("/api/dev/set-position", {
      player_id: document.querySelector("#targetPlayerId").value,
      position: Number(document.querySelector("#targetPosition").value)
    });
    if (action === "set-cash") await postJson("/api/dev/set-cash", {
      player_id: document.querySelector("#targetPlayerId").value,
      cash_won: Number(document.querySelector("#targetCash").value)
    });
    if (action === "set-industrial-rate") await postJson("/api/dev/set-industrial-rate", {
      rate_bps: Number(document.querySelector("#industrialRateBps").value)
    });
    if (action === "set-tax-rate") await postJson("/api/dev/set-tax-rate", {
      player_id: document.querySelector("#targetPlayerId").value,
      tax_rate_bps: Number(document.querySelector("#targetTaxRateBps").value)
    });
    if (action === "create-loan") await postJson("/api/dev/create-loan", {
      player_id: document.querySelector("#targetPlayerId").value,
      principal_won: Number(document.querySelector("#loanPrincipal").value)
    });
    if (action === "settle-start") await postJson("/api/dev/settle-start", {
      player_id: document.querySelector("#targetPlayerId").value
    });
    if (action === "run-laps") await postJson("/api/dev/run-laps", {
      player_id: document.querySelector("#targetPlayerId").value,
      laps: Number(document.querySelector("#lapCount").value)
    });
    if (action === "bot-summary") {
      const response = await fetch("/api/dev/bot-summary");
      stateView.textContent = JSON.stringify(await response.json(), null, 2);
      return;
    }
    if (action === "create-land") await postJson("/api/dev/create-land", {
      player_id: document.querySelector("#targetPlayerId").value,
      region_id: document.querySelector("#targetRegionId").value
    });
    if (action === "create-building") await postJson("/api/dev/create-building", {
      player_id: document.querySelector("#targetPlayerId").value,
      region_id: document.querySelector("#targetRegionId").value,
      building_type: document.querySelector("#targetBuildingType").value
    });
    if (action === "sell-building") await postJson("/api/sell-building", {
      player_id: document.querySelector("#targetPlayerId").value,
      building_id: document.querySelector("#targetBuildingId").value
    });
    if (action === "set-special-visits") await postJson("/api/dev/set-special-visits", {
      special_region_id: document.querySelector("#targetSpecialId").value,
      visits: Number(document.querySelector("#specialVisits").value)
    });
    if (action === "force-special-sale-dice") await postJson("/api/dev/force-special-sale-dice", {
      dice: Number(document.querySelector("#specialSaleDice").value)
    });
    if (action === "run-bot-land-trade") await postJson("/api/dev/run-bot-land-trade", {
      seller_id: document.querySelector("#targetPlayerId").value,
      buyer_id: document.querySelector("#tradeBuyerId").value,
      region_id: document.querySelector("#targetRegionId").value
    });
    if (action === "change-bot-strategy") await postJson("/api/dev/change-bot-strategy", {
      player_id: document.querySelector("#targetPlayerId").value,
      strategy: document.querySelector("#targetBotStrategy").value
    });
    if (action === "run-next-turns") await postJson("/api/dev/run-next-turns", { turns: Number(document.querySelector("#nextTurns").value) });
    if (action === "fast-forward-rounds") await postJson("/api/dev/fast-forward-rounds", { rounds: Number(document.querySelector("#fastRounds").value) });
    await refresh();
  });
});

renderSlots();
loadHostSession().then(async (authenticated) => {
  if (!authenticated) return;
  try {
    await refresh();
    startHostPolling();
  } catch (error) {
    showError(error.message);
  }
});
