let playerId = window.localStorage.getItem("tour_player_id");
let reconnectToken = window.localStorage.getItem("tour_reconnect_token");
let storedGameInstanceId = window.localStorage.getItem("tour_game_instance_id");
let lastState = null;
let lastPrivate = null;
let activeInfoTab = "arrival";
let selectedCellIndex = null;
let lastArrivalPosition = null;
let pendingArrivalFocus = null;
let activeFinanceTab = "assets";
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
const topbarCash = $("#topbarCash");
const mainGuide = $("#mainGuide");
const roundStatus = $("#roundStatus");
const turnTimer = $("#turnTimer");
const purchaseLand = $("#purchaseLand");
const purchaseSpecial = $("#purchaseSpecial");
const declineAction = $("#declineAction");
const build = $("#build");
const buildingType = $("#buildingType");
const manageAction = $("#manageAction");
const tradeAction = $("#tradeAction");
const reviveAction = $("#reviveAction");
const boardGrid = $("#boardGrid");
const arrivalPanel = $("#arrivalPanel");
const assetPanel = $("#assetPanel");
const eventPanel = $("#eventPanel");
const settlementPanel = $("#settlementPanel");
const requestPanel = $("#requestPanel");
const managementPanel = $("#managementPanel");
const tradeModal = $("#tradeModal");
const rankingModal = $("#rankingModal");
const financeModal = $("#financeModal");
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
let buildConfirmationOrigin = null;
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
    flushPendingArrivalFocus();
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
  if (player.id === lastState?.current_turn_player_id) chip.classList.add("current-turn-chip");
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
    const previousPosition = lastPrivate?.player?.position ?? null;
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
  const affectedRows = new Set();
  (action.asset_changes || []).forEach((change) => {
    const selectors = [];
    if (change.building_id) selectors.push(`[data-building-id="${CSS.escape(change.building_id)}"]`);
    if (change.region_id) selectors.push(`[data-region-id="${CSS.escape(change.region_id)}"]`);
    if (change.special_region_id) selectors.push(`[data-special-region-id="${CSS.escape(change.special_region_id)}"]`);
    if (change.type?.includes("loan")) selectors.push('[data-finance-section="loan"]');
    if (change.type?.includes("refund")) selectors.push(`[data-refund-region-id="${CSS.escape(change.region_id || "")}"]`);
    selectors.forEach((selector) => document.querySelectorAll(selector).forEach((row) => affectedRows.add(row)));
  });
  if ((action.cash_changes || []).some((change) => change.reason === "tax")) {
    document.querySelectorAll('[data-finance-section="tax"]').forEach((row) => affectedRows.add(row));
  }
  affectedRows.forEach((row) => {
    row.classList.add("asset-change-highlight");
    if ((action.asset_changes || []).some((change) => change.type?.includes("removed") && change.building_id === row.dataset.buildingId)) {
      row.classList.add("asset-removing");
    }
  });
  await animationController.wait(animationDuration(240, 80));
  highlighted?.classList.remove("economic-highlight");
  affectedRows.forEach((row) => row.classList.remove("asset-change-highlight", "asset-removing"));
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
      if (action.sequence != null) {
        postJson("/api/economic/acknowledge", { player_id: playerId, sequence: action.sequence }, { retryCount: 1 })
          .catch((error) => console.warn("Economic animation cursor was not acknowledged", error));
      }
    }
  });
}

