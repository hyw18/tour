let playerId = window.localStorage.getItem("tour_player_id");
let lastState = null;
let lastPrivate = null;
let activeInfoTab = "arrival";
let selectedCellIndex = null;
let selectedBuildingId = null;
let actionInFlight = false;
let refreshInFlight = false;

const $ = (selector) => document.querySelector(selector);
const joinForm = $("#joinForm");
const nickname = $("#nickname");
const playerBadge = $("#playerBadge");
const turnTitle = $("#turnTitle");
const playerState = $("#playerState");
const purchaseLand = $("#purchaseLand");
const purchaseSpecial = $("#purchaseSpecial");
const declineAction = $("#declineAction");
const build = $("#build");
const buildingType = $("#buildingType");
const manageAction = $("#manageAction");
const tradeAction = $("#tradeAction");
const reviveAction = $("#reviveAction");
const boardGrid = $("#boardGrid");
const zoomCell = $("#zoomCell");
const arrivalPanel = $("#arrivalPanel");
const assetPanel = $("#assetPanel");
const eventPanel = $("#eventPanel");
const settlementPanel = $("#settlementPanel");
const requestPanel = $("#requestPanel");
const managementPanel = $("#managementPanel");
const tradeModal = $("#tradeModal");
const actionMessage = $("#actionMessage");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function money(value) {
  return new Intl.NumberFormat("ko-KR").format(Math.trunc(value || 0));
}

function percent(bps) {
  return `${((bps || 0) / 100).toFixed(2)}%`;
}

function typeName(type) {
  return ({
    residential: "주거",
    commercial: "상업",
    industrial: "산업",
    mixed_use: "복합"
  })[type] || type || "-";
}

