let playerId = window.localStorage.getItem("tour_player_id");
let reconnectToken = window.localStorage.getItem("tour_reconnect_token");
let storedGameInstanceId = window.localStorage.getItem("tour_game_instance_id");
let lastState = null;
let lastPrivate = null;
let activeInfoTab = "arrival";
let selectedCellIndex = null;
let selectedBuildingId = null;
let actionInFlight = false;
let refreshInFlight = false;
let refreshController = null;
let refreshTimer = null;
let renderedStateVersion = -1;
let refreshSequence = 0;
let pendingSnapshot = null;
let observedRollActionId = null;
const queuedOccurrenceIds = new Set();
const animationState = {
  type: null,
  sequenceId: null,
  playing: false,
  skippable: true,
  startedAt: null
};

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
const animationOverlay = $("#animationOverlay");
const diceStage = $("#diceStage");
const diceFace = $("#diceFace");
const diceResultText = $("#diceResultText");
const eventReveal = $("#eventReveal");
const economicStage = $("#economicStage");
const animationPreference = $("#animationPreference");
const buildConfirmModal = $("#buildConfirmModal");
let activeBuildPreview = null;
let economicActionsInitialized = false;
const queuedEconomicActionIds = new Set();

class AnimationSequenceController {
  constructor() {
    this.queue = [];
    this.processing = false;
    this.skipRequested = false;
    this.cancelled = false;
    this.currentCancel = null;
  }

  enqueue(type, sequenceId, task) {
    return new Promise((resolve) => {
      this.queue.push({ type, sequenceId, task, resolve });
      this.drain();
    });
  }

  async drain() {
    if (this.processing) return;
    this.processing = true;
    while (this.queue.length) {
      const item = this.queue.shift();
      this.skipRequested = false;
      this.cancelled = false;
      Object.assign(animationState, {
        type: item.type,
        sequenceId: item.sequenceId,
        playing: true,
        startedAt: Date.now()
      });
      renderActionState();
      try {
        await item.task();
      } catch (error) {
        if (error.name !== "AnimationCancelled") console.error("Animation sequence failed", error);
      } finally {
        item.resolve();
      }
    }
    Object.assign(animationState, { type: null, sequenceId: null, playing: false, startedAt: null });
    this.processing = false;
    hideAnimationOverlay();
    renderActionState();
    renderedStateVersion = -1;
    scheduleRefresh(true);
  }

  skip() {
    this.skipRequested = true;
  }

  cancel() {
    this.cancelled = true;
    this.skipRequested = true;
    if (this.currentCancel) this.currentCancel();
    this.currentCancel = null;
    this.queue.splice(0).forEach((item) => item.resolve());
    hideAnimationOverlay();
  }

  async wait(milliseconds) {
    if (milliseconds <= 0 || this.skipRequested) return;
    const started = performance.now();
    await new Promise((resolve, reject) => {
      const frame = (now) => {
        if (this.cancelled) {
          const error = new Error("animation cancelled");
          error.name = "AnimationCancelled";
          reject(error);
          return;
        }
        if (this.skipRequested || document.hidden || now - started >= milliseconds) {
          resolve();
          return;
        }
        window.requestAnimationFrame(frame);
      };
      window.requestAnimationFrame(frame);
    });
  }
}

const animationController = new AnimationSequenceController();

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
  button.disabled = actionInFlight || animationState.playing || !rule.allowed;
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
  const icons = { residential: "⌂", commercial: "▥", industrial: "⚙", mixed_use: "⌂▥" };
  return Object.entries(counts).map(([type, count]) => `${icons[type] || "◆"} ${typeName(type)} ${count}`).join(" · ");
}

function playerChip(player) {
  const chip = document.createElement("span");
  chip.className = `chip ${player.id === playerId ? "mine" : ""} ${player.is_bot ? "bot-chip" : ""}`;
  chip.dataset.playerId = player.id;
  chip.textContent = player.nickname.slice(0, 2);
  chip.title = `${player.nickname} · ${statusName(player.status)}`;
  return chip;
}

function selectedAnimationMode() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return "minimal";
  return animationPreference?.value || "full";
}

function animationDuration(full, fast) {
  const mode = selectedAnimationMode();
  if (mode === "minimal") return 0;
  return mode === "fast" ? fast : full;
}

