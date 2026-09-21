/* Minimal API client for the Sol peer-tutor backend.
 *
 * A front-end wires to the real system with two calls:
 *   run a submission  ->  runModel(participantId, exerciseId, src)
 *   ask the tutor     ->  solTurn({...})
 * Both return the same shapes the UI consumes (the backend keeps the run() result
 * contract and Sol's JSON contract), so the UI is unchanged.
 */
const BASE_URL =
  (typeof window !== "undefined" && window.SOL_BACKEND_URL) || "http://localhost:8000";

async function _json(path, opts) {
  const res = await fetch(BASE_URL + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    // A 4xx carries FastAPI's validation detail. Surface the offending field, not
    // just the status: "422" alone is what made the recent-shape mismatch expensive
    // to find.
    let reason = "";
    try {
      const body = await res.json();
      if (Array.isArray(body?.detail)) {
        reason = ": " + body.detail.map((d) => `${(d.loc || []).join(".")}: ${d.msg}`).join("; ");
      }
    } catch (e) { /* no JSON body */ }
    throw new Error(`${path} -> ${res.status}${reason}`);
  }
  return res.json();
}

export function getCurriculum() {
  return _json("/api/curriculum", { method: "GET" });
}

// Runs a submission: executes it in the sandboxed runner and grades it,
// server-side, and logs the run to the research trace.
export function runModel(participantId, exerciseId, source) {
  return _json("/api/run", {
    method: "POST",
    body: JSON.stringify({ participant_id: participantId, exercise_id: exerciseId, source }),
  });
}

// Asks the tutor: runs the full evaluation-first loop server-side and returns
// the Sol turn.
// `stance` is the RQ2/H2 manipulated variable (peer|oracle|control); it is
// assigned per participant via URL and held constant for the session.
// `recent` is the dialogue window: [{ role: "user"|"assistant", content }]. The
// legacy [{ who: "student"|"tutor", text }] spelling is still accepted (the
// backend normalizes both), but the role/content form is the documented one. An
// entry with no role, or one that is not an object, is dropped server-side.
// `result` is the run envelope (the object `/api/run` returned); a non-object is
// ignored rather than failing the turn.
export function solTurn({ participantId, exerciseId, event, mode, stance, source, result, recent, signals }) {
  return _json("/api/sol/turn", {
    method: "POST",
    body: JSON.stringify({
      participant_id: participantId,
      exercise_id: exerciseId,
      event: event || "chat",
      mode: mode || "study",
      stance: stance || "peer",
      source: source || "",
      result: result || null,
      recent: recent || [],
      signals: signals || null,
    }),
  });
}

export function createParticipant(anonCode, consent) {
  return _json("/api/participant", {
    method: "POST",
    body: JSON.stringify({ anon_code: anonCode, consent: !!consent }),
  });
}

export async function exportEvents(participantId) {
  const res = await fetch(`${BASE_URL}/api/session/${participantId}/events.jsonl`);
  return res.text();
}