function enqueuePendingEconomicActions(privateData, publicActions = []) {
  const cursor = privateData?.animation_cursor ?? privateData?.latest_economic_sequence ?? 0;
  const actionsById = new Map();
  [...(privateData?.unread_economic_actions || []), ...publicActions]
    .filter((action) => action.sequence > cursor)
    .forEach((action) => actionsById.set(action.action_id, action));
  const actions = [...actionsById.values()].sort((left, right) => left.sequence - right.sequence).slice(-30);
  if (!economicActionsInitialized) {
    economicActionsInitialized = true;
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
      el.innerHTML = '<span class="arrival-badge">도착</span><span class="cell-index"></span><strong></strong><small></small><div class="chip-stack"></div>';
      el.addEventListener("click", () => {
        selectedCellIndex = Number(el.dataset.cellIndex);
        activeInfoTab = "arrival";
        renderArrival(lastState, lastPrivate?.player, lastPrivate);
        renderBoard(lastState, lastPrivate?.player);
        applyInfoTabs();
      });
      boardGrid.append(el);
    });
  }
  state.board.forEach((cell, index) => {
    const el = boardGrid.children[index];
    const isArrival = Boolean(me && index === me.position);
    const isSelected = selectedCellIndex !== null && index === selectedCellIndex && !isArrival;
    const isTurnPosition = Boolean(currentTurnPlayer && index === currentTurnPlayer.position);
    el.className = `board-cell cell-${cell?.type || "plain"} ${isArrival ? "arrival-cell my-position-cell" : ""} ${isSelected ? "selected-cell" : ""} ${isTurnPosition ? "turn-player-cell" : ""} ${index === 0 ? "start-cell" : ""}`;
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
  const privatePlayer = privateData?.player || me;
  const remaining = privateData?.turn_remaining_seconds;
  const current = state.players.find((player) => player.id === state.current_turn_player_id);
  const isMyTurn = state.current_turn_player_id === playerId;
  topbarCash.textContent = `${money(privatePlayer.cash_won)}원`;
  roundStatus.textContent = `R${state.global_round} / ${state.config.total_rounds}`;
  turnTimer.className = "";
  if (state.paused) {
    turnTimer.textContent = "일시중지";
    turnTimer.classList.add("timer-paused");
  } else if (remaining == null) {
    turnTimer.textContent = "시간 제한 없음";
  } else {
    const seconds = Math.max(0, Math.ceil(remaining));
    turnTimer.textContent = `${seconds <= 5 ? "긴급 · " : seconds <= 10 ? "주의 · " : ""}${seconds}초`;
    if (seconds <= 5) turnTimer.classList.add("timer-critical");
    else if (seconds <= 10) turnTimer.classList.add("timer-warning");
  }
  mainGuide.textContent = isMyTurn
    ? (privateData?.pending_action ? "내 턴 · 도착 칸에서 행동을 선택하세요." : "내 턴 · 가능한 행동을 확인하세요.")
    : `${current?.nickname || "다음 플레이어"} 차례를 기다리는 중`;
}

function renderArrival(state, me, privateData) {
  const index = selectedCellIndex ?? me?.position ?? 0;
  const cell = state.board[index];
  const isActualArrival = Boolean(me && index === me.position);
  const region = state.regions?.find((item) => item.id === cell?.region_id);
  const special = state.special_region_details?.[cell?.special_region_id];
  const ownerId = cell?.region_id ? state.land_ownership[cell.region_id] : state.special_ownership?.[cell?.special_region_id];
  const recentVisitExpense = (privateData?.recent_expenses || []).slice().reverse()
    .find((item) => item.region_id === cell?.region_id && ["land_fee", "building_visit_fee"].includes(item.source));
  const pending = isActualArrival ? privateData?.pending_action : null;
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
  const cellTypeName = ({ region: "일반지역", special: "특수지역", event: "이벤트 칸", start: "출발지", transport: "교통·이동 칸" })[cell?.type] || cell?.type || "대기";
  const availableActions = isActualArrival
    ? Object.entries(privateData?.allowed_actions || {})
      .filter(([name, rule]) => rule.allowed && ["purchase_land", "purchase_special", "build", "manage", "trade", "decline_action"].includes(name))
      .map(([name]) => ({ purchase_land: "토지 구매", purchase_special: "특수지역 구매", build: "건설", manage: "관리", trade: "거래", decline_action: "포기" })[name])
      .filter(Boolean)
    : [];
  const lastSettlement = privateData?.last_settlement;
  const settlementLedger = lastSettlement?.ledger || privateData?.ledger || {};
  const typeDetails = cell?.type === "event"
    ? "<div class=\"callout sapphire\"><strong>이벤트 발생 칸</strong><span>도착 시 서버가 확정한 이벤트 카드를 공개합니다.</span></div>"
    : cell?.type === "start"
      ? `<div class="callout sapphire"><strong>출발지 정산</strong><span>산업·복합 수익 → 과세소득 → 세금 → 보너스 → 대출 상환 → 최종 현금</span>${lastSettlement ? `<span>보너스 ${money(settlementLedger.start_bonus)}원 · 세금 ${money(settlementLedger.tax_due)}원 · 대출 상환 ${money(settlementLedger.loan_payment)}원</span><span>정산 후 현금 ${money(lastSettlement.cash_after)}원</span>` : "<span>도착 후 서버 정산 결과가 여기에 표시됩니다.</span>"}</div>`
      : cell?.type === "transport"
        ? "<div class=\"callout sapphire\"><strong>교통·이동</strong><span>실제 이동 결과와 후속 행동은 서버 판정을 따릅니다.</span></div>"
        : "";
  arrivalPanel.classList.toggle("viewing-arrival", isActualArrival);
  arrivalPanel.classList.toggle("viewing-selection", !isActualArrival);
  arrivalPanel.innerHTML = `
    <span class="arrival-context">${isActualArrival ? "도착 칸" : "선택한 칸 · 행동은 실제 도착 칸 기준"}</span>
    <h2>${escapeHtml(cellName(cell) || "대기")}</h2>
    <p>${escapeHtml(cellTypeName)}</p>
    ${region ? `<div class="detail-list"><span>토지가 ${money(region.land_price)}원</span><span>소유자 ${escapeHtml(ownerId ? playerName(state, ownerId) : "없음")}</span><span>${escapeHtml(buildingSummary(state, cell) || "건물 없음")}</span><span>${recentVisitExpense ? `최근 서버 확정 방문비용 ${money(recentVisitExpense.amount_won)}원` : "방문비용·방문료는 서버의 실제 건물과 이벤트 판정 후 확정됩니다."}</span></div>` : ""}
    ${special ? `<div class="special-sheet"><span>최초 가격 ${money(special.initial_price_won)}원</span><span>현재 가치 ${money(special.current_value_won)}원</span><span>타인 방문 ${special.external_visits}회 · 다음 상승 ${money(special.next_increase_won)}원</span><span>소유자 ${escapeHtml(playerName(state, ownerId))}</span><span>강제매각 ${money(special.forced_sale_min_won)}~${money(special.forced_sale_max_won)}원</span></div>` : ""}
    ${typeDetails}${purchaseDetails}${buildDetails}
    ${isActualArrival ? `<div class="arrival-actions-summary"><strong>가능한 행동</strong><span>${escapeHtml(availableActions.join(" · ") || "즉시 선택할 행동 없음")}</span></div>` : ""}
  `;
}

function renderAssets(state, privateData) {
  const previousScroll = $("#financeScroll")?.scrollTop || 0;
  const assets = privateData?.assets || { lands: [], buildings: [], special_regions: [] };
  const ledger = privateData?.ledger || {};
  const loan = privateData?.loan;
  const refunds = privateData?.pending_commercial_sale_refunds || [];
  const buildingRows = assets.buildings.map((building) => `
    <button class="asset-row" type="button" data-building-select="${escapeHtml(building.id)}" data-building-id="${escapeHtml(building.id)}" data-region-id="${escapeHtml(building.region_id)}">
      <strong>${escapeHtml(building.region_name)} · ${typeName(building.building_type)}</strong>
      <span>시세 ${money(building.adjusted_market_value_won)}원</span>
      <span>명목 ${escapeHtml(building.nominal_owner_name)} · 운영 ${escapeHtml(building.operator_name)}</span>
      <span>체인 ${escapeHtml(building.ownership_chain_names.join(" → "))}</span>
      <span>${escapeHtml(building.return_rate_kind)} ${percent(building.return_rate_bps)}</span>
    </button>
  `).join("") || "<p>보유 건물이 없습니다.</p>";
  assetPanel.innerHTML = `
    <h2>본인 자산현황</h2>
    <section class="asset-section" data-finance-pane="tax" data-finance-section="tax"><h3>세금</h3><div class="detail-list"><span>과세소득 ${money(ledger.taxable_income)}원</span><span>세율 ${percent(privateData?.tax_rate_bps)}</span><span>${ledger.closed ? "확정" : "예상"} 세금 ${money(ledger.tax_due)}원</span></div></section>
    <section class="asset-section" data-finance-pane="loan" data-finance-section="loan"><h3>대출</h3>${loan ? `<div class="detail-list"><span>원금 ${money(loan.principal_won)}원</span><span>남은 총상환액 ${money(loan.remaining_due_won)}원</span><span>이자 ${money(loan.interest_won)}원</span><span>마감까지 출발지 ${loan.due_laps_remaining}회 · 자동상환</span></div>` : "<p>대출 없음</p>"}</section>
    <section class="asset-section" data-finance-pane="assets"><h3>일반토지 ${assets.lands.length}</h3><div class="asset-list">${assets.lands.map((land) => `<div class="asset-row" data-region-id="${escapeHtml(land.region_id)}">${escapeHtml(land.name)} (${money(land.land_price_won)}원)</div>`).join("") || "없음"}</div></section>
    <section class="asset-section" data-finance-pane="assets"><h3>특수지역 ${assets.special_regions.length}</h3><div class="asset-list">${assets.special_regions.map((item) => `<div class="asset-row" data-special-region-id="${escapeHtml(item.special_region_id)}">${escapeHtml(item.name)} 최초 ${money(item.initial_price_won)} / 현재 ${money(item.current_value_won)}원</div>`).join("") || "없음"}</div></section>
    <section class="asset-section" data-finance-pane="assets"><h3>건물·운영권 ${assets.buildings.length}</h3><div class="asset-list">${buildingRows}</div></section>
    <section class="asset-section" data-finance-pane="history"><h3>상업 매각 예정 환급</h3><div class="asset-list">${refunds.map((item) => `<div class="asset-row" data-refund-region-id="${escapeHtml(item.region_id)}">${escapeHtml(regionName(state, item.region_id))} ${money(item.refund_won)}원</div>`).join("") || "없음"}</div></section>
    <section class="asset-section" data-finance-pane="history"><h3>최근 수익·지출</h3><p>수익 ${(privateData?.recent_income || []).slice(-3).map((item) => `R${item.round ?? "-"} · ${escapeHtml(item.region_id ? `${regionName(state, item.region_id)} ` : "")}${escapeHtml(item.display_name || item.source)} +${money(item.amount_won)}원${item.counterparty_player_id ? ` · ${escapeHtml(playerName(state, item.counterparty_player_id))}` : ""}`).join("<br>") || "없음"}</p><p>지출 ${(privateData?.recent_expenses || []).slice(-3).map((item) => `R${item.round ?? "-"} · ${escapeHtml(item.region_id ? `${regionName(state, item.region_id)} ` : "")}${escapeHtml(item.display_name || item.source)} -${money(item.amount_won)}원${item.counterparty_player_id ? ` · ${escapeHtml(playerName(state, item.counterparty_player_id))}` : ""}`).join("<br>") || "없음"}</p></section>
  `;
  applyFinanceTab();
  if ($("#financeScroll")) $("#financeScroll").scrollTop = previousScroll;
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
    <div class="event-card"><strong>${escapeHtml(event.title)}</strong><span>${escapeHtml(scopeName(event.scope))} · ${escapeHtml(event.target_name)}</span><span>${escapeHtml(({ growing: "확대", peak: "최대", recovering: "회복", completed: "종료" })[event.phase] || event.phase)} · ${event.rounds_remaining}라운드 남음</span><span>${escapeHtml((event.current_effect_summary || []).join(" · "))}</span><small>최대 ${escapeHtml((event.maximum_effect_summary || []).join(" · "))}</small><div class="progress"><i style="width:${Math.min(100, Math.max(0, event.phase_progress_bps / 100))}%"></i></div></div>
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
  const recentStatuses = (privateData?.recent_domain_events || []).slice(-3).reverse();
  const statusNames = {
    land_trade_proposed: "토지 거래 제안 전송", land_trade_accepted: "토지 거래 성립", land_trade_rejected: "토지 거래 거절", land_trade_expired: "토지 거래 만료",
    operating_right_proposed: "운영권 양도 제안 전송", operating_right_accepted: "운영권 거래 성립", operating_right_rejected: "운영권 거래 거절", operating_right_expired: "운영권 거래 만료",
    usage_change_requested: "용도 변경 신청", usage_change_approved: "용도 변경 승인", usage_change_rejected: "용도 변경 거절", rights_recalled: "권한 회수 완료"
  };
  const takeover = privateData?.pending_land_takeover;
  const takeoverHtml = takeover ? `<div class="request-card"><strong>파산 토지 인수</strong><span>지역 ${escapeHtml(regionName(state, takeover.region_id))}</span><span>필요 토지가 ${money(takeover.land_price_won)}원 · 현재 현금 ${money(takeover.current_cash_won)}원</span><span>남은 시간 ${takeover.remaining_seconds}초 · 미응답 자동 포기</span></div>` : "";
  requestPanel.innerHTML = `<h2>거래 및 승인 요청</h2>${requests.map((offer) => `<div class="request-card">${requestDetails(state, offer)}</div>`).join("")}${takeoverHtml || (!requests.length ? "<p>관련 요청이 없습니다.</p>" : "")}<h3>최근 요청 상태</h3>${recentStatuses.map((event) => `<p>R${event.round} · ${escapeHtml(statusNames[event.event_type] || event.event_type)}</p>`).join("") || "<p>최근 상태 변경 없음</p>"}`;
}

function renderTradeModal(state, privateData) {
  const takeover = privateData?.pending_land_takeover;
  if (takeover) {
    tradeModal.hidden = false;
    tradeModal.innerHTML = `<div class="dealer-card trade-card"><div class="trade-description"><strong>파산 토지 인수</strong><span>지역 ${escapeHtml(regionName(state, takeover.region_id))}</span><span>필요 토지가 ${money(takeover.land_price_won)}원 · 현재 현금 ${money(takeover.current_cash_won)}원</span><span>남은 시간 ${takeover.remaining_seconds}초 · 미응답 자동 포기</span></div><div class="response-actions"><button type="button" data-takeover="accept" ${takeover.can_accept ? "" : "disabled"}>인수</button><button type="button" class="danger-action" data-takeover="reject">포기</button></div></div>`;
    tradeModal.querySelectorAll("[data-takeover]").forEach((button) => button.addEventListener("click", () => {
      const accept = button.dataset.takeover === "accept";
      if (!accept) return performAction(button, "/api/bankruptcy/takeover/respond", { player_id: playerId, accept });
      return confirmedRequest(button, "/api/bankruptcy/takeover/respond", { player_id: playerId, accept }, {
        title: "파산 토지를 인수할까요?", target: regionName(state, takeover.region_id), amount: takeover.land_price_won,
        cashAfter: takeover.current_cash_won - takeover.land_price_won, change: "토지와 관련 건물의 명목 소유권을 인수합니다.", strong: true, reversible: false, confirmLabel: "토지 인수 확정"
      });
    }));
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
  return `<div class="bankruptcy-card" data-finance-pane="assets"><strong>파산·부활 정보</strong><span>사유 ${escapeHtml(record.reason || bankruptcy.reason)}</span><span>파산 라운드 ${record.bankruptcy_round ?? "-"}</span><span>${bankruptcy.spectating ? "현재 관전 상태" : ""}</span><span>${bankruptcy.can_revive ? "지금 부활 가능 · 현금 10,000,000원·출발지에서 재시작" : escapeHtml(bankruptcy.reason)}</span></div>`;
}

function renderInfoPanels(state, me, privateData) {
  renderArrival(state, me, privateData);
  renderAssets(state, privateData);
  renderEvents(state, privateData);
  renderSettlement(state, privateData);
  renderRequests(state, privateData);
  const bankruptcyHtml = renderBankruptcy(privateData);
  if (bankruptcyHtml) assetPanel.insertAdjacentHTML("afterbegin", bankruptcyHtml);
  applyFinanceTab();
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

let rankingDialogOrigin = null;
let financeDialogOrigin = null;

function renderRankings(state) {
  const list = $("#rankingList");
  const rankedRows = $("#rankedPlayerRows");
  const unrankedRows = $("#unrankedPlayerRows");
  const unrankedGroup = $("#unrankedPlayers");
  const rows = state.public_wealth?.players || [];
  const activeIds = new Set(rows.map((row) => row.player_id));
  list.querySelectorAll("[data-ranking-player-id]").forEach((element) => {
    if (!activeIds.has(element.dataset.rankingPlayerId)) element.remove();
  });
  rows.forEach((row) => {
    const player = state.players.find((item) => item.id === row.player_id) || {};
    let element = list.querySelector(`[data-ranking-player-id="${CSS.escape(row.player_id)}"]`);
    if (!element) {
      element = document.createElement("div");
      element.className = "ranking-row";
      element.dataset.rankingPlayerId = row.player_id;
    }
    const rowContainer = row.rank == null ? unrankedRows : rankedRows;
    if (element.parentElement !== rowContainer) rowContainer.append(element);
    const nextRank = row.rank == null ? "순위 없음" : `${row.rank}위`;
    if (element.dataset.rank && element.dataset.rank !== String(row.rank)) {
      element.classList.add("rank-changed");
      window.setTimeout(() => element.classList.remove("rank-changed"), 600);
    }
    element.dataset.rank = String(row.rank);
    element.classList.toggle("ranking-exited", row.status === "exited");
    element.innerHTML = `
      <strong>${escapeHtml(nextRank)}</strong>
      <span>${escapeHtml(row.nickname)}${player.is_bot ? " · BOT" : ""}</span>
      <span>${escapeHtml(statusName(row.status))}</span>
      <span>공개 자산 ${money(row.total_asset_won)}원</span>
      <span>토지 ${(player.lands || []).length}</span>
      <span>${state.current_turn_player_id === row.player_id ? "● 현재 턴" : ""}</span>`;
  });
  unrankedGroup.hidden = !rows.some((row) => row.rank == null);
}

function applyFinanceTab() {
  document.querySelectorAll("[data-finance-tab]").forEach((button) => button.classList.toggle("active", button.dataset.financeTab === activeFinanceTab));
  document.querySelectorAll("[data-finance-pane]").forEach((pane) => { pane.hidden = pane.dataset.financePane !== activeFinanceTab; });
}

function openPanelDialog(modal, origin) {
  if (modal === rankingModal) rankingDialogOrigin = origin;
  if (modal === financeModal) financeDialogOrigin = origin;
  modal.hidden = false;
  window.requestAnimationFrame(() => modal.querySelector("button")?.focus());
}

function closePanelDialog(modal) {
  modal.hidden = true;
  if (modal === rankingModal) { rankingDialogOrigin?.focus(); rankingDialogOrigin = null; }
  if (modal === financeModal) { financeDialogOrigin?.focus(); financeDialogOrigin = null; }
}

function applyInfoTabs() {
  document.querySelectorAll("[data-info-tab]").forEach((button) => button.classList.toggle("active", button.dataset.infoTab === activeInfoTab));
  const panels = { arrival: arrivalPanel, events: eventPanel, requests: requestPanel };
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
      || privateData?.player?.status === "bankrupt"
      || (lastPrivate && !privateData)
    );
    if (lastState && state.game_instance_id !== lastState.game_instance_id) {
      lastArrivalPosition = null;
      selectedCellIndex = null;
      pendingArrivalFocus = null;
    }
    if (criticalChange) {
      animationController.cancel();
      pendingSnapshot = null;
      queuedOccurrenceIds.clear();
      queuedEconomicActionIds.clear();
      economicActionsInitialized = false;
      buildConfirmModal.hidden = true;
      activeBuildPreview = null;
      rankingModal.hidden = true;
      financeModal.hidden = true;
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
    playerBadge.innerHTML = authenticatedMe
      ? `<strong>${escapeHtml(authenticatedMe.nickname)}</strong><span>${escapeHtml(statusName(authenticatedMe.status))}</span>`
      : "<strong>입장 전</strong><span>대기</span>";
    const current = state.players.find((player) => player.id === state.current_turn_player_id);
    turnTitle.textContent = current ? (current.id === playerId ? "내 턴" : `${current.nickname} 턴`) : "대기 중";
    if (!authenticatedMe) {
      topbarCash.textContent = "—";
      roundStatus.textContent = `R${state.global_round} / ${state.config.total_rounds}`;
      turnTimer.textContent = "입장 후 표시";
      mainGuide.textContent = "게임 입장을 기다리고 있습니다.";
    }
    renderBoard(state, authenticatedMe);
    if (authenticatedMe) renderMeters(state, authenticatedMe, privateData);
    renderInfoPanels(state, authenticatedMe, privateData);
    renderRankings(state);
    renderTradeModal(state, privateData);
    applyInfoTabs();
    renderActionState();
    renderedStateVersion = state.state_version;
    pendingSnapshot = null;
    enqueuePendingEvents(privateData);
    enqueuePendingEconomicActions(privateData, state.public_economic_actions || []);
    if (authenticatedMe) {
      if (lastArrivalPosition === null) {
        lastArrivalPosition = authenticatedMe.position;
        if (selectedCellIndex === null) selectedCellIndex = authenticatedMe.position;
      } else if (authenticatedMe.position !== lastArrivalPosition) {
        lastArrivalPosition = authenticatedMe.position;
        focusArrivalInformation(authenticatedMe.position);
      }
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      if (animationState.playing) animationController.cancel();
      actionInFlight = false;
      hideAnimationOverlay();
      renderActionState();
      showMessage(error.message || "서버 연결이 끊겼습니다. 다시 연결하는 중입니다.", true);
    }
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

function arrivalFocusBlocked() {
  return !financeModal.hidden || !rankingModal.hidden || !tradeModal.hidden
    || !buildConfirmModal.hidden || !$("#actionConfirmModal").hidden || !eventReveal.hidden;
}

function focusArrivalInformation(position, animate = true) {
  pendingArrivalFocus = position;
  if (arrivalFocusBlocked() || !lastState || !lastPrivate) return;
  selectedCellIndex = position;
  activeInfoTab = "arrival";
  renderBoard(lastState, lastPrivate.player);
  renderArrival(lastState, lastPrivate.player, lastPrivate);
  applyInfoTabs();
  arrivalPanel.classList.toggle("arrival-card-emphasis", animate && selectedAnimationMode() !== "minimal");
  document.querySelectorAll(".command-zone button:not([disabled])").forEach((button) => {
    button.classList.toggle("arrival-action-emphasis", animate && selectedAnimationMode() !== "minimal");
  });
  window.setTimeout(() => arrivalPanel.classList.remove("arrival-card-emphasis"), 600);
  window.setTimeout(() => document.querySelectorAll(".arrival-action-emphasis").forEach((button) => button.classList.remove("arrival-action-emphasis")), 600);
  arrivalPanel.scrollIntoView({ block: "nearest", behavior: selectedAnimationMode() === "minimal" ? "auto" : "smooth" });
  pendingArrivalFocus = null;
}

function flushPendingArrivalFocus() {
  if (pendingArrivalFocus !== null) focusArrivalInformation(pendingArrivalFocus);
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

let confirmationOrigin = null;
let pendingConfirmedAction = null;

function confirmationFocusables(modal) {
  return [...modal.querySelectorAll('button:not([disabled]), select:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])')];
}

function trapConfirmationFocus(event, modal) {
  if (event.key !== "Tab" || modal.hidden) return;
  const focusables = confirmationFocusables(modal);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

function closeActionConfirmation() {
  if (actionInFlight) return;
  $("#actionConfirmModal").hidden = true;
  pendingConfirmedAction = null;
  confirmationOrigin?.focus();
  confirmationOrigin = null;
  flushPendingArrivalFocus();
}

function confirmBeforeAction(origin, config, callback) {
  if (actionInFlight || animationState.playing) return;
  confirmationOrigin = origin || document.activeElement;
  pendingConfirmedAction = callback;
  const modal = $("#actionConfirmModal");
  modal.classList.toggle("strong-confirm", Boolean(config.strong));
  $("#actionConfirmTitle").textContent = config.title;
  $("#actionConfirmDetails").innerHTML = `
    <dl class="confirm-details">
      <dt>행동 대상</dt><dd>${escapeHtml(config.target || "현재 대상")}</dd>
      <dt>지급·수령 금액</dt><dd>${config.amount == null ? "금액 이동 없음" : `${money(config.amount)}원`}</dd>
      <dt>현재 현금</dt><dd>${money(lastPrivate?.player?.cash_won)}원</dd>
      <dt>처리 후 예상 현금</dt><dd>${config.cashAfter == null ? "상대 응답·서버 판정 후 확정" : `${money(config.cashAfter)}원`}</dd>
      <dt>권리 변경</dt><dd>${escapeHtml(config.change || "서버 결과에 따라 반영")}</dd>
      <dt>되돌리기</dt><dd>${config.reversible ? "후속 행동으로 변경 가능" : "처리 후 즉시 되돌릴 수 없음"}</dd>
      <dt>세금·수익 영향</dt><dd>${escapeHtml(config.impact || "서버 공식 규칙에 따라 반영")}</dd>
      <dt>서버 상태 버전</dt><dd>${lastPrivate?.state_version ?? "-"}</dd>
    </dl>`;
  $("#actionConfirmError").textContent = "";
  $("#confirmAction").textContent = config.confirmLabel || "확정";
  modal.hidden = false;
  window.requestAnimationFrame(() => $("#cancelActionConfirm").focus());
}

async function runConfirmedAction() {
  if (!pendingConfirmedAction || actionInFlight) return;
  const callback = pendingConfirmedAction;
  $("#actionConfirmModal").hidden = true;
  pendingConfirmedAction = null;
  try { await callback(); }
  finally {
    confirmationOrigin?.focus();
    confirmationOrigin = null;
  }
}

function confirmedRequest(button, url, body, config) {
  const confirmedStateVersion = lastPrivate?.state_version;
  confirmBeforeAction(button, config, () => performAction(button, url, {
    ...body,
    expected_state_version: confirmedStateVersion
  }));
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
  buildConfirmationOrigin = build;
  buildConfirmModal.hidden = false;
  $("#buildConfirmDetails").innerHTML = "<p>최신 건설 조건을 확인하는 중…</p>";
  $("#buildConfirmError").textContent = "";
  $("#confirmBuild").disabled = true;
  try {
    renderBuildConfirmation(await loadBuildPreview(selectedType));
    window.requestAnimationFrame(() => $("#cancelBuildConfirm").focus());
  } catch (error) {
    $("#buildConfirmError").textContent = error.message;
  }
}

function closeBuildConfirmation() {
  if (actionInFlight) return;
  buildConfirmModal.hidden = true;
  activeBuildPreview = null;
  buildConfirmationOrigin?.focus();
  buildConfirmationOrigin = null;
  flushPendingArrivalFocus();
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
    if (buildConfirmModal.hidden) {
      buildConfirmationOrigin?.focus();
      buildConfirmationOrigin = null;
    }
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
  const selected = lastPrivate?.assets?.buildings?.find((item) => item.id === selectedBuildingId);
  if (kind === "sell") return confirmedRequest(button, "/api/sell-building", { player_id: playerId, building_id: selectedBuildingId }, {
    title: "건물을 매각할까요?", target: `${selected?.region_name} ${typeName(selected?.building_type)}`,
    amount: selected?.immediate_sale_proceeds_won, cashAfter: (lastPrivate?.player?.cash_won || 0) + (selected?.immediate_sale_proceeds_won || 0),
    change: "건물 소유권과 보드 아이콘이 제거됩니다.", impact: selected?.sale_mode, strong: true, reversible: false, confirmLabel: "건물 매각 확정"
  });
  if (kind === "usage") {
    const newType = $("#usageType").value;
    const option = selected?.usage_change_options?.[newType];
    return confirmedRequest(button, "/api/usage-change/request", { requester_id: playerId, building_id: selectedBuildingId, new_type: newType }, {
      title: "용도 변경을 신청할까요?", target: `${selected?.region_name} · ${typeName(selected?.building_type)} → ${typeName(newType)}`,
      amount: option?.cost_won, cashAfter: (lastPrivate?.player?.cash_won || 0) - (option?.cost_won || 0), change: "승인 완료 시 건물 유형과 운영 체인이 변경됩니다.", reversible: false
    });
  }
  if (kind === "recall") return confirmedRequest(button, "/api/operating-right/recall", { requester_id: playerId, building_id: selectedBuildingId }, {
    title: "운영권을 회수할까요?", target: `${selected?.region_name} ${typeName(selected?.building_type)}`, amount: selected?.recall_preview?.payout_won,
    cashAfter: null, change: `${selected?.recall_preview?.payer_name} → ${selected?.recall_preview?.recipient_name} 지급 후 하위 체인 제거`, strong: true, reversible: false
  });
  if (kind === "right") {
    const price = Number($("#rightPrice").value);
    return confirmedRequest(button, "/api/operating-right/transfer/propose", { requester_id: playerId, target_id: $("#rightTarget").value, building_id: selectedBuildingId, price_won: price }, {
      title: "운영권 양도를 제안할까요?", target: `${selected?.region_name} · ${typeName(selected?.building_type)}`, amount: price,
      cashAfter: null, change: "상대가 수락하면 운영 체인 끝에 상대가 추가됩니다.", strong: true, reversible: false, confirmLabel: "양도 제안 전송"
    });
  }
  if (kind === "land") {
    const regionId = action("propose_land_trade").region_id;
    const price = lastState.regions?.find((item) => item.id === regionId)?.land_price;
    return confirmedRequest(button, "/api/trade/land/propose", { requester_id: playerId, buyer_id: $("#landBuyer").value, region_id: regionId }, {
      title: "토지 거래를 제안할까요?", target: regionName(lastState, regionId), amount: price, cashAfter: null,
      change: "상대가 수락하면 토지 소유권이 이전됩니다.", reversible: false, confirmLabel: "거래 제안 전송"
    });
  }
}

async function respondToRequest(offer, accept, button) {
  const url = offer.type === "land_trade" ? "/api/trade/land/respond" : offer.type === "operating_right" ? "/api/operating-right/transfer/respond" : "/api/usage-change/respond";
  const body = offer.type === "usage_change" ? { approver_id: playerId, approve: accept } : { responder_id: playerId, accept };
  if (!accept) return performAction(button, url, body);
  return confirmedRequest(button, url, body, {
    title: `${requestLabel(offer.type)}를 ${offer.type === "usage_change" ? "승인" : "수락"}할까요?`,
    target: offer.region_id ? regionName(lastState, offer.region_id) : requestLabel(offer.type), amount: offer.price_won ?? offer.cost_won,
    cashAfter: offer.type === "usage_change" ? null : (lastPrivate?.player?.cash_won || 0) - (offer.price_won || 0),
    change: offer.expected_chain ? offer.expected_chain.map((id) => playerName(lastState, id)).join(" → ") : "수락 즉시 권리가 변경됩니다.", reversible: false
  });
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
purchaseLand.addEventListener("click", (event) => {
  const rule = action("purchase_land");
  confirmedRequest(event.currentTarget, "/api/purchase-land", { player_id: playerId }, { title: "일반토지를 구매할까요?", target: regionName(lastState, rule.region_id), amount: rule.price_won, cashAfter: rule.cash_after_won, change: "토지 소유자로 등록됩니다.", reversible: false, confirmLabel: "토지 구매 확정" });
});
purchaseSpecial.addEventListener("click", (event) => {
  const pending = lastPrivate?.pending_action || {};
  confirmedRequest(event.currentTarget, "/api/purchase-special", { player_id: playerId }, { title: "특수지역을 구매할까요?", target: pending.special_region_id, amount: pending.price_won, cashAfter: (lastPrivate?.player?.cash_won || 0) - (pending.price_won || 0), change: "특수지역 소유자로 등록됩니다.", reversible: false, confirmLabel: "특수지역 구매 확정" });
});
declineAction.addEventListener("click", (event) => performAction(event.currentTarget, "/api/decline-action", { player_id: playerId }));
build.addEventListener("click", openBuildConfirmation);
$("#cancelBuildConfirm").addEventListener("click", closeBuildConfirmation);
$("#confirmBuild").addEventListener("click", confirmBuildAction);
buildConfirmModal.addEventListener("click", (event) => {
  if (event.target === buildConfirmModal) closeBuildConfirmation();
});
reviveAction.addEventListener("click", (event) => confirmedRequest(event.currentTarget, "/api/revive", { player_id: playerId }, {
  title: "플레이어로 부활할까요?", target: "현재 관전 캐릭터", amount: 0, cashAfter: 10_000_000,
  change: "출발지에서 현금 10,000,000원으로 게임에 복귀합니다.", reversible: false, confirmLabel: "부활 확정"
}));
$("#cancelActionConfirm").addEventListener("click", closeActionConfirmation);
$("#confirmAction").addEventListener("click", runConfirmedAction);
$("#actionConfirmModal").addEventListener("click", (event) => {
  if (event.target === $("#actionConfirmModal")) closeActionConfirmation();
});
manageAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "manage"));
tradeAction.addEventListener("click", () => renderManagement(lastState, lastPrivate, "trade"));

document.querySelectorAll("[data-info-tab]").forEach((button) => button.addEventListener("click", () => {
  activeInfoTab = button.dataset.infoTab;
  applyInfoTabs();
}));
$("#openRankings").addEventListener("click", (event) => openPanelDialog(rankingModal, event.currentTarget));
$("#closeRankings").addEventListener("click", () => { closePanelDialog(rankingModal); flushPendingArrivalFocus(); });
$("#openFinance").addEventListener("click", (event) => {
  applyFinanceTab();
  openPanelDialog(financeModal, event.currentTarget);
});
$("#closeFinance").addEventListener("click", () => { closePanelDialog(financeModal); flushPendingArrivalFocus(); });
document.querySelectorAll("[data-finance-tab]").forEach((button) => button.addEventListener("click", () => {
  activeFinanceTab = button.dataset.financeTab;
  applyFinanceTab();
}));
[rankingModal, financeModal].forEach((modal) => modal.addEventListener("click", (event) => {
  if (event.target === modal) { closePanelDialog(modal); flushPendingArrivalFocus(); }
}));

animationPreference.value = window.localStorage.getItem("tour_animation_preference") || "full";
animationPreference.addEventListener("change", () => {
  window.localStorage.setItem("tour_animation_preference", animationPreference.value);
});
$("#skipAnimation").addEventListener("click", () => animationController.skip());
$("#skipEventReveal").addEventListener("click", () => {
  animationController.skip();
  eventReveal.classList.add("is-revealed");
});
$("#skipEconomicAnimation").addEventListener("click", () => animationController.skip());

document.addEventListener("keydown", (event) => {
  if (!buildConfirmModal.hidden) {
    trapConfirmationFocus(event, buildConfirmModal);
    if (event.key === "Escape") closeBuildConfirmation();
  } else if (!$("#actionConfirmModal").hidden) {
    trapConfirmationFocus(event, $("#actionConfirmModal"));
    if (event.key === "Escape") closeActionConfirmation();
  } else if (!financeModal.hidden) {
    trapConfirmationFocus(event, financeModal);
    if (event.key === "Escape") { closePanelDialog(financeModal); flushPendingArrivalFocus(); }
  } else if (!rankingModal.hidden) {
    trapConfirmationFocus(event, rankingModal);
    if (event.key === "Escape") { closePanelDialog(rankingModal); flushPendingArrivalFocus(); }
  }
});
window.addEventListener("popstate", () => {
  if (!buildConfirmModal.hidden) closeBuildConfirmation();
  if (!$("#actionConfirmModal").hidden) closeActionConfirmation();
  if (!financeModal.hidden) closePanelDialog(financeModal);
  if (!rankingModal.hidden) closePanelDialog(rankingModal);
  flushPendingArrivalFocus();
});

window.addEventListener("orientationchange", () => window.requestAnimationFrame(() => scheduleRefresh(true)));
window.addEventListener("pageshow", () => scheduleRefresh(true));
document.addEventListener("visibilitychange", () => {
  if (document.hidden) animationController.skip();
  scheduleRefresh(!document.hidden);
});

scheduleRefresh(true);