function statusName(status) {
  return ({
    lobby: "대기",
    active: "게임 중",
    bankrupt: "파산·관전",
    spectator: "관전",
    exited: "자동 퇴장"
  })[status] || status || "-";
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

function playerName(state, id) {
  return state.players.find((player) => player.id === id)?.nickname || id || "-";
}

function regionName(state, regionId) {
  return state.regions?.find((region) => region.id === regionId)?.name || regionId || "-";
}

function boardCellForRegion(state, regionId) {
  return state.board.find((cell) => cell.region_id === regionId);
}

function action(name) {
  return lastPrivate?.allowed_actions?.[name] || { allowed: false, reason: "현재 사용할 수 없습니다." };
}

function configureActionButton(button, name) {
  const rule = action(name);
  button.disabled = actionInFlight || !rule.allowed;
  button.title = rule.allowed ? "" : rule.reason;
  button.dataset.disabledReason = rule.reason || "";
}

function buildingSummary(state, cell) {
  const buildings = state.buildings.filter((building) => building.region_id === cell?.region_id);
  if (!buildings.length) return "";
  const counts = buildings.reduce((acc, building) => {
    acc[building.building_type] = (acc[building.building_type] || 0) + 1;
    return acc;
  }, {});
  return Object.entries(counts).map(([type, count]) => `${typeName(type)} ${count}`).join(" · ");
}

function playerChip(player) {
  const chip = document.createElement("span");
  chip.className = `chip ${player.id === playerId ? "mine" : ""} ${player.is_bot ? "bot-chip" : ""}`;
  chip.textContent = player.nickname.slice(0, 2);
  chip.title = `${player.nickname} · ${statusName(player.status)}`;
  return chip;
}

function renderBoard(state, me) {
  boardGrid.innerHTML = "";
  const currentTurnPlayer = state.players.find((player) => player.id === state.current_turn_player_id);
  state.board.forEach((cell, index) => {
    const coord = boardCoord(index);
    const el = document.createElement("button");
    const isFocus = index === (me?.position ?? currentTurnPlayer?.position ?? 0);
    el.type = "button";
    el.className = `board-cell cell-${cell?.type || "plain"} ${isFocus ? "current-cell" : ""} ${index === 0 ? "start-cell" : ""}`;
    el.style.setProperty("--x", coord.x);
    el.style.setProperty("--y", coord.y);
    el.innerHTML = `<span class="cell-index">${index}</span><strong>${escapeHtml(cellName(cell))}</strong><small>${escapeHtml(buildingSummary(state, cell))}</small>`;
    const ownerId = cell.region_id && state.land_ownership[cell.region_id];
    if (ownerId) {
      el.dataset.owner = ownerId;
      el.classList.add("owned-cell");
      el.title = `소유자: ${playerName(state, ownerId)}`;
    }
    const chips = document.createElement("div");
    chips.className = "chip-stack";
    state.players.filter((player) => player.position === index).forEach((player) => chips.append(playerChip(player)));
    el.append(chips);
    el.addEventListener("click", () => {
      selectedCellIndex = index;
      activeInfoTab = "arrival";
      renderInfoPanels(state, me, lastPrivate);
      applyInfoTabs();
    });
    boardGrid.append(el);
  });
  const activeCell = state.board[me?.position ?? 0];
  zoomCell.innerHTML = `<span>현재 위치</span><strong>${me ? `${me.position}. ${escapeHtml(cellName(activeCell))}` : "입장 대기"}</strong><small>${escapeHtml(activeCell?.type || "")}</small>`;
}

async function privateState() {
  if (!playerId) return null;
  const response = await fetch(`/api/player/${encodeURIComponent(playerId)}/private`, {
    headers: { "X-Player-Id": playerId }
  });
  if (response.status === 403) {
    playerId = null;
    lastPrivate = null;
    window.localStorage.removeItem("tour_player_id");
    return null;
  }
  if (!response.ok) return null;
  return response.json();
}

function renderMeters(state, me, privateData) {
  const wealth = state.public_wealth?.players?.find((row) => row.player_id === playerId);
  const privatePlayer = privateData?.player || me;
  const remaining = privateData?.turn_remaining_seconds;
  const assets = privateData?.assets || { lands: [], buildings: [], special_regions: [] };
  const loan = privateData?.loan;
  const ledger = privateData?.ledger || {};
  playerState.innerHTML = `
    <div class="metric"><span>닉네임 · 상태</span><strong>${escapeHtml(privatePlayer.nickname)} · ${statusName(privatePlayer.status)}</strong></div>
    <div class="metric emerald"><span>현재 현금</span><strong>${money(privatePlayer.cash_won)}원</strong></div>
    <div class="metric sapphire"><span>즉시 종료 총재산</span><strong>${money(wealth?.total_asset_won)}원</strong></div>
    <div class="metric"><span>순위 · 위치</span><strong>${wealth?.rank ?? "-"}위 · ${privatePlayer.position}칸</strong></div>
    <div class="metric"><span>라운드 · 남은 턴</span><strong>${state.global_round} · ${remaining == null ? "무제한" : `${remaining}초`}</strong></div>
    <div class="metric"><span>보유 자산</span><strong>토지 ${assets.lands.length} · 특수 ${assets.special_regions.length} · 건물 ${assets.buildings.length}</strong></div>
    <div class="metric ruby"><span>세금 · 대출</span><strong>${money(ledger.tax_due)}원 · ${money(loan?.remaining_due_won)}원</strong></div>
  `;
}

function renderArrival(state, me, privateData) {
  const index = selectedCellIndex ?? me?.position ?? 0;
  const cell = state.board[index];
  const region = state.regions?.find((item) => item.id === cell?.region_id);
  const special = state.special_region_details?.[cell?.special_region_id];
  const ownerId = cell?.region_id ? state.land_ownership[cell.region_id] : state.special_ownership?.[cell?.special_region_id];
  const pending = privateData?.pending_action;
  const purchaseRule = privateData?.allowed_actions?.purchase_land;
  const buildRule = privateData?.allowed_actions?.build;
  const purchaseDetails = pending?.type === "purchase_land" ? `
    <div class="callout sapphire">
      <strong>토지 구매 선택</strong>
      <span>토지가 ${money(purchaseRule?.price_won)}원</span>
      <span>현재 현금 ${money(purchaseRule?.current_cash_won)}원</span>
      <span>구매 후 예상 잔액 ${money(purchaseRule?.cash_after_won)}원</span>
    </div>` : "";
  const buildDetails = pending?.type === "build" ? `
    <div class="callout sapphire">
      <strong>${pending.source === "land_purchase" ? "토지 구매 완료" : "건설 선택"}</strong>
      ${pending.source === "land_purchase" ? "<span>토지 구매는 건물 행동을 소비하지 않습니다.</span><span>이번 방문에서 건물 1채를 추가로 건설할 수 있습니다.</span>" : ""}
      ${Object.entries(buildRule?.building_options || {}).map(([type, option]) => `<span>${typeName(type)} ${money(option.price_won)}원 · 건설 후 ${money(option.cash_after_won)}원${option.reason ? ` · ${escapeHtml(option.reason)}` : ""}</span>`).join("")}
    </div>` : "";
  arrivalPanel.innerHTML = `
    <h2>${index}. ${escapeHtml(cellName(cell) || "대기")}</h2>
    <p>${escapeHtml(cell?.type || "입장 후 정보가 표시됩니다.")}</p>
    ${region ? `<div class="detail-list"><span>토지가 ${money(region.land_price)}원</span><span>소유자 ${escapeHtml(playerName(state, ownerId))}</span><span>${escapeHtml(buildingSummary(state, cell) || "건물 없음")}</span></div>` : ""}
    ${special ? `<div class="special-sheet"><span>최초 가격 ${money(special.initial_price_won)}원</span><span>현재 가치 ${money(special.current_value_won)}원</span><span>타인 방문 ${special.external_visits}회 · 다음 상승 ${money(special.next_increase_won)}원</span><span>소유자 ${escapeHtml(playerName(state, ownerId))}</span><span>강제매각 ${money(special.forced_sale_min_won)}~${money(special.forced_sale_max_won)}원</span></div>` : ""}
    ${purchaseDetails}${buildDetails}
  `;
}

function renderAssets(state, privateData) {
  const assets = privateData?.assets || { lands: [], buildings: [], special_regions: [] };
  const ledger = privateData?.ledger || {};
  const loan = privateData?.loan;
  const refunds = privateData?.pending_commercial_sale_refunds || [];
  const buildingRows = assets.buildings.map((building) => `
    <button class="asset-row" type="button" data-building-select="${escapeHtml(building.id)}">
      <strong>${escapeHtml(building.region_name)} · ${typeName(building.building_type)}</strong>
      <span>시세 ${money(building.adjusted_market_value_won)}원</span>
      <span>명목 ${escapeHtml(building.nominal_owner_name)} · 운영 ${escapeHtml(building.operator_name)}</span>
      <span>체인 ${escapeHtml(building.ownership_chain_names.join(" → "))}</span>
      <span>${escapeHtml(building.return_rate_kind)} ${percent(building.return_rate_bps)}</span>
    </button>
  `).join("") || "<p>보유 건물이 없습니다.</p>";
  assetPanel.innerHTML = `
    <h2>본인 자산현황</h2>
    <section class="asset-section"><h3>세금</h3><div class="detail-list"><span>과세소득 ${money(ledger.taxable_income)}원</span><span>세율 ${percent(privateData?.tax_rate_bps)}</span><span>${ledger.closed ? "확정" : "예상"} 세금 ${money(ledger.tax_due)}원</span></div></section>
    <section class="asset-section"><h3>대출</h3>${loan ? `<div class="detail-list"><span>원금 ${money(loan.principal_won)}원</span><span>남은 총상환액 ${money(loan.remaining_due_won)}원</span><span>이자 ${money(loan.interest_won)}원</span><span>마감까지 출발지 ${loan.due_laps_remaining}회 · 자동상환</span></div>` : "<p>대출 없음</p>"}</section>
    <section class="asset-section"><h3>일반토지 ${assets.lands.length}</h3><p>${assets.lands.map((land) => `${escapeHtml(land.name)}(${money(land.land_price_won)}원)`).join(" · ") || "없음"}</p></section>
    <section class="asset-section"><h3>특수지역 ${assets.special_regions.length}</h3><p>${assets.special_regions.map((item) => `${escapeHtml(item.name)} 최초 ${money(item.initial_price_won)} / 현재 ${money(item.current_value_won)}원`).join(" · ") || "없음"}</p></section>
    <section class="asset-section"><h3>건물 ${assets.buildings.length}</h3><div class="asset-list">${buildingRows}</div></section>
    <section class="asset-section"><h3>상업 매각 예정 환급</h3><p>${refunds.map((item) => `${escapeHtml(regionName(state, item.region_id))} ${money(item.refund_won)}원`).join(" · ") || "없음"}</p></section>
    <section class="asset-section"><h3>최근 수익·지출</h3><p>수익 ${(privateData?.recent_income || []).slice(-3).map((item) => `${escapeHtml(item.source)} ${money(item.amount_won)}`).join(" · ") || "없음"}</p><p>지출 ${(privateData?.recent_expenses || []).slice(-3).map((item) => `${escapeHtml(item.source)} ${money(item.amount_won)}`).join(" · ") || "없음"}</p></section>
  `;
  assetPanel.querySelectorAll("[data-building-select]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedBuildingId = button.dataset.buildingSelect;
      renderManagement(state, privateData, "manage");
    });
  });
}

