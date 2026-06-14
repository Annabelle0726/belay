/* Minimal API client for the Quantum Inventioneers backend.
 *
 * Wiring the existing artifact to the real system is two swaps:
 *   artifact run(src,target,tol)  ->  runModel(participantId, exerciseId, src)
 *   artifact askSol(payload)      ->  solTurn({...})
 * Both return the SAME shapes the artifact already consumes (the backend keeps
 * the run() result contract and Sol's JSON contract), so the UI is unchanged.
 */
const BASE_URL =
  (typeof window !== "undefined" && window.QI_BACKEND_URL) || "http://localhost:8000";

async function _json(path, opts) {
  const res = await fetch(BASE_URL + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

export function getCurriculum() {
  return _json("/api/curriculum", { method: "GET" });
}

// Replaces the artifact's local run(): compiles + executes (local sim or
// Classiq) + grades, server-side, and logs the run to the research trace.
export function runModel(participantId, exerciseId, source) {
  return _json("/api/run", {
    method: "POST",
    body: JSON.stringify({ participant_id: participantId, exercise_id: exerciseId, source }),
  });
}

// Replaces the artifact's in-browser askSol(): runs the full evaluation-first
// loop server-side and returns the (artifact-compatible) Sol turn.
// `stance` is the RQ2/H2 manipulated variable (peer|oracle|control); it is
// assigned per participant via URL and held constant for the session.
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
