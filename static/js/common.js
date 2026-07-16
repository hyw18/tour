function idempotencyKey() {
  if (window.crypto && window.crypto.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random()}`;
}

async function postJson(url, body) {
  const csrfToken = window.hostCsrfToken || sessionStorage.getItem("hostCsrfToken");
  const gameInstanceId = window.currentGameInstanceId || window.localStorage.getItem("tour_game_instance_id");
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": idempotencyKey(),
      ...(gameInstanceId ? { "X-Game-Instance-Id": gameInstanceId } : {}),
      ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {})
    },
    body: JSON.stringify(body || {})
  });
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