function showAnimationStage(stage) {
  animationOverlay.hidden = false;
  diceStage.hidden = stage !== diceStage;
  eventReveal.hidden = stage !== eventReveal;
  economicStage.hidden = stage !== economicStage;
}

function hideAnimationOverlay() {
  animationOverlay.hidden = true;
  diceStage.hidden = true;
  eventReveal.hidden = true;
  economicStage.hidden = true;
  diceFace.classList.remove("is-rolling", "is-result");
  eventReveal.classList.remove("is-revealed");
  document.querySelectorAll(".piece-moving-cell,.arrival-highlight")
    .forEach((cell) => cell.classList.remove("piece-moving-cell", "arrival-highlight"));
}

function setDiceFace(value, text) {
  diceFace.dataset.face = String(value);
  diceResultText.textContent = text || `주사위 결과 ${value}`;
}

async function playDiceAnimation(result) {
  showAnimationStage(diceStage);
  diceFace.classList.add("is-rolling");
  diceResultText.textContent = "주사위를 굴리는 중…";
  const rollingTime = animationDuration(700, 280);
  const started = performance.now();
  while (!animationController.skipRequested && performance.now() - started < rollingTime) {
    setDiceFace(1 + Math.floor(Math.random() * 6), "주사위를 굴리는 중…");
    await animationController.wait(70);
  }
  diceFace.classList.remove("is-rolling");
  setDiceFace(result.dice, `주사위 결과 ${result.dice}`);
  diceFace.classList.add("is-result");
  await animationController.wait(animationDuration(300, 100));
}

function moveChipTo(playerIdToMove, position) {
  const cell = boardGrid.querySelector(`[data-cell-index="${position}"]`);
  if (!cell) return;
  let chip = [...boardGrid.querySelectorAll(".chip")].find((item) => item.dataset.playerId === playerIdToMove);
  if (!chip) {
    const player = lastState?.players?.find((item) => item.id === playerIdToMove);
    if (player) chip = playerChip(player);
  }
  if (chip) cell.querySelector(".chip-stack")?.append(chip);
}

async function playMovementAnimation(result) {
  const path = Array.isArray(result.movement_path) ? result.movement_path : [];
  if (!path.length || selectedAnimationMode() === "minimal" || animationController.skipRequested) {
    moveChipTo(result.player_id, result.to_position);
  } else {
    const stepTime = path.length <= 3 ? 160 : 120;
    const cappedStepTime = Math.min(stepTime, Math.floor(1500 / path.length));
    for (const position of path) {
      if (animationController.skipRequested) break;
      document.querySelectorAll(".piece-moving-cell").forEach((cell) => cell.classList.remove("piece-moving-cell"));
      moveChipTo(result.player_id, position);
      boardGrid.querySelector(`[data-cell-index="${position}"]`)?.classList.add("piece-moving-cell");
      await animationController.wait(cappedStepTime);
    }
    moveChipTo(result.player_id, result.to_position);
  }
  document.querySelectorAll(".piece-moving-cell").forEach((cell) => cell.classList.remove("piece-moving-cell"));
  const arrival = boardGrid.querySelector(`[data-cell-index="${result.to_position}"]`);
  arrival?.classList.add("arrival-highlight");
  await animationController.wait(animationDuration(260, 80));
  arrival?.classList.remove("arrival-highlight");
}

async function playDiceSequence(result) {
  try {
    await playDiceAnimation(result);
    await playMovementAnimation(result);
  } finally {
    setDiceFace(result.dice, `주사위 결과 ${result.dice}`);
    moveChipTo(result.player_id, result.to_position);
  }
}

function scopeName(scope) {
  return ({ personal: "개인", regional: "지역", nationwide: "전국" })[scope] || scope;
}

function rememberedOccurrences() {
  const key = `tour_seen_event_occurrences_${storedGameInstanceId || "none"}`;
  try {
    return { key, values: new Set(JSON.parse(window.localStorage.getItem(key) || "[]")) };
  } catch (_error) {
    return { key, values: new Set() };
  }
}

