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
const boardStatus = document.querySelector("#boardStatus");

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
  document.querySelectorAll(".authenticated-content, .debug-tools")
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
  const url = "/api/host/state";
  let response;
  try {
    response = await fetch("/api/host/state");
  } catch (error) {
    console.error("Host state request failed", { url, error });
    setServerReachability(false);
    throw new Error("서버에 연결할 수 없습니다");
  }
  if (!response.ok) {
    const responseBody = await response.text();
    console.error("Host state request failed", { url, status: response.status, response: responseBody });
    if ([401, 403].includes(response.status)) throw new Error("host-auth-required");
    throw new Error("호스트 상태를 불러오지 못했습니다");
  }
  const state = await response.json();
  setServerReachability(true);
  return state;
}

function setServerReachability(online) {
  if (!serverStatus) return;
  serverStatus.innerHTML = online ? '<i aria-hidden="true">●</i> ON' : '<i aria-hidden="true">●</i> OFF';
  serverStatus.classList.toggle("on", online);
  serverStatus.classList.toggle("off", !online);
}

function setBoardStatus(message, kind = "loading") {
  if (!boardStatus) return;
  boardStatus.textContent = message;
  boardStatus.className = `board-status ${kind}`;
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
      <span class="slot-status">✓ 준비</span>
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
  const readySlots = new Set((state.players || []).filter((player) => player.status !== "exited").map((player) => player.slot_index));
  const allSlotsReady = readySlots.size === Number(state.config?.total_slots || 0);
  document.querySelectorAll("#totalSlots,#totalRounds,#turnLimit,#botDelay,#fastSimulation,[data-slot-type]")
    .forEach((element) => { element.disabled = !editable; });
  document.querySelectorAll("[data-bot-strategy]").forEach((element) => {
    const type = element.closest(".slot-row")?.querySelector("[data-slot-type]")?.value;
    element.disabled = !editable || type !== "bot";
  });
  document.querySelector("#saveConfig").disabled = !editable || !configDirty;
  document.querySelector("#startGame").disabled = requestInFlight || !["setup", "lobby"].includes(phase) || configDirty || !allSlotsReady;
  document.querySelector("#startGame").title = !allSlotsReady ? "모든 참가 슬롯이 준비되어야 시작할 수 있습니다" : "";
  document.querySelector("#pauseGame").disabled = requestInFlight || phase !== "active";
  document.querySelector("#resumeGame").disabled = requestInFlight || phase !== "paused";
  document.querySelector("#finishGame").disabled = requestInFlight || !["active", "paused"].includes(phase);
  document.querySelector("#newGame").disabled = requestInFlight || phase !== "finished";
  document.querySelector("#resetAll").disabled = requestInFlight;
  document.querySelector("#viewResults").disabled = phase !== "finished";
  document.querySelector("#hostConfigPanel").classList.toggle("is-locked", phase === "finished");
  document.querySelector("#configLockNotice").hidden = phase !== "finished";

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
  document.querySelector("#configStatusText").textContent = configDirty ? "변경사항 있음" : (editable ? "저장됨" : "잠김");
  document.querySelector("#nextActionText").textContent = nextActions[phase] || "상태 확인";
  document.querySelector("#configDirty").hidden = !configDirty;
  document.querySelector("#saveConfig").classList.toggle("attention", configDirty);
  document.querySelector("#newGame").classList.toggle("is-recommended", phase === "finished");
  document.querySelector("#pauseGame").classList.toggle("is-recommended", phase === "active");
  document.querySelector("#resumeGame").classList.toggle("is-recommended", phase === "paused");
  const guidance = document.querySelector("#configGuidance");
  guidance.textContent = phase === "finished" ? "🔒 새 게임 준비 후 설정 변경 가능" :
    (["active", "paused"].includes(phase) ? "🔒 게임 진행 중에는 설정을 변경할 수 없습니다" : "✓ 설정 저장됨");
  guidance.hidden = configDirty;
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
  if (!hostBoardGrid) throw new Error("보드 컨테이너를 찾을 수 없습니다");
  if (!Array.isArray(state.board) || state.board.length !== 40) {
    console.error("Invalid board data", {
      url: "/api/host/state",
      status: 200,
      response: state,
      missingFields: !Array.isArray(state.board) ? ["board"] : [`board length: ${state.board.length}`],
    });
    hostBoardGrid.replaceChildren();
    setBoardStatus("보드 데이터를 불러오지 못했습니다.", "error");
    return false;
  }
  const players = Array.isArray(state.players) ? state.players : [];
  const buildings = Array.isArray(state.buildings) ? state.buildings : [];
  const ownership = state.land_ownership || {};
  hostBoardGrid.innerHTML = "";
  state.board.forEach((cell, index) => {
    const coord = boardCoord(index);
    const el = document.createElement("div");
    el.className = `board-cell host-cell cell-${cell.type || "plain"} ${index === 0 ? "start-cell" : ""}`;
    if (players.some((player) => player.position === index)) el.classList.add("current-cell");
    el.style.setProperty("--x", coord.x);
    el.style.setProperty("--y", coord.y);
    const buildingCount = buildings.filter((building) => building.region_id === cell.region_id).length;
    const ownerId = cell.region_id ? ownership[cell.region_id] : null;
    const owner = players.find((player) => player.id === ownerId);
    el.innerHTML = `
      <span class="cell-index">${index}</span>
      <strong>${cellName(cell)}</strong>
      <small>${owner ? `소유 ${owner.nickname}` : (buildingCount ? `건물 ${buildingCount}` : "")}</small>
      <div class="chip-stack"></div>
    `;
    const chips = el.querySelector(".chip-stack");
    players.filter((player) => player.position === index).forEach((player) => {
      const chip = document.createElement("span");
      chip.className = `chip ${player.is_bot ? "bot-chip" : ""}`;
      chip.textContent = player.nickname.slice(0, 2);
      chips.append(chip);
    });
    hostBoardGrid.append(el);
  });
  setBoardStatus("보드 준비 완료", "ready");
  window.requestAnimationFrame(() => {
    const style = window.getComputedStyle(hostBoardGrid);
    const bounds = hostBoardGrid.getBoundingClientRect();
    if (!bounds.width || !bounds.height || style.display === "none" || style.visibility === "hidden") {
      console.error("Board container is not visible", { bounds: bounds.toJSON?.() || bounds, display: style.display, visibility: style.visibility });
      setBoardStatus("보드 렌더링 영역을 표시할 수 없습니다.", "error");
    }
  });
  return true;
}

