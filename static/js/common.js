function idempotencyKey() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random()}`;
}

async function postJson(url, body, options = {}) {
  const csrfToken = window.hostCsrfToken || sessionStorage.getItem("hostCsrfToken");
  const gameInstanceId = window.currentGameInstanceId || window.localStorage.getItem("tour_game_instance_id");
  const logicalKey = options.idempotencyKey || idempotencyKey();
  const retryCount = Math.max(0, Math.min(3, Number(options.retryCount ?? 1)));
  const timeoutMs = Number(options.timeoutMs ?? 10000);
  const timeoutController = !options.signal && timeoutMs > 0 ? new AbortController() : null;
  const timeoutId = timeoutController ? window.setTimeout(() => timeoutController.abort(), timeoutMs) : null;
  const requestOptions = {
      method: "POST",
      signal: options.signal || timeoutController?.signal,
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": logicalKey,
        ...(gameInstanceId ? { "X-Game-Instance-Id": gameInstanceId } : {}),
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
      },
      body: JSON.stringify(body || {})
  };
  let response;
  try {
    for (let attempt = 0; attempt <= retryCount; attempt += 1) {
      try {
        response = await fetch(url, requestOptions);
        break;
      } catch (error) {
        if (attempt >= retryCount || error.name === "AbortError") throw error;
      }
    }
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.user_message || data.error || "요청을 처리하지 못했습니다.");
    error.status = response.status;
    error.code = data.error_code;
    throw error;
  }
  return data;
}

async function getState() {
  const response = await fetch("/api/state");
  return response.json();
}
