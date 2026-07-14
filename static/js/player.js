let playerId = window.localStorage.getItem("tour_player_id");
let lastState = null;
let activeInfoTab = "arrival";

const joinForm = document.querySelector("#joinForm");
const nickname = document.querySelector("#nickname");
const playerBadge = document.querySelector("#playerBadge");
const turnTitle = document.querySelector("#turnTitle");
const playerState = document.querySelector("#playerState");
const purchaseLand = document.querySelector("#purchaseLand");
const declineAction = document.querySelector("#declineAction");
const build = document.querySelector("#build");
const buildingType = document.querySelector("#buildingType");
const boardGrid = document.querySelector("#boardGrid");
const zoomCell = document.querySelector("#zoomCell");
const arrivalPanel = document.querySelector("#arrivalPanel");
const eventPanel = document.querySelector("#eventPanel");
const settlementPanel = document.querySelector("#settlementPanel");
const tradeModal = document.querySelector("#tradeModal");

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

function cellClass(cell, index, currentIndex) {
  const classes = ["board-cell", `cell-${cell?.type || "plain"}`];
  if (index === currentIndex) classes.push("current-cell");
  if (index === 0) classes.push("start-cell");
  return classes.join(" ");
}

function playerChip(player) {
  const chip = document.createElement("span");
  chip.className = `chip ${player.id === playerId ? "mine" : ""}`;
  chip.textContent = player.nickname.slice(0, 2);
  chip.title = `${player.nickname} · ${player.status}`;
  return chip;
}

