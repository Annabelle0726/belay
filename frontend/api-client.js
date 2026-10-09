import "./auth-client.js";

/* Minimal API client for the Sol peer-tutor backend.
 *
 * A front-end wires to the real system with two calls:
 *   run a submission  ->  runModel(participantId, exerciseId, src)
 *   ask the tutor     ->  solTurn({...})
 * Both return the same shapes the UI consumes (the backend keeps the run() result
 * contract and Sol's JSON contract), so the UI is unchanged.
 */
import "./control-messages.js";
import "./request-lifecycle.js";
import "./ask-jobs.js";

const askJobs = globalThis.belayAskJobs();

const BASE_URL =
  (typeof window !== "undefined" && window.SOL_BACKEND_URL) || "http://localhost:8000";

async function _json(path, opts, validate) {
  return globalThis.belayRequestJSON(BASE_URL + path, {
    ...opts,
    headers: await window.BelayAuth.headers(BASE_URL),
  }, { validate });
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
export async function solTurn({ participantId, exerciseId, event, mode, stance, source, result, recent, signals }) {
  const turn = await askJobs.ask(BASE_URL, "/api/sol/jobs", {
      participant_id: participantId,
      exercise_id: exerciseId,
      event: event || "chat",
      mode: mode || "study",
      stance: stance || "peer",
      source: source || "",
      result: result || null,
      recent: recent || [],
      signals: signals || null,
  });
  askJobs.acknowledge(turn);
  return turn;
}

export function createParticipant(anonCode, consent) {
  return _json("/api/participant", {
    method: "POST",
    body: JSON.stringify({ anon_code: anonCode, consent: !!consent }),
  });
}

export async function exportEvents(participantId) {
  const res = await fetch(`${BASE_URL}/api/session/${encodeURIComponent(participantId)}/events.jsonl`, { headers: await window.BelayAuth.headers(BASE_URL) });
  if (!res.ok) throw new Error(`Export failed: ${res.status}`);
  return res.text();
}

export async function recoverSolTurn(exerciseId) {
  const turn = await askJobs.recover(BASE_URL, "/api/sol/jobs", exerciseId);
  if (turn) askJobs.acknowledge(turn);
  return turn;
}
