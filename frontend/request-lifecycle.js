/* SPDX-License-Identifier: AGPL-3.0-only */
// A browser deadline stops waiting, not server execution. Never automatically
// retry a potentially billable POST. Shared by the pages and API client.
globalThis.belayRequestError = function (code, uncertain = false, message) {
  const error = new Error(message || globalThis.belayControlMessage({ code }));
  error.code = code;
  error.uncertain = uncertain;
  error.belayRequest = true;
  return error;
};

globalThis.belayValidateTurn = function (data) {
  const strings = (value) => Array.isArray(value) && value.every((item) => typeof item === "string");
  if (!data || Array.isArray(data) || typeof data.message !== "string" || !data.message.trim()) return false;
  if (data.check_question != null && typeof data.check_question !== "string") return false;
  if (data.memory != null && (typeof data.memory !== "object" || Array.isArray(data.memory) ||
      ["grasped", "shaky"].some((key) => data.memory[key] != null && !strings(data.memory[key])))) return false;
  if (data.components != null && (typeof data.components !== "object" || Array.isArray(data.components) ||
      (data.components.overlay_declined != null && !strings(data.components.overlay_declined)))) return false;
  return true;
};

globalThis.belayRequestJSON = async function (url, options = {}, { timeoutMs = 90000, validate } = {}) {
  const controller = new AbortController();
  let timer;
  const request = async () => {
    const response = await fetch(url, { ...options, signal: controller.signal });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      const code = data?.detail?.code;
      // A generic 5xx/coordinator outage may have happened after dispatch.
      const denied = ["verified_execution_required", "invalid_controls_mode", "controls_not_initialized"];
      const uncertain = (response.status >= 500 && !denied.includes(code)) ||
        ["execution_unknown", "worker_lost", "execution_deadline"].includes(code);
      throw globalThis.belayRequestError(code || "request_failed", uncertain,
        globalThis.belayControlMessage({ code: uncertain ? "execution_unknown" : code },
          uncertain ? null : response.headers.get("Retry-After")));
    }
    let data;
    try { data = await response.json(); }
    catch { throw globalThis.belayRequestError("invalid_response", true); }
    if (validate && !validate(data)) throw globalThis.belayRequestError("invalid_response", true);
    return data;
  };
  const deadline = new Promise((resolve, reject) => {
    timer = setTimeout(() => {
      reject(globalThis.belayRequestError("request_timeout", true));
      controller.abort();
    }, timeoutMs);
  });
  try { return await Promise.race([request(), deadline]); }
  catch (error) {
    if (error?.belayRequest) throw error;
    throw globalThis.belayRequestError("request_lost", true);
  } finally { clearTimeout(timer); }
};

// Local display/duplicate protection only. HTTP idempotency and reload recovery
// require the authenticated job API; this gate makes no server-side guarantee.
globalThis.belayTurnGate = function () {
  let active = null;
  let generation = 0;
  const uncertain = new Set();
  return {
    begin(key) {
      if (active || uncertain.has(key)) return null;
      active = { key, generation };
      return active;
    },
    current(token, key) { return active === token && generation === token.generation && token.key === key; },
    invalidate() { generation += 1; },
    finish(token, unknown = false) {
      if (unknown) uncertain.add(token.key);
      if (active === token) active = null;
    },
    blocked(key) { return Boolean(active) || uncertain.has(key); },
    unknown(key) { return uncertain.has(key); },
  };
};