function rememberOccurrence(occurrenceId) {
  const remembered = rememberedOccurrences();
  remembered.values.add(occurrenceId);
  window.localStorage.setItem(remembered.key, JSON.stringify([...remembered.values].slice(-200)));
}

function fillEventCard(occurrence) {
  $("#eventRevealScope").textContent = `${scopeName(occurrence.scope)} 이벤트 · R${occurrence.triggered_round}`;
  $("#eventRevealTitle").textContent = occurrence.title;
  $("#eventRevealDescription").textContent = occurrence.description || occurrence.public_description;
  $("#eventRevealDetails").innerHTML = `
    <dt>적용 대상</dt><dd>${escapeHtml(occurrence.target_name)}</dd>
    <dt>최대 효과</dt><dd>${escapeHtml((occurrence.maximum_effect_summary || occurrence.effect_summary || []).join(" · "))}</dd>
    <dt>지속</dt><dd>${occurrence.duration_rounds}라운드</dd>
    <dt>회복</dt><dd>${occurrence.recovery_rounds}라운드</dd>`;
  $("#eventRevealEffects").innerHTML = (occurrence.effect_summary || [])
    .map((effect) => `<li>${escapeHtml(effect)}</li>`).join("");
}

async function revealEventOccurrence(occurrence) {
  showAnimationStage(eventReveal);
  fillEventCard(occurrence);
  eventReveal.classList.remove("is-revealed");
  await animationController.wait(animationDuration(320, 100));
  eventReveal.classList.add("is-revealed");
  await animationController.wait(animationDuration(480, 120));
  await new Promise((resolve) => {
    const confirm = $("#confirmEvent");
    const cancel = () => {
      confirm.removeEventListener("click", handler);
      resolve();
    };
    const handler = async () => {
      confirm.disabled = true;
      try {
        await postJson("/api/event/acknowledge", {
          player_id: playerId,
          occurrence_id: occurrence.occurrence_id,
          last_seen_event_version: lastState.event_version
        });
        rememberOccurrence(occurrence.occurrence_id);
        confirm.removeEventListener("click", handler);
        animationController.currentCancel = null;
        resolve();
      } catch (error) {
        showMessage(error.message || "이벤트 확인에 실패했습니다.", true);
        confirm.disabled = false;
      }
    };
    confirm.disabled = false;
    confirm.addEventListener("click", handler);
    animationController.currentCancel = cancel;
  });
  eventReveal.classList.remove("is-revealed");
}

function enqueuePendingEvents(privateData) {
  const remembered = rememberedOccurrences().values;
  (privateData?.pending_event_occurrences || []).forEach((occurrence) => {
    if (remembered.has(occurrence.occurrence_id) || queuedOccurrenceIds.has(occurrence.occurrence_id)) return;
    queuedOccurrenceIds.add(occurrence.occurrence_id);
    animationController.enqueue("event", occurrence.occurrence_id, async () => {
      await revealEventOccurrence(occurrence);
      queuedOccurrenceIds.delete(occurrence.occurrence_id);
    });
  });
}

const economicReasonNames = {
  land_purchase: "토지 구매비", special_region_purchase: "특수지역 구매비",
  building_construction: "건설비", building_sale: "건물 매각",
  land_fee: "일반 토지 방문비용", building_visit_fee: "건물 방문료",
  lap_building_return: "산업·복합 바퀴 수익", lap_building_loss: "산업·복합 바퀴 손실",
  tax: "세금 납부", start_bonus: "출발지 보너스 · 비과세",
  commercial_sale_refund: "상업 매각 예정 환급", loan_repayment: "대출 자동상환",
  usage_change: "용도 변경 비용", operating_right_trade: "운영권 거래대금",
  land_trade: "토지 거래대금", operating_right_recall: "권한 회수 대금",
  event_cash_change: "이벤트 현금 변화"
};

function economicSeenStore() {
  const key = `tour_seen_economic_actions_${storedGameInstanceId || "none"}`;
  try {
    return { key, values: new Set(JSON.parse(window.localStorage.getItem(key) || "[]")) };
  } catch (_error) {
    return { key, values: new Set() };
  }
}

function rememberEconomicAction(actionId) {
  const store = economicSeenStore();
  store.values.add(actionId);
  window.localStorage.setItem(store.key, JSON.stringify([...store.values].slice(-300)));
}