function renderEvents(state, privateData) {
  const activeEvents = privateData?.active_events || [];
  eventPanel.innerHTML = `<h2>현재 적용 이벤트</h2>${activeEvents.map((event) => `
    <div class="event-card"><strong>${escapeHtml(event.id)}</strong><span>${event.age_rounds <= event.duration_rounds ? "활성 단계" : "회복 단계"}</span><div class="progress"><i style="width:${Math.min(100, Math.max(0, (event.age_rounds / Math.max(1, event.duration_rounds + event.recovery_rounds)) * 100))}%"></i></div></div>
  `).join("") || "<p>현재 적용 이벤트가 없습니다.</p>"}<div class="gauge"><span>산업 수익률</span><i style="left:50%"></i><b style="width:${Math.min(100, (state.industrial_return_rate_bps / 2400) * 100)}%"></b><em>${percent(state.industrial_return_rate_bps)}</em></div>${playerId ? '<button type="button" id="acknowledgeEvents">이벤트 확인</button>' : ""}`;
  $("#acknowledgeEvents")?.addEventListener("click", (event) => performAction(event.currentTarget, "/api/event/acknowledge", { player_id: playerId }));
}

function renderSettlement(state, privateData) {
  const ledger = privateData?.ledger || {};
  const settlement = privateData?.last_settlement;
  const final = state.final_results;
  settlementPanel.innerHTML = `
    <h2>${final ? "최종 정산" : "최근 출발지 정산"}</h2>
    ${settlement ? `<ol class="settlement-list"><li>수익 ${money(ledger.gross_income)}원</li><li>손실 ${money(ledger.losses)}원</li><li>세금 ${money(ledger.tax_due)}원</li><li>출발지 보너스 ${money(ledger.start_bonus)}원</li><li>대출 상환 ${money(ledger.loan_payment)}원</li><li>정산 후 현금 ${money(settlement.cash_after)}원</li></ol>` : "<p>아직 출발지 정산 기록이 없습니다.</p>"}
    ${final ? `<div class="callout sapphire">종료 사유 ${escapeHtml(final.reason)} · 내 순위 ${final.rankings?.[playerId] ?? "없음"} · 최종 자산 ${money(final.assets?.[playerId])}원</div>` : ""}
  `;
}