function renderPublicPanels(state) {
  hostPhase.textContent = `${document.querySelector("#gameStatusText").textContent} · R${state.global_round}`;
  setServerReachability(state.server_status === "online");
  const hostingOpen = state.engine_phase === "lobby" && !state.ended;
  document.querySelector("#hostingStatusText").textContent = hostingOpen ? "열림" : "닫힘";
  const currentPlayer = state.players?.find((player) => player.id === state.current_turn_player_id) || null;
  const turnName = currentPlayer?.nickname || "-";
  document.querySelector("#currentRoundText").textContent = state.global_round ?? "-";
  document.querySelector("#currentTurnText").textContent = turnName;
  document.querySelector("#summaryRound").textContent = `${state.global_round ?? "-"} / ${state.config?.total_rounds ?? "-"}`;
  document.querySelector("#summaryPlayers").textContent = `${state.players?.length || 0}명`;
  document.querySelector("#summaryTurn").textContent = turnName;
  document.querySelectorAll(".slot-row").forEach((row, index) => {
    const player = state.players?.find((item) => item.slot_index === index && item.status !== "exited");
    const status = row.querySelector(".slot-status");
    if (status) status.textContent = player ? "✓ 준비" : "○ 대기";
    if (status) status.classList.toggle("waiting", !player);
  });
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
  const renderStep = (name, operation) => {
    try { operation(); }
    catch (error) {
      console.error(`Host render step failed: ${name}`, error);
      if (name === "board") setBoardStatus("보드 렌더링 중 오류가 발생했습니다.", "error");
      else showError(`${name} 영역을 표시하지 못했습니다`);
    }
  };
  renderStep("config", () => renderConfig(state.config));
  renderStep("board", () => renderHostBoard(state));
  renderStep("game status", () => renderPublicPanels(state));
  renderStep("controls", () => updateControlsForPhase(state));
  renderStep("log", () => renderLog(state));
  renderStep("simulation", () => renderBotMetrics(state.simulation_results));
}

document.querySelector("#totalSlots").addEventListener("change", () => renderSlots());
document.querySelector("#viewResults").addEventListener("click", () => {
  document.querySelector("#resultsPanel").scrollIntoView({ behavior: "smooth", block: "start" });
});
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
    await initializeHostDashboard();
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
    if (action === "sell-building") await postJson("/api/dev/sell-building", {
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

async function initializeHostDashboard() {
  setBoardStatus("보드를 불러오는 중입니다…");
  try {
    await refresh();
    startHostPolling();
  } catch (error) {
    if (error.message === "host-auth-required") {
      stopHostPolling();
      setHostAuthenticated(false);
      setBoardStatus("호스트 인증이 필요합니다.", "error");
      return;
    }
    setServerReachability(false);
    setBoardStatus("보드 데이터 요청이 실패했습니다. 잠시 후 다시 시도합니다.", "error");
    showError(error.message);
  }
}

async function initializeHostPage() {
  renderSlots();
  try {
    const authenticated = await loadHostSession();
    if (!authenticated) return;
    await initializeHostDashboard();
  } catch (error) {
    setServerReachability(false);
    showError("호스트 페이지를 초기화하지 못했습니다");
    console.error("Host page initialization failed", error);
  }
}

document.addEventListener("DOMContentLoaded", initializeHostPage, { once: true });