async function animateCashCounter(element, fromValue, toValue) {
  if (!element || selectedAnimationMode() === "minimal" || animationController.skipRequested) {
    if (element) element.textContent = `${money(toValue)}원`;
    return;
  }
  const duration = animationDuration(480, 220);
  const started = performance.now();
  while (!animationController.skipRequested) {
    const progress = Math.min(1, (performance.now() - started) / duration);
    const eased = 1 - ((1 - progress) ** 3);
    element.textContent = `${money(Math.round(fromValue + ((toValue - fromValue) * eased)))}원`;
    if (progress >= 1) break;
    await animationController.wait(16);
  }
  element.textContent = `${money(toValue)}원`;
}

function economicIconFor(action) {
  const building = action.building_type || action.asset_changes?.find((item) => item.building_type)?.building_type;
  if (building) return ({ residential: "⌂", commercial: "▥", industrial: "⚙", mixed_use: "⌂▥" })[building] || "◆";
  if (action.action_type.includes("sale")) return "⇄";
  if (action.action_type.includes("purchase")) return "✓";
  return "₩";
}

async function playEconomicAction(action) {
  showAnimationStage(economicStage);
  $("#economicIcon").textContent = economicIconFor(action);
  const regionId = action.region_id || action.asset_changes?.find((item) => item.region_id)?.region_id;
  const regionCell = regionId ? boardCellForRegion(lastState, regionId) : null;
  const regionIndex = regionCell ? lastState.board.indexOf(regionCell) : -1;
  const highlighted = regionIndex >= 0 ? boardGrid.querySelector(`[data-cell-index="${regionIndex}"]`) : null;
  highlighted?.classList.add("economic-highlight");
  const changes = Array.isArray(action.cash_changes) ? action.cash_changes : [];
  const payers = changes.filter((item) => item.amount_won < 0).map((item) => playerName(lastState, item.player_id));
  const recipients = changes.filter((item) => item.amount_won > 0).map((item) => playerName(lastState, item.player_id));
  $("#economicTransfer").textContent = payers.length && recipients.length ? `${payers.join(", ")} → ${recipients.join(", ")}` : "";
  for (const change of changes) {
    if (animationController.skipRequested) break;
    $("#economicAmount").textContent = `${change.amount_won > 0 ? "+" : ""}${money(change.amount_won)}원`;
    $("#economicAmount").className = change.amount_won >= 0 ? "income" : "expense";
    $("#economicReason").textContent = `${playerName(lastState, change.player_id)} · ${economicReasonNames[change.reason] || change.reason}`;
    if (change.player_id === playerId) {
      await animateCashCounter($("[data-current-cash]"), change.cash_before_won, change.cash_after_won);
    } else {
      await animationController.wait(animationDuration(520, 230));
    }
  }
  if (!changes.length) {
    $("#economicAmount").textContent = action.action_type.includes("sale") ? "매각 완료" : "변경 완료";
    $("#economicReason").textContent = economicReasonNames[action.action_type] || action.action_type;
    await animationController.wait(animationDuration(600, 250));
  }
  document.querySelectorAll(".asset-row").forEach((row) => row.classList.add("asset-change-highlight"));
  await animationController.wait(animationDuration(240, 80));
  highlighted?.classList.remove("economic-highlight");
  document.querySelectorAll(".asset-change-highlight").forEach((row) => row.classList.remove("asset-change-highlight"));
}

function enqueueEconomicAction(action) {
  if (!action?.action_id || queuedEconomicActionIds.has(action.action_id) || economicSeenStore().values.has(action.action_id)) return Promise.resolve();
  if (action.game_instance_id !== storedGameInstanceId) return Promise.resolve();
  queuedEconomicActionIds.add(action.action_id);
  return animationController.enqueue("economic", action.action_id, async () => {
    try { await playEconomicAction(action); }
    finally {
      rememberEconomicAction(action.action_id);
      queuedEconomicActionIds.delete(action.action_id);
    }
  });
}

function enqueuePendingEconomicActions(privateData) {
  const actions = privateData?.economic_actions || [];
  if (!economicActionsInitialized) {
    actions.forEach((action) => rememberEconomicAction(action.action_id));
    economicActionsInitialized = true;
    return;
  }
  actions.forEach(enqueueEconomicAction);
}