function requestLabel(type) {
  return ({ land_trade: "일반토지 거래", operating_right: "운영권 양도", usage_change: "용도 변경 승인" })[type] || type;
}

function requestDetails(state, offer) {
  const building = state.buildings.find((item) => item.id === offer.building_id);
  return `
    <strong>${requestLabel(offer.type)}</strong>
    <span>요청자 ${escapeHtml(offer.requester_name)}</span>
    ${offer.target_name ? `<span>상대 ${escapeHtml(offer.target_name)}</span>` : ""}
    ${offer.region_id ? `<span>지역 ${escapeHtml(regionName(state, offer.region_id))}</span>` : ""}
    ${building ? `<span>건물 ${escapeHtml(regionName(state, building.region_id))} · ${typeName(building.building_type)}</span>` : ""}
    ${offer.new_type ? `<span>변경 ${typeName(offer.new_type)}</span>` : ""}
    ${(offer.price_won ?? offer.cost_won) != null ? `<span>금액 ${money(offer.price_won ?? offer.cost_won)}원</span>` : ""}
    ${offer.current_chain ? `<span>현재 체인 ${offer.current_chain.map((id) => escapeHtml(playerName(state, id))).join(" → ")}</span><span>처리 후 ${offer.expected_chain.map((id) => escapeHtml(playerName(state, id))).join(" → ")}</span>` : ""}
    <span>남은 시간 ${offer.remaining_seconds}초 · ${offer.response_rule === "auto_approve" ? "미응답 자동 승인" : "미응답 자동 거절"}</span>
    ${offer.requester_id === playerId ? "<span>현재 서버 규칙에는 제안 취소 기능이 없어 취소할 수 없습니다.</span>" : ""}
  `;
}