function buildingSummary(state, cell) {
  const regionId = cell?.region_id;
  if (!regionId) return "";
  const buildings = state.buildings.filter((building) => building.region_id === regionId);
  if (!buildings.length) return "";
  const counts = buildings.reduce((acc, building) => {
    acc[building.building_type] = (acc[building.building_type] || 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts).map(([type, count]) => `${type.replace("_", " ")} ${count}`).join(" · ");
}

function renderBoard(state, me) {
  boardGrid.innerHTML = "";
  const currentTurnPlayer = state.players.find((player) => player.id === state.current_turn_player_id);
  const currentIndex = me ? me.position : (currentTurnPlayer?.position ?? 0);
  state.board.forEach((cell, index) => {
    const coord = boardCoord(index);
    const el = document.createElement("div");
    el.className = cellClass(cell, index, currentIndex);
    el.style.setProperty("--x", coord.x);
    el.style.setProperty("--y", coord.y);
    el.innerHTML = `
      <span class="cell-index">${index}</span>
      <strong>${cellName(cell)}</strong>
      <small>${buildingSummary(state, cell)}</small>
    `;
    const ownerId = cell.region_id && state.land_ownership[cell.region_id];
    if (ownerId) {
      el.dataset.owner = ownerId;
      el.classList.add("owned-cell");
    }
    const chips = document.createElement("div");
    chips.className = "chip-stack";
    state.players.filter((player) => player.position === index).forEach((player) => chips.append(playerChip(player)));
    el.append(chips);
    boardGrid.append(el);
  });
  const activeCell = state.board[me?.position ?? 0];
  zoomCell.innerHTML = `
    <span>현재 위치 확대</span>
    <strong>${me ? `${me.position}. ${cellName(activeCell)}` : "입장 대기"}</strong>
    <small>${activeCell?.type || ""}</small>
  `;
}

async function privateState() {
  if (!playerId) return null;
  try {
    const response = await fetch(`/api/player/${playerId}/private`, { headers: { "X-Player-Id": playerId } });
    if (!response.ok) return null;
    return response.json();
  } catch {
    return null;
  }
}

function renderMeters(state, me, privateData) {
  const wealth = state.public_wealth?.players?.find((row) => row.player_id === playerId);
  const loan = privateData?.loan?.remaining_due_won || 0;
  const taxRate = privateData?.tax_rate_bps ?? 0;
  const privatePlayer = privateData?.player || me;
  playerState.innerHTML = `
    <div class="metric emerald"><span>현금</span><strong>${money(privatePlayer?.cash_won)}원</strong></div>
    <div class="metric sapphire"><span>즉시 종료 총재산</span><strong>${money(wealth?.total_asset_won)}원</strong></div>
    <div class="metric"><span>순위</span><strong>${wealth?.rank ?? "-"}</strong></div>
    <div class="metric ruby"><span>세율</span><strong>${(taxRate / 100).toFixed(2)}%</strong></div>
    <div class="metric ruby"><span>대출</span><strong>${money(loan)}원</strong></div>
    <div class="metric"><span>라운드</span><strong>${state.global_round}</strong></div>
  `;
}

function renderInfoPanels(state, me, privateData) {
  const privatePlayer = privateData?.player || me;
  const cell = state.board[me?.position ?? 0];
  const specialId = cell?.special_region_id;
  const pending = state.pending_action && state.pending_action.player_id === playerId ? state.pending_action : null;
  const special = specialId ? `
    <div class="special-sheet">
      <span>최초 가격 ${money(state.special_values?.[specialId] || 0)}원</span>
      <span>현재 가치 ${money(state.special_values?.[specialId] || 0)}원</span>
      <span>다음 상승액은 최초 가격의 20%</span>
      <span>강제매각 84%~104%</span>
    </div>
  ` : "";
  arrivalPanel.innerHTML = `
    <h2>${cellName(cell) || "대기"}</h2>
    <p>${cell?.type || "입장 후 정보가 표시됩니다."}</p>
    <p>${buildingSummary(state, cell) || "건물 정보 없음"}</p>
    ${special}
    ${pending ? `<div class="callout sapphire">가능 행동: ${pending.type}</div>` : ""}
  `;
  const activeEvents = state.active_events || [];
  const rate = state.industrial_return_rate_bps || 0;
  eventPanel.innerHTML = `
    <h2>이벤트</h2>
    ${activeEvents.map((event) => `
      <div class="event-card">
        <strong>${event.id}</strong>
        <span>${event.age_rounds <= event.duration_rounds ? "활성 단계" : "회복 단계"}</span>
        <div class="progress"><i style="width:${Math.min(100, Math.max(0, (event.age_rounds / Math.max(1, event.duration_rounds + event.recovery_rounds)) * 100))}%"></i></div>
      </div>
    `).join("") || "<p>활성 이벤트 없음</p>"}
    <div class="gauge"><span>산업 수익률</span><i style="left:50%"></i><b style="width:${Math.min(100, (rate / 2400) * 100)}%"></b><em>${(rate / 100).toFixed(1)}%</em></div>
  `;
  const ledger = privateData?.ledger || {};
  settlementPanel.innerHTML = `
    <h2>정산</h2>
    <ol class="settlement-list">
      <li>수익 ${money(ledger.gross_income)}원</li>
      <li>손실 ${money(ledger.losses)}원</li>
      <li>세금 ${money(ledger.tax_due)}원</li>
      <li>출발지 보너스 3,000,000원</li>
      <li>대출 상환 ${money(ledger.loan_payment)}원</li>
      <li>최종 현금 ${money(privatePlayer?.cash_won)}원</li>
    </ol>
    <button class="skip-motion" type="button">건너뛰기</button>
  `;
}

function renderTradeModal(state) {
  const offer = state.land_trade_offer || state.operating_right_offer || state.usage_change_request;
  if (!offer) {
    tradeModal.hidden = true;
    return;
  }
  const isUsage = Boolean(state.usage_change_request);
  tradeModal.hidden = false;
  tradeModal.innerHTML = `
    <div class="dealer-card trade-card">
      <strong>${isUsage ? "용도 변경 승인" : "거래 요청"}</strong>
      <span>요청자 ${offer.requester_id || "-"}</span>
      <span>대상 ${offer.buyer_id || offer.target_id || offer.approvers?.join(", ") || "-"}</span>
      <span>금액 ${money(offer.price_won || offer.cost_won)}원</span>
      <span>${isUsage ? "미응답 시 자동 승인" : "미응답 시 자동 거절"}</span>
    </div>
  `;
}

function applyInfoTabs() {
  document.querySelectorAll("[data-info-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.infoTab === activeInfoTab);
  });
  arrivalPanel.classList.toggle("compact-hidden", activeInfoTab !== "arrival");
  eventPanel.classList.toggle("compact-hidden", activeInfoTab !== "events");
  settlementPanel.classList.toggle("compact-hidden", activeInfoTab !== "settlement");
}

async function refreshPlayer() {
  const state = await getState();
  lastState = state;
  const me = state.players.find((player) => player.id === playerId);
  const privateData = me ? await privateState() : null;
  if (me) {
    playerBadge.textContent = `${me.nickname} · ${me.status}`;
  } else {
    playerBadge.textContent = "입장 전";
    playerState.innerHTML = `<div class="metric sapphire"><span>게임 상태</span><strong>${state.phase}</strong></div>`;
  }
  const current = state.players.find((player) => player.id === state.current_turn_player_id);
  turnTitle.textContent = current ? `${current.nickname} 턴` : "대기 중";
  renderBoard(state, me);
  if (me) renderMeters(state, me, privateData);
  renderInfoPanels(state, me, privateData);
  renderTradeModal(state);
  applyInfoTabs();

  const pending = state.pending_action;
  purchaseLand.hidden = !(pending && pending.player_id === playerId && pending.type === "purchase_land");
  declineAction.hidden = !(pending && pending.player_id === playerId);
  build.hidden = !(pending && pending.player_id === playerId && pending.type === "build");
  buildingType.hidden = build.hidden;
}

joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const player = await postJson("/api/join", { nickname: nickname.value });
  playerId = player.id;
  window.localStorage.setItem("tour_player_id", playerId);
  await refreshPlayer();
});

document.querySelector("#rollDice").addEventListener("click", async () => {
  await postJson("/api/roll", { player_id: playerId });
  await refreshPlayer();
});

document.querySelector("#endTurn").addEventListener("click", async () => {
  await postJson("/api/end-turn", { player_id: playerId });
  await refreshPlayer();
});

purchaseLand.addEventListener("click", async () => {
  await postJson("/api/purchase-land", { player_id: playerId });
  await refreshPlayer();
});

declineAction.addEventListener("click", async () => {
  await postJson("/api/decline-action", { player_id: playerId });
  await refreshPlayer();
});

build.addEventListener("click", async () => {
  await postJson("/api/build", {
    player_id: playerId,
    building_type: buildingType.value
  });
  await refreshPlayer();
});

document.querySelectorAll("[data-info-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    activeInfoTab = button.dataset.infoTab;
    applyInfoTabs();
  });
});

window.addEventListener("orientationchange", () => {
  if (lastState) window.requestAnimationFrame(() => refreshPlayer());
});

refreshPlayer();
setInterval(refreshPlayer, 1000);
