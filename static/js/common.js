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
  const requestOptions = {
      method: "POST",
      signal: options.signal,
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": logicalKey,
        ...(gameInstanceId ? { "X-Game-Instance-Id": gameInstanceId } : {}),
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
      },
      body: JSON.stringify(body || {})
  };
  let response;
  for (let attempt = 0; attempt <= retryCount; attempt += 1) {
    try {
      response = await fetch(url, requestOptions);
      break;
    } catch (error) {
      if (attempt >= retryCount || error.name === "AbortError") throw error;
    }
  }
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "request failed");
    error.status = response.status;
    throw error;
  }
  return data;
}

async function getState() {
  const response = await fetch("/api/state");
  return response.json();
}