function renderRequests(state, privateData) {
  const requests = privateData?.related_requests || [];
  const takeover = privateData?.pending_land_takeover;
  const takeoverHtml = takeover ? `<div class="request-card"><strong>파산 토지 인수</strong><span>지역 ${escapeHtml(regionName(state, takeover.region_id))}</span><span>필요 토지가 ${money(takeover.land_price_won)}원 · 현재 현금 ${money(takeover.current_cash_won)}원</span><span>남은 시간 ${takeover.remaining_seconds}초 · 미응답 자동 포기</span></div>` : "";
  requestPanel.innerHTML = `<h2>거래 및 승인 요청</h2>${requests.map((offer) => `<div class="request-card">${requestDetails(state, offer)}</div>`).join("")}${takeoverHtml || (!requests.length ? "<p>관련 요청이 없습니다.</p>" : "")}`;
}

function renderTradeModal(state, privateData) {
  const takeover = privateData?.pending_land_takeover;
  if (takeover) {
    tradeModal.hidden = false;
    tradeModal.innerHTML = `<div class="dealer-card trade-card"><div class="trade-description"><strong>파산 토지 인수</strong><span>지역 ${escapeHtml(regionName(state, takeover.region_id))}</span><span>필요 토지가 ${money(takeover.land_price_won)}원 · 현재 현금 ${money(takeover.current_cash_won)}원</span><span>남은 시간 ${takeover.remaining_seconds}초 · 미응답 자동 포기</span></div><div class="response-actions"><button type="button" data-takeover="accept" ${takeover.can_accept ? "" : "disabled"}>인수</button><button type="button" class="danger-action" data-takeover="reject">포기</button></div></div>`;
    tradeModal.querySelectorAll("[data-takeover]").forEach((button) => button.addEventListener("click", () => performAction(button, "/api/bankruptcy/takeover/respond", { player_id: playerId, accept: button.dataset.takeover === "accept" })));
    return;
  }
  const requests = privateData?.related_requests || [];
  const offer = requests[0];
  if (!offer) {
    tradeModal.hidden = true;
    tradeModal.innerHTML = "";
    return;
  }
  const alreadyResponded = offer.type === "usage_change" && Object.hasOwn(offer.responses || {}, playerId);
  const canRespond = offer.can_respond && !alreadyResponded;
  tradeModal.hidden = false;
  tradeModal.innerHTML = `<div class="dealer-card trade-card"><div class="trade-description">${requestDetails(state, offer)}</div>${canRespond ? `<div class="response-actions"><button type="button" data-request-response="accept">${offer.type === "usage_change" ? "승인" : "수락"}</button><button type="button" class="danger-action" data-request-response="reject">거절</button></div>` : `<span class="callout">응답 대기 중</span>`}</div>`;
  tradeModal.querySelectorAll("[data-request-response]").forEach((button) => {
    button.addEventListener("click", () => respondToRequest(offer, button.dataset.requestResponse === "accept", button));
  });
}

function renderBankruptcy(privateData) {
  const bankruptcy = privateData?.bankruptcy;
  if (!bankruptcy || !["bankrupt", "exited", "spectator"].includes(bankruptcy.status)) return "";
  const record = bankruptcy.record || {};
  return `<div class="bankruptcy-card"><strong>${statusName(bankruptcy.status)}</strong><span>사유 ${escapeHtml(record.reason || bankruptcy.reason)}</span><span>파산 라운드 ${record.bankruptcy_round ?? "-"}</span><span>${bankruptcy.spectating ? "현재 관전 상태" : ""}</span><span>${bankruptcy.can_revive ? "지금 부활 가능 · 현금 10,000,000원·출발지에서 재시작" : escapeHtml(bankruptcy.reason)}</span></div>`;
}

function renderInfoPanels(state, me, privateData) {
  renderArrival(state, me, privateData);
  renderAssets(state, privateData);
  renderEvents(state, privateData);
  renderSettlement(state, privateData);
  renderRequests(state, privateData);
  const bankruptcyHtml = renderBankruptcy(privateData);
  if (bankruptcyHtml) assetPanel.insertAdjacentHTML("afterbegin", bankruptcyHtml);
}

