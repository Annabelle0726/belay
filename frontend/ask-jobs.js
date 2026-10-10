/* SPDX-License-Identifier: AGPL-3.0-only */
// Stable logical request pointers only: never prompts, answers or credentials.
// Unknown delivery is recovered with GET, never automatically with another POST.
globalThis.belayAskJobs = function ({ storage,
  uuid = () => globalThis.crypto.randomUUID(), wait = (ms) => new Promise((r) => setTimeout(r, ms)),
  timeoutMs = 90000 } = {}) {
  const receipts = new WeakMap();
  const error = (code, uncertain = false) => globalThis.belayRequestError(code, uncertain,
    uncertain ? globalThis.belayControlMessage({code: ["request_timeout", "request_lost", "invalid_response"].includes(code) ? code : "execution_unknown"}) : undefined);
  async function request(base, path, options = {}, validate, remaining = timeoutMs) {
    const end = Date.now() + Math.max(1, remaining);
    let expired = false, timer;
    const authorized = async () => {
      const headers = await window.BelayAuth.headers(base);
      if (expired || Date.now() >= end) throw error("request_timeout", true);
      return globalThis.belayRequestJSON(base + path, { ...options, headers },
        {validate, timeoutMs: Math.max(1, end - Date.now())});
    };
    const deadline = new Promise((resolve, reject) => {
      timer = setTimeout(() => {expired = true; reject(error("request_timeout", true));}, Math.max(1, remaining));
    });
    try { return await Promise.race([authorized(), deadline]); }
    finally { expired = true; clearTimeout(timer); }
  }
  async function prepare(base, prefix, exercise) {
    let config;
    try { config = await request(base, prefix + "/config", {}, (c) => c &&
      /^[0-9a-f]{64}$/.test(c.recovery_scope) && typeof c.learner_id === "string" &&
      c.assignments && typeof c.assignments[exercise] === "string" &&
      Number.isInteger(c.poll_seconds) && c.poll_seconds >= 1 && c.poll_seconds <= 60 &&
      Number.isInteger(c.result_seconds) && typeof c.notice === "string"); }
    catch (e) {
      e.phase = "configuration"; e.notSubmitted = true;
      if (e.uncertain) e.message = "Tutor service configuration could not be checked. No new feedback was submitted; any previous request is unchanged.";
      e.uncertain = false; // This GET cannot dispatch work. Never alter an older pointer.
      throw e;
    }
    const key = "belay.ask.v1:" + JSON.stringify([base, prefix, config.recovery_scope, exercise, config.assignments[exercise]]);
    return { base, prefix, key, config };
  }
  function read(key) {
    let raw;
    try {
      if (!storage) storage = globalThis.localStorage;
      raw = storage.getItem(key);
    }
    catch { throw error("recovery_unavailable"); }
    if (!raw) return null;
    try {
      const p = JSON.parse(raw);
      if (!/^[A-Za-z0-9_-]{16,128}$/.test(p.request_id) || typeof p.pending !== "boolean") throw Error();
      return p;
    } catch { throw error("execution_unknown", true); }
  }
  function write(key, pointer) {
    try {
      if (pointer) storage.setItem(key, JSON.stringify(pointer));
      else storage.removeItem(key);
    } catch { throw error("recovery_unavailable", true); }
  }
  const states = new Set(["queued", "running", "cancel_requested", "completed", "failed", "cancelled", "unknown", "result_expired"]);
  const validJob = (j) => j && /^[0-9a-f]{64}$/.test(j.id) && states.has(j.state);
  async function watch(context, pointer, onStatus) {
    try { return await poll(context, pointer, onStatus); }
    catch(e) {e.recovered_request = !!context.recovering; throw e;}
  }
  async function poll(context, pointer, onStatus) {
    const deadline = Date.now() + timeoutMs;
    for (;;) {
      if (Date.now() >= deadline) throw error("request_timeout", true);
      let job;
      try {
        job = await request(context.base, context.prefix + "/by-request/" + encodeURIComponent(pointer.request_id),
          {}, validJob, deadline - Date.now());
      } catch (e) {
        if (e.code === "poll_limited") {
          await wait(Math.min(deadline - Date.now(), (e.retryAfter || context.config.poll_seconds) * 1000));
          continue;
        }
        // A missing operation after a lost POST can be a race with admission.
        // It never proves that a second paid request would be safe.
        const failure = error(e.code === "job_unavailable" ? "execution_unknown" : e.code, true);
        failure.status = e.status; throw failure;
      }
      if (onStatus) onStatus(job.state, context.config);
      if (job.state === "completed") {
        if (!globalThis.belayValidateTurn(job.result)) throw error("invalid_response", true);
        receipts.set(job.result, {key: context.key, pointer, recovered:!!context.recovering});
        return job.result;
      }
      if (["failed", "cancelled", "result_expired"].includes(job.state)) {
        write(context.key, { request_id: pointer.request_id, pending: false });
        throw error(job.reason || job.state);
      }
      if (["unknown", "cancel_requested"].includes(job.state)) throw error("execution_unknown", true);
      await wait(Math.min(Math.max(0, deadline - Date.now()), context.config.poll_seconds * 1000));
    }
  }
  return {
    prepare,
    wasRecovered(turn) {return !!receipts.get(turn)?.recovered;},
    acknowledge(turn) {
      const receipt = receipts.get(turn);
      if (!receipt) throw error("invalid_response", true);
      const current = read(receipt.key);
      if (current?.request_id === receipt.pointer.request_id) {
        write(receipt.key, {request_id: receipt.pointer.request_id, pending:false});
      }
    },
    async ask(base, prefix, body, onStatus) {
      const context = await prepare(base, prefix, body.exercise_id);
      if (onStatus) onStatus("preparing", context.config);
      let pointer = read(context.key);
      if (pointer?.pending) return watch({...context,recovering:true}, pointer, onStatus);
      pointer = { request_id: uuid(), pending: true };
      write(context.key, pointer); // Commit pointer BEFORE the only POST.
      const payload = { ...body, participant_id: context.config.learner_id,
        exercise_version: context.config.assignments[body.exercise_id], request_id: pointer.request_id };
      delete payload.pseudo_id;
      delete payload.consent; // Registration/consent remains its own authenticated action.
      try {
        await request(base, prefix, { method: "POST", body: JSON.stringify(payload) }, validJob);
      } catch (e) {
        if (!e.uncertain && ["rate_limited", "queue_full", "payload_too_large", "content_not_storable", "invalid_execution_data", "conversation_conflict",
          "jobs_disabled", "jobs_not_configured", "invalid_controls_mode", "controls_not_initialized", "verified_execution_required"].includes(e.code)) {
          // Preserve the rejected request receipt. Only THIS newly generated ID
          // was definitely not admitted; an existing pending ID never enters here.
          write(context.key, {...pointer, pending:false, not_submitted:true, reason:e.code});
          e.notSubmitted = true;
        }
        throw e;
      }
      return watch(context, pointer, onStatus);
    },
    async recover(base, prefix, exercise, onStatus) {
      const context = await prepare(base, prefix, exercise);
      if (onStatus) onStatus("preparing", context.config);
      const pointer = read(context.key);
      return pointer && !pointer.not_submitted ? watch({...context,recovering:true}, pointer, onStatus) : null;
    },
  };
};
