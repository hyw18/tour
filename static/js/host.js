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
let roomOpened = false;

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
  if (!response.ok) return getState();
  return response.json();
}

function renderSlots() {
  const count = Number(document.querySelector("#totalSlots").value);
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
  }
  syncSlotStrategyVisibility();
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
  hostPhase.textContent = `${state.phase} · R${state.global_round}`;
  if (serverStatus) {
    const isOn = roomOpened || state.phase !== "lobby" || state.players.length > 0;
    serverStatus.textContent = isOn ? "서버 ON" : "서버 OFF";
    serverStatus.classList.toggle("on", isOn);
    serverStatus.classList.toggle("off", !isOn);
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

async function refresh() {
  const state = await getHostState();
  renderHostBoard(state);
  renderPublicPanels(state);
  renderLog(state);
  renderBotMetrics(state.simulation_results);
}

document.querySelector("#totalSlots").addEventListener("change", renderSlots);
document.querySelector("#saveConfig").addEventListener("click", async () => {
  await postJson("/api/config", configPayload());
  roomOpened = true;
  await refresh();
});
document.querySelector("#startGame").addEventListener("click", async () => {
  roomOpened = true;
  await postJson("/api/config", configPayload());
  try {
    await postJson("/api/start");
  } catch (error) {
    if (!error.message.includes("not all slots are filled")) {
      throw error;
    }
    stateView.textContent = "서버 ON · 플레이어 입장을 기다리는 중";
  }
  await refresh();
});
document.querySelector("#pauseGame").addEventListener("click", async () => {
  await postJson("/api/pause");
  await refresh();
});
document.querySelector("#resumeGame").addEventListener("click", async () => {
  await postJson("/api/resume");
  await refresh();
});
document.querySelector("#endHosting").addEventListener("click", async () => {
  await postJson("/api/host/end");
  roomOpened = false;
  stateView.textContent = "서버 OFF · 호스팅이 종료되었습니다";
  renderSlots();
  await refresh();
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
    const result = await postJson("/api/bot-simulation", {
      players: Number(document.querySelector("#totalSlots").value),
      total_rounds: Number(document.querySelector("#totalRounds").value),
      events_enabled: document.querySelector("#simEvents").value === "true",
      event_frequency: Number(document.querySelector("#simFrequency").value),
      seed: Number(document.querySelector("#simSeed").value),
      runs: Number(document.querySelector("#simRuns").value)
    });
    if (simulationRunning) {
      simProgress.textContent = `${result.runs}회 완료`;
      renderBotMetrics(result);
    }
  } catch (error) {
    simProgress.textContent = error.message;
  }
});
document.querySelector("#stopSimulation").addEventListener("click", () => {
  simulationRunning = false;
  simProgress.textContent = "중단 요청됨";
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
refresh();
setInterval(refresh, 1000);