function renderManagement(state, privateData, mode = "manage") {
  if (!privateData) return;
  const assets = privateData.assets || { buildings: [] };
  const currentRegionId = state.board[privateData.player.position]?.region_id;
  const currentBuildings = assets.buildings.filter((item) => item.region_id === currentRegionId);
  if (!selectedBuildingId || !assets.buildings.some((item) => item.id === selectedBuildingId)) {
    selectedBuildingId = currentBuildings[0]?.id || assets.buildings[0]?.id || null;
  }
  const selected = assets.buildings.find((item) => item.id === selectedBuildingId);
  const others = state.players.filter((item) => item.id !== playerId && item.status === "active");
  const landRule = action("propose_land_trade");
  const targetOptions = others.map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.nickname)}</option>`).join("");
  const usageEntries = Object.entries(selected?.usage_change_options || {});
  const firstUsage = usageEntries.find(([, option]) => option.allowed) || usageEntries[0];
  const recall = selected?.recall_preview;
  managementPanel.hidden = false;
  managementPanel.innerHTML = `
    <div class="management-heading"><h2>${mode === "trade" ? "거래 제안" : "자산 관리"}</h2><button type="button" data-close-management>닫기</button></div>
    <label>건물 선택<select id="manageBuilding">${assets.buildings.map((item) => `<option value="${escapeHtml(item.id)}" ${item.id === selectedBuildingId ? "selected" : ""}>${escapeHtml(item.region_name)} · ${typeName(item.building_type)}</option>`).join("")}</select></label>
    ${selected ? `<div class="selected-asset"><strong>${escapeHtml(selected.region_name)} · ${typeName(selected.building_type)}</strong><span>현재 시세 ${money(selected.adjusted_market_value_won)}원 · 건설비 ${money(selected.construction_cost_won)}원</span><span>명목 ${escapeHtml(selected.nominal_owner_name)} · 최종 운영 ${escapeHtml(selected.operator_name)}</span><span>체인 ${escapeHtml(selected.ownership_chain_names.join(" → "))}</span><span>매각: ${escapeHtml(selected.sale_mode)}</span><span>즉시 ${money(selected.immediate_sale_proceeds_won)}원 · 예정 환급 ${money(selected.scheduled_refund_won)}원</span></div>` : "<p>관리할 건물이 없습니다.</p>"}
    <div class="management-actions">
      <button type="button" data-manage="sell" ${selected?.can_sell ? "" : "disabled"} title="${escapeHtml(selected?.sell_reason || "건물을 선택하세요.")}">건물 매각</button>
      <label>변경 용도<select id="usageType">${usageEntries.map(([type, option]) => `<option value="${type}" ${type === firstUsage?.[0] ? "selected" : ""}>${typeName(type)} · ${money(option.cost_won)}원${option.allowed ? "" : " (불가)"}</option>`).join("")}</select></label>
      <div id="usagePreview" class="selected-asset">${firstUsage ? `변경 비용 ${money(firstUsage[1].cost_won)}원 · 승인 후 체인 ${firstUsage[1].expected_chain.map((id) => escapeHtml(playerName(state, id))).join(" → ")}${firstUsage[1].reason ? ` · ${escapeHtml(firstUsage[1].reason)}` : ""}` : "변경할 건물을 선택하세요."}</div>
      <button type="button" data-manage="usage" ${action("request_usage_change").allowed && firstUsage?.[1].allowed ? "" : "disabled"} title="${escapeHtml(firstUsage?.[1].reason || selected?.usage_change_reason || action("request_usage_change").reason)}">용도 변경 신청</button>
      ${recall ? `<div class="selected-asset">회수 전 ${recall.current_chain.map((id) => escapeHtml(playerName(state, id))).join(" → ")}<br>회수 후 ${recall.expected_chain.map((id) => escapeHtml(playerName(state, id))).join(" → ")}<br>시세 ${money(recall.payout_won)}원 · 지급 ${escapeHtml(recall.payer_name)} → 수령 ${escapeHtml(recall.recipient_name)}</div>` : ""}
      <button type="button" data-manage="recall" ${action("recall_rights").allowed && selected?.can_recall ? "" : "disabled"} title="${escapeHtml(selected?.recall_reason || action("recall_rights").reason)}">권한 회수</button>
      <label>양도 상대<select id="rightTarget">${targetOptions}</select></label>
      <label>제안 금액<input id="rightPrice" type="number" min="0" step="50000" value="0"></label>
      <div id="rightPreview" class="selected-asset">현재 ${selected ? escapeHtml(selected.ownership_chain_names.join(" → ")) : "-"}${selected && others[0] ? ` · 양도 후 ${escapeHtml([...selected.ownership_chain_names, others[0].nickname].join(" → "))}` : ""}</div>
      <button type="button" data-manage="right" ${action("propose_operating_right").allowed && selected?.can_transfer && others.length ? "" : "disabled"} title="${escapeHtml(selected?.transfer_reason || action("propose_operating_right").reason)}">운영권 양도 제안</button>
    </div>
    <div class="land-trade-box"><h3>일반토지 거래</h3><p>고정 토지가 ${escapeHtml(regionName(state, landRule.region_id))} · 가격 ${money(state.regions?.find((item) => item.id === landRule.region_id)?.land_price)}원</p><label>상대<select id="landBuyer">${(landRule.targets || []).map((item) => `<option value="${escapeHtml(item.id)}">${escapeHtml(item.nickname)}</option>`).join("")}</select></label><button type="button" data-manage="land" ${landRule.allowed ? "" : "disabled"} title="${escapeHtml(landRule.reason)}">고정가로 거래 제안</button></div>
  `;
  $("#manageBuilding")?.addEventListener("change", (event) => {
    selectedBuildingId = event.target.value;
    renderManagement(state, privateData, mode);
  });
  $("#usageType")?.addEventListener("change", (event) => {
    const option = selected?.usage_change_options?.[event.target.value];
    const preview = $("#usagePreview");
    const button = managementPanel.querySelector('[data-manage="usage"]');
    if (!option || !preview || !button) return;
    preview.textContent = `변경 비용 ${money(option.cost_won)}원 · 승인 후 체인 ${option.expected_chain.map((id) => playerName(state, id)).join(" → ")}${option.reason ? ` · ${option.reason}` : ""}`;
    button.disabled = !action("request_usage_change").allowed || !option.allowed;
    button.title = option.reason || action("request_usage_change").reason;
  });
  $("#rightTarget")?.addEventListener("change", (event) => {
    const target = others.find((item) => item.id === event.target.value);
    if ($("#rightPreview") && selected && target) $("#rightPreview").textContent = `현재 ${selected.ownership_chain_names.join(" → ")} · 양도 후 ${[...selected.ownership_chain_names, target.nickname].join(" → ")}`;
  });
  managementPanel.querySelector("[data-close-management]").addEventListener("click", () => { managementPanel.hidden = true; });
  managementPanel.querySelectorAll("[data-manage]").forEach((button) => button.addEventListener("click", () => manageRequest(button.dataset.manage, button)));
}

function applyInfoTabs() {
  document.querySelectorAll("[data-info-tab]").forEach((button) => button.classList.toggle("active", button.dataset.infoTab === activeInfoTab));
  const panels = { arrival: arrivalPanel, assets: assetPanel, events: eventPanel, settlement: settlementPanel, requests: requestPanel };
  Object.entries(panels).forEach(([name, panel]) => panel.classList.toggle("compact-hidden", activeInfoTab !== name));
}

function renderActionState() {
  configureActionButton($("#rollDice"), "roll");
  configureActionButton($("#endTurn"), "end_turn");
  configureActionButton(purchaseLand, "purchase_land");
  configureActionButton(purchaseSpecial, "purchase_special");
  configureActionButton(declineAction, "decline_action");
  configureActionButton(build, "build");
  configureActionButton(manageAction, "manage");
  configureActionButton(tradeAction, "trade");
  configureActionButton(reviveAction, "revive");
  buildingType.disabled = actionInFlight || !action("build").allowed;
  const available = action("build").building_types || [];
  const options = action("build").building_options || {};
  Array.from(buildingType.options).forEach((option) => {
    const details = options[option.value];
    option.disabled = !available.includes(option.value);
    option.textContent = `${typeName(option.value)}${details ? ` · ${money(details.price_won)}원` : ""}`;
    option.title = details?.reason || "";
  });
  if (buildingType.selectedOptions[0]?.disabled) {
    const firstAvailable = Array.from(buildingType.options).find((option) => !option.disabled);
    if (firstAvailable) buildingType.value = firstAvailable.value;
  }
  const pendingType = lastPrivate?.pending_action?.type;
  declineAction.textContent = pendingType === "purchase_land"
    ? "토지 구매 포기"
    : pendingType === "build" ? "이번 방문 건설하지 않기" : "포기";
}

async function refreshPlayer() {
  if (refreshInFlight) return;
  refreshInFlight = true;
  try {
    const state = await getState();
    lastState = state;
    let me = state.players.find((player) => player.id === playerId);
    const privateData = me ? await privateState() : null;
    lastPrivate = privateData;
    if (!privateData && playerId === null) me = null;
    joinForm.hidden = Boolean(me);
    playerBadge.textContent = me ? `${me.nickname} · ${statusName(me.status)}` : "입장 전";
    if (!me) playerState.innerHTML = `<div class="metric sapphire"><span>게임 상태</span><strong>${escapeHtml(state.phase)}</strong></div>`;
    const current = state.players.find((player) => player.id === state.current_turn_player_id);
    turnTitle.textContent = current ? `${current.nickname} 턴` : "대기 중";
    renderBoard(state, me);
    if (me && privateData) renderMeters(state, me, privateData);
    renderInfoPanels(state, me, privateData);
    renderTradeModal(state, privateData);
    applyInfoTabs();
    renderActionState();
  } catch (error) {
    showMessage(error.message || "상태를 불러오지 못했습니다.", true);
  } finally {
    refreshInFlight = false;
  }
}

function showMessage(message, isError = false) {
  actionMessage.textContent = message || "";
  actionMessage.classList.toggle("error", isError);
}

async function performAction(button, url, body) {
  if (actionInFlight) return;
  actionInFlight = true;
  renderActionState();
  showMessage("처리 중…");
  try {
    await postJson(url, body);
    showMessage("처리되었습니다.");
  } catch (error) {
    showMessage(error.message || "요청을 처리하지 못했습니다.", true);
  } finally {
    actionInFlight = false;
    await refreshPlayer();
  }
}

async function manageRequest(kind, button) {
  if (!selectedBuildingId && kind !== "land") return;
  if (kind === "sell") return performAction(button, "/api/sell-building", { player_id: playerId, building_id: selectedBuildingId });
  if (kind === "usage") return performAction(button, "/api/usage-change/request", { requester_id: playerId, building_id: selectedBuildingId, new_type: $("#usageType").value });
  if (kind === "recall") return performAction(button, "/api/operating-right/recall", { requester_id: playerId, building_id: selectedBuildingId });
  if (kind === "right") return performAction(button, "/api/operating-right/transfer/propose", { requester_id: playerId, target_id: $("#rightTarget").value, building_id: selectedBuildingId, price_won: Number($("#rightPrice").value) });
  if (kind === "land") return performAction(button, "/api/trade/land/propose", { requester_id: playerId, buyer_id: $("#landBuyer").value, region_id: action("propose_land_trade").region_id });
}

async function respondToRequest(offer, accept, button) {
  if (offer.type === "land_trade") return performAction(button, "/api/trade/land/respond", { responder_id: playerId, accept });
  if (offer.type === "operating_right") return performAction(button, "/api/operating-right/transfer/respond", { responder_id: playerId, accept });
  return performAction(button, "/api/usage-change/respond", { approver_id: playerId, approve: accept });
}

joinForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (actionInFlight) return;
  try {
    const player = await postJson("/api/join", { nickname: nickname.value });
    playerId = player.id;
    window.localStorage.setItem("tour_player_id", playerId);
    await refreshPlayer();
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("#rollDice").addEventListener("click", (event) => performAction(event.currentTarget, "/api/roll", { player_id: playerId }));
$("#endTurn").addEventListener("click", (event) => performAction(event.currentTarget, "/api/end-turn", { player_id: playerId }));
purchaseLand.addEventListener("click", (event) => performAction(event.currentTarget, "/api/purchase-land", { player_id: playerId }));
purchaseSpecial.addEventListener("click", (event) => performAction(event.currentTarget, "/api/purchase-special", { player_id: playerId }));
declineAction.addEventListener("click", (event) => performAction(event.currentTarget, "/api/decline-action", { player_id: playerId }));
build.addEventListener("click", (event) => performAction(event.currentTarget, "/api/build", { player_id: playerId, building_type: buildingType.value }));
reviveAction.addEventListener("click", (event) => performAction(event.currentTarget, "/api/revive", { player_id: playerId }));
manageAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "manage"));
tradeAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "trade"));

document.querySelectorAll("[data-info-tab]").forEach((button) => button.addEventListener("click", () => {
  activeInfoTab = button.dataset.infoTab;
  applyInfoTabs();
}));

window.addEventListener("orientationchange", () => window.requestAnimationFrame(refreshPlayer));
window.addEventListener("pageshow", refreshPlayer);

refreshPlayer();
setInterval(refreshPlayer, 1000);