function renderBoard(state, me) {
  const currentTurnPlayer = state.players.find((player) => player.id === state.current_turn_player_id);
  if (boardGrid.children.length !== state.board.length) {
    boardGrid.replaceChildren();
    state.board.forEach((cell, index) => {
      const coord = boardCoord(index);
      const el = document.createElement("button");
      el.type = "button";
      el.dataset.cellIndex = String(index);
      el.style.setProperty("--x", coord.x);
      el.style.setProperty("--y", coord.y);
      el.innerHTML = '<span class="cell-index"></span><strong></strong><small></small><div class="chip-stack"></div>';
      el.addEventListener("click", () => {
        selectedCellIndex = Number(el.dataset.cellIndex);
        activeInfoTab = "arrival";
        renderInfoPanels(lastState, lastPrivate?.player, lastPrivate);
        applyInfoTabs();
      });
      boardGrid.append(el);
    });
  }
  state.board.forEach((cell, index) => {
    const el = boardGrid.children[index];
    const isFocus = index === (me?.position ?? currentTurnPlayer?.position ?? 0);
    el.className = `board-cell cell-${cell?.type || "plain"} ${isFocus ? "current-cell" : ""} ${index === 0 ? "start-cell" : ""}`;
    el.querySelector(".cell-index").textContent = String(index);
    el.querySelector("strong").textContent = cellName(cell);
    el.querySelector("small").textContent = buildingSummary(state, cell);
    delete el.dataset.owner;
    el.title = "";
    const ownerId = cell.region_id && state.land_ownership[cell.region_id];
    if (ownerId) {
      el.dataset.owner = ownerId;
      el.classList.add("owned-cell");
      el.title = `소유자: ${playerName(state, ownerId)}`;
    }
    const chips = el.querySelector(".chip-stack");
    chips.replaceChildren();
    state.players.filter((player) => player.position === index).forEach((player) => chips.append(playerChip(player)));
  });
  const activeCell = state.board[me?.position ?? 0];
  zoomCell.innerHTML = `<span>현재 위치</span><strong>${me ? `${me.position}. ${escapeHtml(cellName(activeCell))}` : "입장 대기"}</strong><small>${escapeHtml(activeCell?.type || "")}</small>`;
}

async function reconnectPlayer(signal) {
  if (!playerId || !reconnectToken || !storedGameInstanceId) return false;
  const response = await fetch("/api/player/reconnect", {
    method: "POST",
    signal,
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey(),
      "X-Game-Instance-Id": storedGameInstanceId
    },
    body: JSON.stringify({
      player_id: playerId,
      reconnect_token: reconnectToken,
      game_instance_id: storedGameInstanceId
    })
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    showMessage(
      response.status === 409
        ? "이전 게임이 종료되었습니다. 새 게임에 다시 입장하세요."
        : (data.error || "기존 캐릭터로 재접속할 수 없습니다."),
      true
    );
    return false;
  }
  return true;
}

async function getPlayerSnapshot(signal) {
  const response = await fetch(`/api/player/${encodeURIComponent(playerId)}/state`, {
    signal,
    headers: { "X-Player-Id": playerId }
  });
  if (response.status === 403 && await reconnectPlayer(signal)) {
    return getPlayerSnapshot(signal);
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
    <div class="metric emerald"><span>현재 현금</span><strong data-current-cash>${money(privatePlayer.cash_won)}원</strong></div>
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
  `).join("") || "<p>현재 적용 이벤트가 없습니다.</p>"}<div class="gauge"><span>산업 수익률</span><i style="left:50%"></i><b style="width:${Math.min(100, (state.industrial_return_rate_bps / 2400) * 100)}%"></b><em>${percent(state.industrial_return_rate_bps)}</em></div>`;
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
  buildingType.disabled = actionInFlight || animationState.playing || !action("build").allowed;
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
  const sequence = ++refreshSequence;
  refreshController = new AbortController();
  try {
    let state;
    let privateData = null;
    if (playerId) {
      const snapshot = await getPlayerSnapshot(refreshController.signal);
      if (snapshot) {
        state = snapshot.public;
        privateData = snapshot.private;
        if (state.state_version !== privateData.state_version || state.state_version !== snapshot.state_version) return;
      }
    }
    if (!state) state = await getState();
    if (sequence !== refreshSequence || state.state_version < renderedStateVersion) return;
    const criticalChange = lastState && (
      state.game_instance_id !== lastState.game_instance_id
      || state.ended
      || privateData?.player?.status === "exited"
    );
    if (criticalChange) {
      animationController.cancel();
      pendingSnapshot = null;
      queuedOccurrenceIds.clear();
      queuedEconomicActionIds.clear();
      economicActionsInitialized = false;
      buildConfirmModal.hidden = true;
      activeBuildPreview = null;
    } else if (animationState.playing) {
      pendingSnapshot = { public: state, private: privateData, state_version: state.state_version };
      return;
    }
    const incomingRoll = state.last_roll;
    if (observedRollActionId === null) {
      observedRollActionId = incomingRoll?.action_id || null;
    } else if (incomingRoll?.action_id && incomingRoll.action_id !== observedRollActionId && lastState) {
      observedRollActionId = incomingRoll.action_id;
      pendingSnapshot = { public: state, private: privateData, state_version: state.state_version };
      animationController.enqueue("dice", incomingRoll.action_id, () => playDiceSequence(incomingRoll));
      return;
    }
    const me = state.players.find((player) => player.id === playerId);
    const authenticatedMe = privateData ? me : null;
    if (state.state_version === renderedStateVersion) return;
    lastState = state;
    lastPrivate = privateData;
    joinForm.hidden = Boolean(authenticatedMe);
    playerBadge.textContent = authenticatedMe ? `${authenticatedMe.nickname} · ${statusName(authenticatedMe.status)}` : "입장 전";
    if (!authenticatedMe) playerState.innerHTML = `<div class="metric sapphire"><span>게임 상태</span><strong>${escapeHtml(state.phase)}</strong></div>`;
    const current = state.players.find((player) => player.id === state.current_turn_player_id);
    turnTitle.textContent = current ? `${current.nickname} 턴` : "대기 중";
    renderBoard(state, authenticatedMe);
    if (authenticatedMe) renderMeters(state, authenticatedMe, privateData);
    renderInfoPanels(state, authenticatedMe, privateData);
    renderTradeModal(state, privateData);
    applyInfoTabs();
    renderActionState();
    renderedStateVersion = state.state_version;
    pendingSnapshot = null;
    enqueuePendingEvents(privateData);
    enqueuePendingEconomicActions(privateData);
  } catch (error) {
    if (error.name !== "AbortError") showMessage(error.message || "상태를 불러오지 못했습니다.", true);
  } finally {
    refreshInFlight = false;
    refreshController = null;
  }
}

function pollingDelay() {
  if (document.hidden) return 5000;
  if (!lastState || ["setup", "lobby", "finished"].includes(lastState.phase)) return 4000;
  const waiting = lastPrivate?.pending_action || (lastPrivate?.related_requests || []).length;
  return lastState.current_turn_player_id === playerId || waiting ? 750 : 2000;
}

function scheduleRefresh(immediate = false) {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer);
  if (immediate && refreshController) refreshController.abort();
  refreshTimer = window.setTimeout(async () => {
    await refreshPlayer();
    scheduleRefresh();
  }, immediate ? 0 : pollingDelay());
}

function showMessage(message, isError = false) {
  actionMessage.textContent = message || "";
  actionMessage.classList.toggle("error", isError);
}

async function performAction(button, url, body) {
  if (actionInFlight || animationState.playing) return;
  actionInFlight = true;
  renderActionState();
  showMessage("처리 중…");
  try {
    const result = await postJson(url, body);
    if (result.economic_action) await enqueueEconomicAction(result.economic_action);
    showMessage("처리되었습니다.");
  } catch (error) {
    showMessage(error.message || "요청을 처리하지 못했습니다.", true);
  } finally {
    actionInFlight = false;
    await refreshPlayer();
  }
}

async function loadBuildPreview(selectedType) {
  const regionId = lastPrivate?.pending_action?.region_id;
  if (!regionId) throw new Error("현재 건설할 지역이 없습니다.");
  const response = await fetch(`/api/player/${encodeURIComponent(playerId)}/build-preview?region_id=${encodeURIComponent(regionId)}&building_type=${encodeURIComponent(selectedType)}`, {
    headers: { "X-Player-Id": playerId }
  });
  const preview = await response.json();
  if (!response.ok) throw new Error(preview.error || "건설 조건을 확인하지 못했습니다.");
  return preview;
}

function renderBuildConfirmation(preview) {
  activeBuildPreview = preview;
  $("#buildConfirmTitle").textContent = `${preview.region_name}에 ${preview.building_type_name} 건물을 건설할까요?`;
  $("#buildConfirmDetails").innerHTML = `
    <dl class="confirm-details">
      <dt>지역</dt><dd>${escapeHtml(preview.region_name)}</dd>
      <dt>건물 유형</dt><dd>${escapeHtml(preview.building_type_name)}</dd>
      <dt>토지 소유</dt><dd>${preview.land_owned ? "본인 소유" : "소유하지 않음"}</dd>
      <dt>건설비</dt><dd>${money(preview.price_won)}원</dd>
      <dt>현재 현금</dt><dd>${money(preview.current_cash_won)}원</dd>
      <dt>건설 후 예상 현금</dt><dd>${money(preview.cash_after_won)}원</dd>
      <dt>주요 수익</dt><dd>${escapeHtml(preview.income_description)}</dd>
      <dt>기본 세율 영향</dt><dd>+${preview.tax_base_add_bps / 100}%p</dd>
      <dt>동일 유형</dt><dd>${preview.same_type_count}채${preview.limit == null ? "" : ` / 최대 ${preview.limit}채`}</dd>
      <dt>매각 규칙</dt><dd>${escapeHtml(preview.sale_description)}</dd>
    </dl>
    <p class="confirm-warning">성공하면 이번 방문의 건물 편집 기회를 사용하며 추가 건물 행동을 할 수 없습니다.</p>`;
  $("#buildConfirmError").textContent = preview.reason || "";
  const confirm = $("#confirmBuild");
  confirm.textContent = `${preview.building_type_name} 건설 확정`;
  confirm.disabled = !preview.allowed;
}

async function openBuildConfirmation() {
  if (actionInFlight || animationState.playing || !action("build").allowed) return;
  const selectedType = buildingType.value;
  buildConfirmModal.hidden = false;
  $("#buildConfirmDetails").innerHTML = "<p>최신 건설 조건을 확인하는 중…</p>";
  $("#buildConfirmError").textContent = "";
  $("#confirmBuild").disabled = true;
  try {
    renderBuildConfirmation(await loadBuildPreview(selectedType));
  } catch (error) {
    $("#buildConfirmError").textContent = error.message;
  }
}

function closeBuildConfirmation() {
  if (actionInFlight) return;
  buildConfirmModal.hidden = true;
  activeBuildPreview = null;
}

async function confirmBuildAction() {
  const preview = activeBuildPreview;
  if (!preview || actionInFlight) return;
  actionInFlight = true;
  $("#confirmBuild").disabled = true;
  $("#cancelBuildConfirm").disabled = true;
  $("#confirmBuild").textContent = "건설 처리 중…";
  renderActionState();
  try {
    const result = await postJson("/api/build", {
      player_id: playerId,
      game_instance_id: preview.game_instance_id,
      state_version: preview.state_version,
      region_id: preview.region_id,
      building_type: preview.building_type,
      preview_price_won: preview.price_won
    });
    buildConfirmModal.hidden = true;
    activeBuildPreview = null;
    if (result.economic_action) await enqueueEconomicAction(result.economic_action);
    showMessage(`${preview.region_name} ${preview.building_type_name} 건설이 완료되었습니다.`);
  } catch (error) {
    $("#buildConfirmError").textContent = error.message || "건설 요청에 실패했습니다.";
    try { renderBuildConfirmation(await loadBuildPreview(preview.building_type)); }
    catch (refreshError) { $("#buildConfirmError").textContent = `${error.message} ${refreshError.message}`; }
  } finally {
    actionInFlight = false;
    $("#cancelBuildConfirm").disabled = false;
    renderActionState();
    await refreshPlayer();
  }
}

async function performRoll(button) {
  if (actionInFlight || animationState.playing) return;
  actionInFlight = true;
  renderActionState();
  showAnimationStage(diceStage);
  diceFace.classList.add("is-rolling");
  diceResultText.textContent = "서버에서 주사위 결과를 확인하는 중…";
  showMessage("주사위를 굴리는 중…");
  try {
    const result = await postJson("/api/roll", { player_id: playerId });
    observedRollActionId = result.action_id;
    await animationController.enqueue("dice", result.action_id, () => playDiceSequence(result));
    if (result.economic_action) await enqueueEconomicAction(result.economic_action);
    showMessage(`주사위 결과 ${result.dice}`);
  } catch (error) {
    hideAnimationOverlay();
    showMessage(error.message || "주사위를 굴리지 못했습니다.", true);
  } finally {
    actionInFlight = false;
    renderedStateVersion = -1;
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
    window.localStorage.removeItem("tour_player_id");
    window.localStorage.removeItem("tour_reconnect_token");
    window.localStorage.removeItem("tour_game_instance_id");
    window.currentGameInstanceId = null;
    const player = await postJson("/api/join", { nickname: nickname.value });
    playerId = player.id;
    reconnectToken = player.reconnect_token;
    storedGameInstanceId = player.game_instance_id;
    window.localStorage.setItem("tour_player_id", playerId);
    window.localStorage.setItem("tour_reconnect_token", reconnectToken);
    window.localStorage.setItem("tour_game_instance_id", storedGameInstanceId);
    window.currentGameInstanceId = storedGameInstanceId;
    renderedStateVersion = -1;
    await refreshPlayer();
  } catch (error) {
    showMessage(error.message, true);
  }
});

$("#rollDice").addEventListener("click", (event) => performRoll(event.currentTarget));
$("#endTurn").addEventListener("click", (event) => performAction(event.currentTarget, "/api/end-turn", { player_id: playerId }));
purchaseLand.addEventListener("click", (event) => performAction(event.currentTarget, "/api/purchase-land", { player_id: playerId }));
purchaseSpecial.addEventListener("click", (event) => performAction(event.currentTarget, "/api/purchase-special", { player_id: playerId }));
declineAction.addEventListener("click", (event) => performAction(event.currentTarget, "/api/decline-action", { player_id: playerId }));
build.addEventListener("click", openBuildConfirmation);
$("#cancelBuildConfirm").addEventListener("click", closeBuildConfirmation);
$("#confirmBuild").addEventListener("click", confirmBuildAction);
buildConfirmModal.addEventListener("click", (event) => {
  if (event.target === buildConfirmModal) closeBuildConfirmation();
});
reviveAction.addEventListener("click", (event) => performAction(event.currentTarget, "/api/revive", { player_id: playerId }));
manageAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "manage"));
tradeAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "trade"));

document.querySelectorAll("[data-info-tab]").forEach((button) => button.addEventListener("click", () => {
  activeInfoTab = button.dataset.infoTab;
  applyInfoTabs();
}));

animationPreference.value = window.localStorage.getItem("tour_animation_preference") || "full";
animationPreference.addEventListener("change", () => {
  window.localStorage.setItem("tour_animation_preference", animationPreference.value);
});
$("#animationMuted").checked = window.localStorage.getItem("tour_animation_muted") !== "false";
$("#animationMuted").addEventListener("change", (event) => {
  window.localStorage.setItem("tour_animation_muted", String(event.target.checked));
});
$("#skipAnimation").addEventListener("click", () => animationController.skip());
$("#skipEventReveal").addEventListener("click", () => {
  animationController.skip();
  eventReveal.classList.add("is-revealed");
});
$("#skipEconomicAnimation").addEventListener("click", () => animationController.skip());

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !buildConfirmModal.hidden) closeBuildConfirmation();
});
window.addEventListener("popstate", () => {
  if (!buildConfirmModal.hidden) closeBuildConfirmation();
});

window.addEventListener("orientationchange", () => window.requestAnimationFrame(() => scheduleRefresh(true)));
window.addEventListener("pageshow", () => scheduleRefresh(true));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) animationController.skip();
  scheduleRefresh(!document.hidden);
});

scheduleRefresh(true);
