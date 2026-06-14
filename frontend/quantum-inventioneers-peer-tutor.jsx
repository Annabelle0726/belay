import React, { useState, useMemo, useRef, useEffect } from "react";
import {
  Play, RotateCcw, Send, Download, Brain, Shield, Database, Compass,
  GitBranch, Sparkles, HelpCircle, Atom, Activity, Eye, Lightbulb,
  ArrowLeftRight, AlertTriangle, Check, ChevronDown, Heart, History
} from "lucide-react";
import { runModel, solTurn, createParticipant, exportEvents } from "./api-client.js";

/* Mode flags — set before loading the bundle.
 *
 *   window.QI_BACKEND_URL = "https://your-host"
 *     → BACKEND=true: all run/turn calls go to the real server;
 *       Anthropic key is on the server; research trace is logged.
 *
 *   window.QI_OFFLINE = true   (explicit offline/demo flag, default OFF)
 *     → OFFLINE=true: local circuit simulator for run(); Sol is unavailable
 *       (no LLM call); no research trace.  Use for circuit-only demos.
 *
 *   Neither set (default): UI shows a configuration notice; run/Sol disabled.
 */
const BACKEND = typeof window !== "undefined" && !!window.QI_BACKEND_URL;
const OFFLINE  = !BACKEND && typeof window !== "undefined" && !!window.QI_OFFLINE;

/* ============================================================================
   QUANTUM INVENTIONEERS — Peer-Tutor V1  (MVP for NSF IUSE §5 / §6)
   ----------------------------------------------------------------------------
   Anchors:
     • AWS "Evaluation-First Agentic AI" draft  -> the 5-component architecture
       (Planner · Peer-Reasoner · Self-Evaluation · Governance · Memory),
       explicit uncertainty, self-critique, abstain/escalate, affect as a
       first-class signal.  The peer tutor is the "high-frequency testbed."
     • NSF IUSE "Quantum Inventioneers" §5/§6  -> the peer tutor as pedagogical
       instrument AND research variable; scaffolded diagnosis, worked analogies,
       stretch prompting, meta-cognitive/meta-affective support; logged traces.
   The faithful-to-PEER move: Sol is a classmate a few weeks ahead, not an
   oracle. It co-reasons, shows calibrated uncertainty, preserves productive
   struggle, and can flip roles so the student teaches it (the protege effect).
   ========================================================================== */

/* ----------------------------- Quantum core ------------------------------ */
const SQ = Math.SQRT1_2;
const cx = (re, im = 0) => ({ re, im });
const cadd = (a, b) => ({ re: a.re + b.re, im: a.im + b.im });
const cmul = (a, b) => ({ re: a.re * b.re - a.im * b.im, im: a.re * b.im + a.im * b.re });
const cabs2 = (a) => a.re * a.re + a.im * a.im;

const GATE = {
  H: [[cx(SQ), cx(SQ)], [cx(SQ), cx(-SQ)]],
  X: [[cx(0), cx(1)], [cx(1), cx(0)]],
  Z: [[cx(1), cx(0)], [cx(0), cx(-1)]],
  S: [[cx(1), cx(0)], [cx(0), cx(0, 1)]],
};

const maskOf = (q, n) => 1 << (n - 1 - q);          // qubit 0 = leftmost / high bit
const bitOf = (i, q, n) => (i >> (n - 1 - q)) & 1;

function initState(n) {
  const N = 1 << n;
  const s = Array.from({ length: N }, () => cx(0, 0));
  s[0] = cx(1, 0);
  return s;
}
function applySingle(state, n, q, U) {
  const m = maskOf(q, n);
  const out = state.slice();
  for (let i = 0; i < state.length; i++) {
    if ((i & m) === 0) {
      const j = i | m, a = state[i], b = state[j];
      out[i] = cadd(cmul(U[0][0], a), cmul(U[0][1], b));
      out[j] = cadd(cmul(U[1][0], a), cmul(U[1][1], b));
    }
  }
  return out;
}
function applyCX(state, n, ctrl, tgt) {
  const mc = maskOf(ctrl, n), mt = maskOf(tgt, n);
  const out = new Array(state.length);
  for (let i = 0; i < state.length; i++) out[i] = (i & mc) ? state[i ^ mt] : state[i];
  return out;
}
const bitsOf = (i, n) => { let s = ""; for (let k = 0; k < n; k++) s += bitOf(i, k, n); return s; };

/* ------------------------- Functional-model parser ------------------------ */
/* A small, declarative, hardware-agnostic instruction set in the spirit of
   Classiq's high-level functional modeling (production swaps in the Classiq
   SDK + Classiq AI Agent). */
function parseQ(tok) {
  const m = String(tok).match(/^q?(\d+)$/i);
  return m ? parseInt(m[1], 10) : NaN;
}
function synthesize(src) {
  const lines = src.split("\n");
  let n = null;
  const gates = [];
  for (let li = 0; li < lines.length; li++) {
    let line = lines[li].replace(/#.*/, "").trim();
    if (!line) continue;
    const parts = line.split(/\s+/);
    const op = parts[0].toLowerCase();
    const where = `line ${li + 1}`;
    if (op === "allocate") {
      if (n !== null) return { ok: false, error: `Duplicate allocate (${where}). Allocate qubits once.` };
      const k = parseInt(parts[1], 10);
      if (!Number.isInteger(k) || k < 1 || k > 4) return { ok: false, error: `allocate needs a number 1–4 (${where}).` };
      n = k; continue;
    }
    if (n === null) return { ok: false, error: `Allocate qubits before the first operation (${where}).` };
    const need = (cnt) => parts.length - 1 >= cnt;
    const chk = (q) => Number.isInteger(q) && q >= 0 && q < n;
    if (op === "measure") { continue; }                       // implicit full measurement
    if (op === "superpose") {
      if (parts[1] && parts[1].toLowerCase() === "all") { for (let q = 0; q < n; q++) gates.push({ t: "H", q }); continue; }
      const q = parseQ(parts[1]); if (!chk(q)) return { ok: false, error: `superpose: bad qubit "${parts[1] ?? ""}" (${where}).` };
      gates.push({ t: "H", q }); continue;
    }
    if (op === "flip" || op === "phase" || op === "sgate") {
      const q = parseQ(parts[1]); if (!chk(q)) return { ok: false, error: `${op}: bad qubit "${parts[1] ?? ""}" (${where}).` };
      gates.push({ t: op === "flip" ? "X" : op === "phase" ? "Z" : "S", q }); continue;
    }
    if (op === "entangle") {
      if (!need(2)) return { ok: false, error: `entangle needs a control and a target, e.g. "entangle q0 q1" (${where}).` };
      const c = parseQ(parts[1]), t = parseQ(parts[2]);
      if (!chk(c) || !chk(t)) return { ok: false, error: `entangle: bad qubit(s) (${where}).` };
      if (c === t) return { ok: false, error: `entangle: control and target must differ (${where}).` };
      gates.push({ t: "CX", c, q: t }); continue;
    }
    return { ok: false, error: `Unknown operation "${parts[0]}" (${where}).` };
  }
  if (n === null) return { ok: false, error: "No qubits allocated. Start with e.g. \"allocate 2\"." };
  return { ok: true, n, gates };
}
function run(src, target, tol) {
  const syn = synthesize(src);
  if (!syn.ok) return { ok: false, error: syn.error };
  let st = initState(syn.n);
  for (const g of syn.gates) {
    if (g.t === "CX") st = applyCX(st, syn.n, g.c, g.q);
    else st = applySingle(st, syn.n, g.q, GATE[g.t]);
  }
  const probs = {};
  for (let i = 0; i < st.length; i++) probs[bitsOf(i, syn.n)] = (probs[bitsOf(i, syn.n)] || 0) + cabs2(st[i]);
  const dist = Object.entries(probs).filter(([, p]) => p > 1e-6).map(([bits, p]) => ({ bits, p })).sort((a, b) => a.bits.localeCompare(b.bits));
  const keys = new Set([...Object.keys(target), ...Object.keys(probs)]);
  const unexpected = [], missing = [];
  let tvd = 0;
  for (const b of keys) {
    const a = probs[b] || 0, t = target[b] || 0;
    tvd += Math.abs(a - t);
    if (a - t > tol) unexpected.push(b);
    else if (t - a > tol) missing.push(b);
  }
  tvd = tvd / 2;
  const goalMet = unexpected.length === 0 && missing.length === 0;
  let diff = "";
  if (goalMet) diff = "The outcome distribution matches the target.";
  else {
    const u = unexpected.length ? `weight on ${unexpected.map((b) => `|${b}⟩`).join(", ")} that the target doesn't have` : "";
    const m = missing.length ? `${unexpected.length ? " and is missing" : "missing"} weight on ${missing.map((b) => `|${b}⟩`).join(", ")}` : "";
    diff = `Your run has ${u}${m}.`.replace("has  and", "has").replace("has missing", "is missing");
  }
  return { ok: true, n: syn.n, gates: syn.gates, dist, goalMet, diff, tvd };
}

/* -------------------------------- Exercises ------------------------------- */
const EXERCISES = [
  {
    id: "superpose", title: "01 · Superposition", concept: "single-qubit superposition",
    goalText: "One qubit, equal odds of measuring 0 or 1 (50 / 50).",
    target: { "0": 0.5, "1": 0.5 }, tol: 0.07,
    prompt: "Put a single qubit into an equal superposition — a 50/50 chance of 0 or 1 when measured.",
    starter: "# Goal: one qubit in an equal superposition (50/50).\nallocate 1\n# your move here\nmeasure all\n",
  },
  {
    id: "bell", title: "02 · Entanglement", concept: "two-qubit entanglement (Bell pair)",
    goalText: "Two qubits, perfectly correlated: only 00 and 11, each ~50%.",
    target: { "00": 0.5, "11": 0.5 }, tol: 0.07,
    prompt: "Create a Bell pair: two qubits that always agree — 50% |00⟩ and 50% |11⟩, never |01⟩ or |10⟩.",
    starter: "# Goal: a Bell pair on 2 qubits (00 and 11, 50/50).\nallocate 2\nsuperpose q0\n# what links q0 and q1 so they always agree?\nmeasure all\n",
  },
  {
    id: "uniform2", title: "03 · Independence", concept: "independent superposition vs. entanglement",
    goalText: "Two qubits, all four outcomes equally likely (25% each).",
    target: { "00": 0.25, "01": 0.25, "10": 0.25, "11": 0.25 }, tol: 0.07,
    prompt: "Make all four outcomes — 00, 01, 10, 11 — equally likely (25% each). Hint: this is NOT entanglement.",
    starter: "# Goal: 00, 01, 10, 11 all equally likely (25% each).\n# This is the opposite of a Bell pair — think about each qubit on its own.\nallocate 2\n# your move here\nmeasure all\n",
  },
  {
    id: "ghz", title: "04 · Scaling", concept: "scaling entanglement to a 3-qubit GHZ state",
    goalText: "Three qubits, all-0 or all-1 (50 / 50) — a GHZ state.",
    target: { "000": 0.5, "111": 0.5 }, tol: 0.07,
    prompt: "Build a 3-qubit GHZ state: all three qubits agree — 50% |000⟩ and 50% |111⟩.",
    starter: "# Goal: a 3-qubit GHZ state (000 and 111, 50/50).\nallocate 3\nsuperpose q0\n# spread the correlation from q0 out to q1 and q2\nmeasure all\n",
  },
];

/* Sol's prompts, buildContext, and askSol have been removed.
   The tutor loop now runs entirely server-side (/api/sol/turn).
   In OFFLINE mode Sol is unavailable; in BACKEND mode it responds via the
   Jetstream2 inference service — no model key lives in the browser. */

/* ------------------------------- UI helpers ------------------------------- */
const AFFECT = {
  flow: { c: "#7bd88f", label: "Flow" },
  productive_struggle: { c: "#5fd0c5", label: "Productive struggle" },
  curious: { c: "#6aa3ff", label: "Curious" },
  confusion: { c: "#e7a93e", label: "Confusion" },
  frustration: { c: "#e8745c", label: "Frustration" },
  disengaged: { c: "#8b93a7", label: "Disengaged" },
};
const INTERV = {
  observe: { icon: Eye, label: "Observing" },
  co_reason: { icon: GitBranch, label: "Reasoning together" },
  diagnose: { icon: Activity, label: "Diagnosing" },
  worked_analogy: { icon: Lightbulb, label: "Worked analogy" },
  stretch: { icon: Sparkles, label: "Stretch challenge" },
  reciprocate: { icon: ArrowLeftRight, label: "Your turn to explain" },
  encourage: { icon: Heart, label: "Encouragement" },
  revisit: { icon: History, label: "Spaced check" },
  escalate: { icon: AlertTriangle, label: "Beyond me — ask instructor" },
};

/* concept_id → human label, mirroring backend curriculum/concepts.py CONCEPTS.
   Used to label the §5e revisit concept; falls back to the raw id if unmapped. */
const CONCEPT_LABELS = {
  superposition: "Single-qubit superposition",
  determinism: "Deterministic state preparation (X gate)",
  measurement: "Quantum measurement and outcome distributions",
  entanglement: "Two-qubit entanglement (Bell pair)",
  independence: "Independent superposition vs. entanglement",
  scaling: "Scaling entanglement to larger registers (GHZ)",
  phase: "Relative phase and measurement statistics",
  abstraction: "Specification → synthesized algorithm (abstraction + debugging)",
};
const GOV = {
  none: "—",
  withholding_solution: "Withholding full solution (preserve learning)",
  redirect_answer_seeking: "Answer-seeking → redirected to reasoning",
  encourage_tone: "Encouraging tone",
  flag_escalate: "Flagged for instructor",
};

function computeSignals(arr) {
  const trend = arr.slice(-3).map((a) => +a.tvd.toFixed(2));
  let sinceProgress = 0;
  for (let i = arr.length - 1; i > 0; i--) {
    if (arr[i].ok && arr[i].tvd < arr[i - 1].tvd - 0.01) break;
    sinceProgress++;
  }
  const last2 = arr.slice(-2);
  const repeatedError = last2.length === 2 && !last2[0].ok && !last2[1].ok && last2[0].err === last2[1].err;
  return { attempts: arr.length, distanceTrend: trend, repeatedError, sinceLastProgress: sinceProgress };
}

/* -------------------------------- Circuit -------------------------------- */
function Circuit({ result }) {
  if (!result || !result.ok) {
    return <div className="qi-circuit-empty">No synthesized circuit yet — write a model and press <b>Synthesize&nbsp;&amp;&nbsp;Run</b>.</div>;
  }
  const { n, gates } = result;
  const LAB = 30, COL = 48, ROW = 44, PADT = 20, METER = 34;
  const w = LAB + Math.max(1, gates.length) * COL + METER + 16;
  const h = PADT * 2 + (n - 1) * ROW + 16;
  const yq = (q) => PADT + 8 + q * ROW;
  const xg = (i) => LAB + i * COL + COL / 2;
  return (
    <div className="qi-circuit-scroll">
      <svg width={w} height={h} className="qi-svg">
        {Array.from({ length: n }).map((_, q) => (
          <g key={q}>
            <text x={2} y={yq(q) + 4} className="qi-qlabel">q{q}</text>
            <line x1={LAB} y1={yq(q)} x2={w - METER - 8} y2={yq(q)} className="qi-wire" />
          </g>
        ))}
        {gates.map((g, i) => {
          const x = xg(i);
          if (g.t === "CX") {
            const y1 = yq(g.c), y2 = yq(g.q);
            return (
              <g key={i}>
                <line x1={x} y1={y1} x2={x} y2={y2} className="qi-cxline" />
                <circle cx={x} cy={y1} r={4.5} className="qi-ctrl" />
                <circle cx={x} cy={y2} r={11} className="qi-target" />
                <line x1={x - 11} y1={y2} x2={x + 11} y2={y2} className="qi-plus" />
                <line x1={x} y1={y2 - 11} x2={x} y2={y2 + 11} className="qi-plus" />
              </g>
            );
          }
          const y = yq(g.q);
          return (
            <g key={i}>
              <rect x={x - 15} y={y - 14} width={30} height={28} rx={6} className="qi-gate" />
              <text x={x} y={y + 5} className="qi-gtext">{g.t}</text>
            </g>
          );
        })}
        {Array.from({ length: n }).map((_, q) => {
          const x = w - METER, y = yq(q);
          return (
            <g key={"m" + q}>
              <rect x={x - 2} y={y - 13} width={26} height={26} rx={5} className="qi-meter" />
              <path d={`M ${x + 3} ${y + 5} A 8 8 0 0 1 ${x + 19} ${y + 5}`} className="qi-meterarc" />
              <line x1={x + 11} y1={y + 5} x2={x + 17} y2={y - 3} className="qi-meterarc" />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ------------------------------ Pipeline stage --------------------------- */
function Stage({ idx, icon: Icon, title, children, active }) {
  return (
    <div className={"qi-stage" + (active ? " qi-stage-on" : "")} style={{ animationDelay: `${idx * 90}ms` }}>
      <div className="qi-stage-head"><Icon size={14} /><span>{title}</span></div>
      <div className="qi-stage-body">{children}</div>
    </div>
  );
}

/* ================================== APP =================================== */
export default function App() {
  // ── all hooks first (required by React) ──────────────────────────────────
  const [exId, setExId] = useState("bell");
  const ex = useMemo(() => EXERCISES.find((e) => e.id === exId), [exId]);
  const [source, setSource] = useState(ex.starter);
  const [result, setResult] = useState(null);
  const [attempts, setAttempts] = useState([]); // {tvd, ok, err}
  const [messages, setMessages] = useState([]); // {who:'sol'|'me', text}
  const [tele, setTele] = useState(null);
  const [memory, setMemory] = useState({ grasped: [], shaky: [] });
  const [mode, setMode] = useState("study"); // study | teach
  const [watch, setWatch] = useState(true);
  const [busy, setBusy] = useState(false);
  const [apiErr, setApiErr] = useState(null);
  const [input, setInput] = useState("");
  const [log, setLog] = useState([]);
  const [aboutOpen, setAboutOpen] = useState(false);
  const chatRef = useRef(null);
  const teleSeq = useRef(0);

  // ── wired-mode state (unused when BACKEND=false) ──────────────────────────
  // Stance is read once from ?stance= and held constant for the session.
  // It is the RQ2/H2 manipulated variable; varying it mid-session would break
  // the manipulation, so it is NOT a student-facing toggle.
  const [stance] = useState(() => {
    if (typeof window === "undefined") return "peer";
    const p = new URLSearchParams(window.location.search).get("stance");
    return ["peer", "oracle", "control"].includes(p) ? p : "peer";
  });
  const [participantId, setParticipantId] = useState(null);
  const [enrollCode, setEnrollCode] = useState("");
  const [onboardErr, setOnboardErr] = useState(null);
  const [onboardBusy, setOnboardBusy] = useState(false);

  useEffect(() => { setSource(ex.starter); setResult(null); setAttempts([]); }, [exId]);
  useEffect(() => { if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight; }, [messages, busy]);

  const signals = useMemo(() => computeSignals(attempts), [attempts]);

  // ── helpers ───────────────────────────────────────────────────────────────
  function recentDialogue(extra) {
    const base = messages.slice(-6).map((m) => ({ who: m.who === "me" ? "student" : "sol", text: m.text }));
    if (extra) base.push({ who: "student", text: extra });
    return base;
  }

  // ── onboarding (wired path only) ─────────────────────────────────────────
  async function handleConsent(consentVal) {
    setOnboardBusy(true); setOnboardErr(null);
    try {
      const code = enrollCode.trim() || ("anon-" + Math.random().toString(36).slice(2, 8));
      const p = await createParticipant(code, consentVal);
      setParticipantId(p.id);
    } catch (_) {
      setOnboardErr("Couldn't connect to the backend — check the URL and try again.");
    } finally {
      setOnboardBusy(false);
    }
  }

  // ── callSol: routes to /api/sol/turn (BACKEND) or shows offline notice ───
  async function callSol(event, studentText, override = {}) {
    if (!BACKEND) {
      // Sol lives only on the server — unavailable without a backend URL.
      setApiErr(OFFLINE
        ? "Sol needs a backend connection and isn't available offline. You can still run circuits and explore the distribution."
        : "Set window.QI_BACKEND_URL to connect this UI to a running backend.");
      return;
    }
    const useResult  = override.result  !== undefined ? override.result  : result;
    const useSignals = override.signals || signals;
    setBusy(true); setApiErr(null);
    try {
      const reply = await solTurn({
        participantId, exerciseId: exId, event, mode, stance, source,
        result: useResult, recent: recentDialogue(studentText), signals: useSignals,
      });
      teleSeq.current += 1;
      setMessages((m) => [...m, { who: "sol", text: reply.message }]);
      setTele({ ...reply, seq: teleSeq.current });
      if (reply.memory && (reply.memory.grasped || reply.memory.shaky)) {
        setMemory({ grasped: reply.memory.grasped || [], shaky: reply.memory.shaky || [] });
      }
      setLog((L) => [...L, {
        ts: new Date().toISOString(), exercise: ex.id, mode, event,
        affective_state: reply.affective_state, confidence: reply.confidence,
        intervention: reply.intervention, governance: reply.governance,
        goal_met: useResult?.ok ? useResult.goalMet : false, tvd: useResult?.ok ? +useResult.tvd.toFixed(3) : null,
      }]);
    } catch (_) {
      // Peer-voiced; never surface raw server errors.
      setApiErr("Hmm, I need a second — let me catch up. Try that again in a moment.");
    } finally { setBusy(false); }
  }

  // ── doRun: three-way branch ───────────────────────────────────────────────
  async function doRun() {
    if (BACKEND) {
      // Wired path: compile + grade on the server, log to research trace.
      if (!participantId) return;   // onboarding enforces this; belt-and-suspenders
      setBusy(true); setApiErr(null);
      try {
        const r = await runModel(participantId, exId, source);
        setBusy(false);
        setResult(r);
        const next = [...attempts, { tvd: r.ok ? r.tvd : 1, ok: r.ok, err: r.ok ? null : r.error }];
        setAttempts(next);
        if (watch) await callSol("run", null, { result: r, signals: computeSignals(next) });
      } catch (_) {
        setApiErr("Couldn't reach the backend — check the connection and try again.");
        setBusy(false);
      }
    } else if (OFFLINE) {
      // Explicit offline/demo mode: local circuit simulator only (no logging, no Sol).
      const r = run(source, ex.target, ex.tol);
      setResult(r);
      const next = [...attempts, { tvd: r.ok ? r.tvd : 1, ok: r.ok, err: r.ok ? null : r.error }];
      setAttempts(next);
      if (watch && !busy) callSol("run", null, { result: r, signals: computeSignals(next) });
    } else {
      // Neither flag set — show a configuration notice.
      setApiErr("Set window.QI_BACKEND_URL to connect to a backend, or window.QI_OFFLINE = true for local circuit exploration.");
    }
  }

  function send() {
    const t = input.trim();
    if (!t || busy) return;
    if (BACKEND && !participantId) return;   // fail-safe: no backend calls before registration
    setMessages((m) => [...m, { who: "me", text: t }]);
    setInput("");
    callSol("chat", t);
  }

  function exportLog() {
    const blob = new Blob([JSON.stringify(log, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "quantum-inventioneers-session-log.json"; a.click();
    URL.revokeObjectURL(url);
  }

  // Primary export in BACKEND mode: GET /api/session/{pid}/events.jsonl
  // (durable §6 research trace, consenters only).  Falls back to local log.
  async function doExport() {
    if (BACKEND && participantId) {
      const text = await exportEvents(participantId);
      const blob = new Blob([text], { type: "application/x-ndjson" });
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `qi-trace-${participantId}.jsonl`; a.click();
      URL.revokeObjectURL(url);
    } else {
      exportLog();
    }
  }

  const aff = tele && AFFECT[tele.affective_state] ? AFFECT[tele.affective_state] : null;
  const iv = tele && INTERV[tele.intervention] ? INTERV[tele.intervention] : null;
  const conf = tele ? Math.max(0, Math.min(1, tele.confidence ?? 0.5)) : 0;
  // Persistent learner model (§5e). Null on the control arm — degrade gracefully.
  const lm = tele && tele.components ? tele.components.learner_model : null;

  // ── onboarding screen (wired path, before registration) ──────────────────
  if (BACKEND && !participantId) {
    return (
      <div className="qi-root">
        <style dangerouslySetInnerHTML={{ __html: CSS }} />
        <div className="qi-bg" />
        <div className="qi-onboard">
          <div className="qi-onboard-card">
            <div className="qi-ob-logo"><Atom size={24} /></div>
            <div className="qi-ob-title">Quantum Inventioneers</div>
            <div className="qi-ob-sub">Peer-Tutor&nbsp;·&nbsp;V1 — a study partner, not an answer key</div>

            <label className="qi-ob-label">
              Enrollment code <small>— NOT your name or email</small>
              <input
                className="qi-input"
                placeholder="Leave blank for a random anonymous code"
                value={enrollCode}
                onChange={(e) => setEnrollCode(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleConsent(true); }}
                disabled={onboardBusy}
              />
            </label>

            <div className="qi-ob-consent">
              <p>
                This session is part of a research study exploring how AI peer-tutoring supports
                learning in quantum software engineering. With your consent, your interactions —
                the code you write and Sol's responses — are logged to a research trace. No personal
                data (name, email, or any identifier beyond the anonymous code above) is collected.
                You may participate without research logging by choosing the second option;
                your tutoring experience is <em>identical</em> either way.
              </p>
            </div>

            {onboardErr && <div className="qi-apierr">{onboardErr}</div>}

            <div className="qi-ob-btns">
              <button className="qi-run" onClick={() => handleConsent(true)} disabled={onboardBusy}>
                I consent to research logging
              </button>
              <button className="qi-ob-skip" onClick={() => handleConsent(false)} disabled={onboardBusy}>
                Use without research logging
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── main app render ───────────────────────────────────────────────────────
  return (
    <div className="qi-root">
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
      <div className="qi-bg" />

      {/* Header */}
      <header className="qi-header">
        <div className="qi-brand">
          <div className="qi-logo"><Atom size={20} /></div>
          <div>
            <div className="qi-title">Quantum Inventioneers</div>
            <div className="qi-sub">Peer-Tutor&nbsp;·&nbsp;V1 — a study partner, not an answer key</div>
          </div>
        </div>
        <div className="qi-headctl">
          <div className="qi-mode">
            <button className={mode === "study" ? "on" : ""} onClick={() => setMode("study")}>Study with Sol</button>
            <button className={mode === "teach" ? "on" : ""} onClick={() => setMode("teach")} title="Flip roles — you teach Sol (the protégé effect)">
              <ArrowLeftRight size={13} /> Teach Sol
            </button>
          </div>
          <button className="qi-about" onClick={() => setAboutOpen((v) => !v)}>What is this? <ChevronDown size={14} style={{ transform: aboutOpen ? "rotate(180deg)" : "none", transition: "transform .2s" }} /></button>
        </div>
      </header>

      {/* Mode banner — shown when not in full backend mode */}
      {!BACKEND && (
        <div className="qi-demo-banner">
          {OFFLINE
            ? "Offline mode — local circuit simulator only. Sol needs a backend connection."
            : "Not connected to a backend — set window.QI_BACKEND_URL to enable Sol and research logging, or window.QI_OFFLINE = true for circuit exploration only."}
        </div>
      )}

      {aboutOpen && (
        <div className="qi-aboutbox">
          <p><b>V1 MVP for the NSF IUSE proposal.</b> Sol is an AI <i>peer</i> — a classmate a few weeks ahead — built on the five-component agentic architecture from our AWS draft (Planner · Peer-Reasoner · Self-Evaluation · Governance · Memory). It co-reasons, shows calibrated uncertainty, preserves productive struggle, and can flip roles so you teach it. The "glass box" on the right makes every pedagogical decision — and the research trace §6 needs — visible per turn.</p>
          <p className="qi-caveat">The exercises use a faithful high-level functional-model stand-in + a real state-vector simulator; production swaps in the Classiq SDK and the Classiq AI Agent. The live peer tutor runs server-side via the Jetstream2 Inference Service — no model key lives in the browser.</p>
        </div>
      )}

      <div className="qi-grid">
        {/* ----------------------------- LAB ----------------------------- */}
        <section className="qi-lab">
          <div className="qi-exrow">
            {EXERCISES.map((e) => (
              <button key={e.id} className={"qi-extab" + (e.id === exId ? " on" : "")} onClick={() => setExId(e.id)}>{e.title}</button>
            ))}
          </div>

          <div className="qi-prompt">
            <div className="qi-prompt-k">Challenge</div>
            <p>{ex.prompt}</p>
            <div className="qi-goal"><span>TARGET</span> {ex.goalText}</div>
          </div>

          <div className="qi-editor-wrap">
            <div className="qi-editor-bar">
              <span>functional_model.qmod</span>
              <button className="qi-reset" onClick={() => setSource(ex.starter)}><RotateCcw size={12} /> reset</button>
            </div>
            <textarea className="qi-editor" spellCheck={false} value={source} onChange={(e) => setSource(e.target.value)} />
            <div className="qi-ops">
              <b>ops</b> allocate N · superpose qK|all · entangle qC qT · flip qK · phase qK · measure all · # comment
            </div>
          </div>

          <div className="qi-runrow">
            <button className="qi-run" onClick={doRun} disabled={busy || (BACKEND && !participantId) || (!BACKEND && !OFFLINE)}><Play size={15} /> Synthesize &amp; Run</button>
            <label className="qi-watch" title="Let Sol watch your runs and react like a study partner">
              <input type="checkbox" checked={watch} onChange={(e) => setWatch(e.target.checked)} /> Sol watches my work
            </label>
          </div>

          {result && (
            <div className="qi-result">
              {result.ok ? (
                <>
                  <div className={"qi-verdict " + (result.goalMet ? "ok" : "no")}>
                    {result.goalMet ? <><Check size={15} /> Target reached — distribution matches.</> : <>Compiles & runs — not the target yet.</>}
                  </div>
                  <Circuit result={result} />
                  <div className="qi-dist">
                    <div className="qi-dist-k">Measurement outcomes</div>
                    {result.dist.map((d) => (
                      <div className="qi-bar" key={d.bits}>
                        <span className="qi-bar-l">|{d.bits}⟩</span>
                        <div className="qi-bar-track"><div className="qi-bar-fill" style={{ width: `${d.p * 100}%` }} /></div>
                        <span className="qi-bar-v">{(d.p * 100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="qi-error"><AlertTriangle size={14} /> {result.error}</div>
              )}
            </div>
          )}
        </section>

        {/* ----------------------------- SOL ----------------------------- */}
        <section className="qi-sol">
          <div className="qi-sol-head">
            <div className="qi-sol-id">
              <div className="qi-sol-av">S</div>
              <div>
                <div className="qi-sol-name">Sol</div>
                <div className="qi-sol-role">{mode === "teach" ? "playing a confused classmate — teach me!" : "your quantum study partner"}</div>
              </div>
            </div>
            <button
              className="qi-export"
              onClick={doExport}
              disabled={BACKEND ? !participantId : !log.length}
              title={BACKEND && participantId
                ? "Download §6 research trace (GET /api/session/{pid}/events.jsonl)"
                : "Download session interaction log (JSON)"}
            >
              <Download size={13} /> {BACKEND && participantId ? "research trace" : "session log"}
            </button>
          </div>

          <div className="qi-chat" ref={chatRef}>
            {messages.length === 0 && !busy && (
              <div className="qi-empty">
                {mode === "teach"
                  ? "Flip the script: Sol will act like a classmate who's confused about this concept. Run your model or say hi, then explain it to them."
                  : "Say hi, or just press Synthesize & Run — Sol studies alongside you and reacts to what you try."}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={"qi-msg " + (m.who === "me" ? "me" : "sol")}>
                {m.who === "sol" && <div className="qi-msg-av">S</div>}
                <div className="qi-bubble">{m.text}</div>
              </div>
            ))}
            {busy && <div className="qi-msg sol"><div className="qi-msg-av">S</div><div className="qi-bubble qi-typing"><span /><span /><span /></div></div>}
            {tele && tele.check_question && !busy && (
              <div className="qi-check"><HelpCircle size={13} /> {tele.check_question}</div>
            )}
          </div>

          {apiErr && <div className="qi-apierr">{apiErr}</div>}

          <div className="qi-inputrow">
            <input
              className="qi-input"
              placeholder={mode === "teach" ? "Explain it to Sol…" : "Ask Sol, or talk through your thinking…"}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") send(); }}
              disabled={busy || (BACKEND && !participantId) || (!BACKEND && !OFFLINE)}
            />
            <button className="qi-send" onClick={send} disabled={busy || !input.trim() || (BACKEND && !participantId) || (!BACKEND && !OFFLINE)}><Send size={15} /></button>
          </div>

          {/* ---------------------- GLASS BOX ---------------------- */}
          <div className="qi-glass">
            <div className="qi-glass-head"><span>Inside Sol — the agentic glass box</span><span className="qi-glass-tag">5-component architecture</span></div>
            {!tele ? (
              <div className="qi-glass-empty">Each exchange flows through five components. They'll light up here as Sol responds.</div>
            ) : (
              <div className="qi-pipe" key={tele.seq}>
                <Stage idx={0} icon={Compass} title="Planner" active>
                  <span className="qi-plan">{tele.planner_note}</span>
                </Stage>
                <Stage idx={1} icon={Brain} title="Peer-Reasoner" active>
                  <div className="qi-readrow">
                    {aff && <span className="qi-chip" style={{ "--ch": aff.c }}>{aff.label}</span>}
                    {iv && <span className="qi-chip qi-chip-iv"><iv.icon size={11} /> {iv.label}</span>}
                  </div>
                  {tele.affect_reasoning && <span className="qi-why">cue: {tele.affect_reasoning}</span>}
                </Stage>
                <Stage idx={2} icon={Activity} title="Self-Evaluation" active>
                  <div className="qi-conf">
                    <span>confidence in own read</span>
                    <div className="qi-conf-track"><div className="qi-conf-fill" style={{ width: `${conf * 100}%`, background: conf < 0.45 ? "#e7a93e" : conf < 0.7 ? "#6aa3ff" : "#7bd88f" }} /></div>
                    <b>{Math.round(conf * 100)}%</b>
                  </div>
                  {tele.self_critique && <span className="qi-why">{tele.self_critique}</span>}
                </Stage>
                <Stage idx={3} icon={Shield} title="Governance" active>
                  <span className={"qi-gov" + (tele.governance !== "none" ? " flag" : "")}>{GOV[tele.governance] || GOV.none}</span>
                </Stage>
                <Stage idx={4} icon={Database} title="Memory" active>
                  <div className="qi-mem">
                    <div><span className="qi-mem-k ok">grasped</span>{(memory.grasped || []).length ? memory.grasped.map((g, i) => <em key={i}>{g}</em>) : <i className="qi-none">—</i>}</div>
                    <div><span className="qi-mem-k shaky">shaky</span>{(memory.shaky || []).length ? memory.shaky.map((g, i) => <em key={i}>{g}</em>) : <i className="qi-none">—</i>}</div>
                  </div>
                  {/* Persistent learner model (§5e). Hidden on control (lm === null). */}
                  {lm && (
                    <div className="qi-lm">
                      <span className="qi-chip-lm" title="concepts marked grasped in the persistent model">{lm.n_grasped} grasped</span>
                      <span className="qi-chip-lm" title="concepts still shaky in the persistent model">{lm.n_shaky} shaky</span>
                      {tele.intervention === "revisit" && lm.revisit_concept && (
                        <span className="qi-chip-revisit" title={lm.revisit_concept}>
                          <History size={11} /> revisiting {CONCEPT_LABELS[lm.revisit_concept] || lm.revisit_concept}
                        </span>
                      )}
                    </div>
                  )}
                </Stage>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ================================== CSS =================================== */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600;9..144,700&family=Hanken+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --ink:#0a0d16; --ink2:#10141f; --ink3:#161b29; --raise:#1b2233;
  --line:#283044; --line2:#323c52;
  --text:#ece6d8; --muted:#9aa4b8; --faint:#6b7488;
  --amber:#e7a93e; --cyan:#5fd0c5; --blue:#6aa3ff; --green:#7bd88f; --red:#e8745c;
  --ui:'Hanken Grotesk',system-ui,sans-serif; --disp:'Fraunces',Georgia,serif; --mono:'JetBrains Mono',monospace;
}
*{box-sizing:border-box}
.qi-root{position:relative;min-height:100vh;background:var(--ink);color:var(--text);font-family:var(--ui);overflow-x:hidden;}
.qi-bg{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(900px 500px at 88% -8%, rgba(95,208,197,.10), transparent 60%),
    radial-gradient(800px 600px at 2% 110%, rgba(231,169,62,.08), transparent 60%),
    linear-gradient(var(--ink),var(--ink));
}
.qi-bg::after{content:"";position:absolute;inset:0;opacity:.5;
  background-image:linear-gradient(rgba(255,255,255,.022) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.022) 1px,transparent 1px);
  background-size:44px 44px;mask-image:radial-gradient(circle at 50% 30%,#000,transparent 85%);}

.qi-header,.qi-grid,.qi-aboutbox{position:relative;z-index:1;}
.qi-header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 26px;border-bottom:1px solid var(--line);background:rgba(12,15,23,.6);backdrop-filter:blur(8px);flex-wrap:wrap;}
.qi-brand{display:flex;align-items:center;gap:14px;}
.qi-logo{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;color:#0a0d16;background:linear-gradient(135deg,var(--cyan),#3fae9f);box-shadow:0 6px 22px rgba(95,208,197,.3);}
.qi-title{font-family:var(--disp);font-weight:600;font-size:22px;letter-spacing:.2px;}
.qi-sub{font-size:12.5px;color:var(--muted);margin-top:1px;}
.qi-headctl{display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.qi-mode{display:flex;background:var(--ink3);border:1px solid var(--line);border-radius:11px;padding:3px;gap:3px;}
.qi-mode button{display:flex;align-items:center;gap:5px;border:0;background:transparent;color:var(--muted);font-family:var(--ui);font-size:13px;font-weight:600;padding:7px 13px;border-radius:8px;cursor:pointer;transition:.18s;}
.qi-mode button.on{background:linear-gradient(135deg,var(--amber),#cf8f28);color:#1a1205;box-shadow:0 3px 12px rgba(231,169,62,.28);}
.qi-mode button:not(.on):hover{color:var(--text);}
.qi-about{border:1px solid var(--line);background:var(--ink3);color:var(--muted);font-family:var(--ui);font-size:12.5px;font-weight:600;padding:8px 12px;border-radius:9px;cursor:pointer;display:flex;align-items:center;gap:6px;}
.qi-about:hover{color:var(--text);border-color:var(--line2);}
.qi-aboutbox{padding:16px 26px;border-bottom:1px solid var(--line);background:var(--ink2);font-size:13.5px;line-height:1.62;color:#cfd6e4;}
.qi-aboutbox p{margin:0 0 8px;max-width:1000px;}
.qi-caveat{color:var(--muted);font-size:12.5px;}

.qi-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:18px;padding:22px 26px 40px;align-items:start;max-width:1480px;margin:0 auto;}
@media(max-width:980px){.qi-grid{grid-template-columns:1fr;}}

/* LAB */
.qi-lab{background:var(--ink2);border:1px solid var(--line);border-radius:16px;padding:16px;animation:rise .5s ease both;}
.qi-exrow{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px;}
.qi-extab{border:1px solid var(--line);background:var(--ink3);color:var(--muted);font-family:var(--ui);font-size:12.5px;font-weight:600;padding:7px 11px;border-radius:9px;cursor:pointer;transition:.16s;}
.qi-extab.on{background:var(--raise);color:var(--text);border-color:var(--cyan);box-shadow:inset 0 0 0 1px rgba(95,208,197,.25);}
.qi-extab:not(.on):hover{color:var(--text);}
.qi-prompt{background:var(--ink3);border:1px solid var(--line);border-radius:12px;padding:14px 15px;margin-bottom:14px;}
.qi-prompt-k{font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--cyan);font-weight:700;margin-bottom:6px;}
.qi-prompt p{margin:0 0 10px;font-size:14.5px;line-height:1.55;}
.qi-goal{font-size:12.5px;color:#cfd6e4;background:var(--ink);border:1px dashed var(--line2);border-radius:8px;padding:8px 10px;}
.qi-goal span{font-family:var(--mono);font-size:10px;color:var(--amber);letter-spacing:.1em;margin-right:8px;}

.qi-editor-wrap{border:1px solid var(--line);border-radius:12px;overflow:hidden;background:#0c1019;}
.qi-editor-bar{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--ink3);border-bottom:1px solid var(--line);font-family:var(--mono);font-size:11.5px;color:var(--muted);}
.qi-reset{border:0;background:transparent;color:var(--muted);font-family:var(--ui);font-size:11.5px;cursor:pointer;display:flex;align-items:center;gap:4px;}
.qi-reset:hover{color:var(--text);}
.qi-editor{width:100%;min-height:158px;resize:vertical;border:0;outline:0;background:transparent;color:#dfe6f0;font-family:var(--mono);font-size:13.5px;line-height:1.62;padding:13px 14px;tab-size:2;}
.qi-editor::selection{background:rgba(95,208,197,.28);}
.qi-ops{padding:8px 12px;border-top:1px solid var(--line);background:var(--ink3);font-family:var(--mono);font-size:11px;color:var(--muted);line-height:1.6;}
.qi-ops b{color:var(--amber);margin-right:7px;}

.qi-runrow{display:flex;align-items:center;gap:14px;margin:14px 0;flex-wrap:wrap;}
.qi-run{display:flex;align-items:center;gap:8px;border:0;background:linear-gradient(135deg,var(--cyan),#3fae9f);color:#08130f;font-family:var(--ui);font-weight:700;font-size:14px;padding:11px 18px;border-radius:11px;cursor:pointer;box-shadow:0 6px 20px rgba(95,208,197,.26);transition:.16s;}
.qi-run:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 9px 26px rgba(95,208,197,.34);}
.qi-run:disabled{opacity:.5;cursor:not-allowed;}
.qi-watch{display:flex;align-items:center;gap:7px;font-size:12.5px;color:var(--muted);cursor:pointer;user-select:none;}
.qi-watch input{accent-color:var(--cyan);width:15px;height:15px;}

.qi-result{margin-top:4px;animation:rise .4s ease both;}
.qi-verdict{display:flex;align-items:center;gap:8px;font-size:13.5px;font-weight:600;padding:10px 13px;border-radius:10px;margin-bottom:12px;}
.qi-verdict.ok{background:rgba(123,216,143,.12);border:1px solid rgba(123,216,143,.4);color:var(--green);}
.qi-verdict.no{background:var(--ink3);border:1px solid var(--line);color:#cfd6e4;}
.qi-error{display:flex;align-items:flex-start;gap:8px;font-family:var(--mono);font-size:12.5px;color:var(--red);background:rgba(232,116,92,.1);border:1px solid rgba(232,116,92,.35);border-radius:10px;padding:11px 13px;line-height:1.5;}

.qi-circuit-scroll{overflow-x:auto;background:#0c1019;border:1px solid var(--line);border-radius:11px;padding:8px 6px;margin-bottom:12px;}
.qi-circuit-empty{font-size:12.5px;color:var(--muted);padding:8px 2px;}
.qi-svg{display:block;}
.qi-qlabel{font-family:var(--mono);font-size:11px;fill:var(--muted);}
.qi-wire{stroke:var(--line2);stroke-width:1.4;}
.qi-gate{fill:rgba(95,208,197,.14);stroke:var(--cyan);stroke-width:1.4;}
.qi-gtext{font-family:var(--mono);font-size:12px;font-weight:600;fill:var(--cyan);text-anchor:middle;}
.qi-cxline{stroke:var(--cyan);stroke-width:1.6;}
.qi-ctrl{fill:var(--cyan);}
.qi-target{fill:none;stroke:var(--cyan);stroke-width:1.6;}
.qi-plus{stroke:var(--cyan);stroke-width:1.6;}
.qi-meter{fill:rgba(231,169,62,.1);stroke:rgba(231,169,62,.5);stroke-width:1.3;}
.qi-meterarc{fill:none;stroke:var(--amber);stroke-width:1.4;}

.qi-dist-k{font-size:10.5px;letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-bottom:9px;}
.qi-bar{display:flex;align-items:center;gap:10px;margin-bottom:7px;}
.qi-bar-l{font-family:var(--mono);font-size:12.5px;color:#dfe6f0;width:54px;}
.qi-bar-track{flex:1;height:18px;background:var(--ink3);border-radius:5px;overflow:hidden;border:1px solid var(--line);}
.qi-bar-fill{height:100%;background:linear-gradient(90deg,rgba(95,208,197,.55),var(--cyan));border-radius:5px 0 0 5px;transition:width .55s cubic-bezier(.2,.7,.2,1);}
.qi-bar-v{font-family:var(--mono);font-size:12px;color:var(--muted);width:40px;text-align:right;}

/* SOL */
.qi-sol{background:var(--ink2);border:1px solid var(--line);border-radius:16px;padding:16px;display:flex;flex-direction:column;animation:rise .5s .07s ease both;}
.qi-sol-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;}
.qi-sol-id{display:flex;align-items:center;gap:11px;}
.qi-sol-av{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;font-family:var(--disp);font-weight:600;font-size:18px;color:#1a1205;background:linear-gradient(135deg,var(--amber),#cf8f28);}
.qi-sol-name{font-family:var(--disp);font-weight:600;font-size:17px;}
.qi-sol-role{font-size:12px;color:var(--muted);margin-top:1px;}
.qi-export{display:flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--ink3);color:var(--muted);font-family:var(--ui);font-size:11.5px;font-weight:600;padding:7px 11px;border-radius:9px;cursor:pointer;}
.qi-export:hover:not(:disabled){color:var(--text);border-color:var(--line2);}
.qi-export:disabled{opacity:.4;cursor:not-allowed;}

.qi-chat{background:#0c1019;border:1px solid var(--line);border-radius:12px;padding:14px;min-height:240px;max-height:340px;overflow-y:auto;display:flex;flex-direction:column;gap:11px;}
.qi-empty{color:var(--muted);font-size:13px;line-height:1.6;margin:auto 0;text-align:center;padding:0 12px;}
.qi-msg{display:flex;gap:9px;align-items:flex-end;max-width:90%;}
.qi-msg.me{align-self:flex-end;flex-direction:row-reverse;}
.qi-msg-av{width:26px;height:26px;border-radius:8px;flex:none;display:grid;place-items:center;font-family:var(--disp);font-weight:600;font-size:13px;color:#1a1205;background:linear-gradient(135deg,var(--amber),#cf8f28);}
.qi-bubble{font-size:13.6px;line-height:1.56;padding:10px 13px;border-radius:13px;white-space:pre-wrap;}
.qi-msg.sol .qi-bubble{background:var(--raise);border:1px solid var(--line);border-bottom-left-radius:4px;color:#e8edf6;}
.qi-msg.me .qi-bubble{background:linear-gradient(135deg,rgba(95,208,197,.2),rgba(95,208,197,.1));border:1px solid rgba(95,208,197,.32);border-bottom-right-radius:4px;color:#eaf6f4;}
.qi-typing{display:flex;gap:4px;align-items:center;padding:13px;}
.qi-typing span{width:6px;height:6px;border-radius:50%;background:var(--muted);animation:blink 1.2s infinite;}
.qi-typing span:nth-child(2){animation-delay:.2s;}.qi-typing span:nth-child(3){animation-delay:.4s;}
.qi-check{align-self:flex-start;display:flex;gap:7px;align-items:flex-start;font-size:12.8px;color:var(--amber);background:rgba(231,169,62,.1);border:1px solid rgba(231,169,62,.32);border-radius:10px;padding:9px 12px;line-height:1.5;}
.qi-apierr{margin-top:10px;font-size:12.5px;color:var(--amber);background:rgba(231,169,62,.09);border:1px solid rgba(231,169,62,.3);border-radius:9px;padding:10px 12px;line-height:1.5;}

.qi-inputrow{display:flex;gap:9px;margin-top:11px;}
.qi-input{flex:1;background:#0c1019;border:1px solid var(--line);border-radius:11px;padding:11px 14px;color:var(--text);font-family:var(--ui);font-size:13.5px;outline:0;transition:.15s;}
.qi-input:focus{border-color:var(--cyan);box-shadow:0 0 0 3px rgba(95,208,197,.12);}
.qi-send{border:0;background:linear-gradient(135deg,var(--cyan),#3fae9f);color:#08130f;width:44px;border-radius:11px;cursor:pointer;display:grid;place-items:center;transition:.15s;}
.qi-send:hover:not(:disabled){transform:translateY(-1px);}
.qi-send:disabled{opacity:.45;cursor:not-allowed;}

/* GLASS BOX */
.qi-glass{margin-top:15px;border:1px solid var(--line);border-radius:13px;background:linear-gradient(180deg,var(--ink3),var(--ink2));overflow:hidden;}
.qi-glass-head{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-bottom:1px solid var(--line);font-family:var(--disp);font-weight:600;font-size:14px;}
.qi-glass-tag{font-family:var(--mono);font-size:10px;letter-spacing:.08em;color:var(--cyan);background:rgba(95,208,197,.1);border:1px solid rgba(95,208,197,.28);padding:3px 8px;border-radius:20px;}
.qi-glass-empty{padding:16px 14px;font-size:12.8px;color:var(--muted);line-height:1.6;}
.qi-pipe{display:flex;flex-direction:column;}
.qi-stage{padding:11px 14px;border-bottom:1px solid var(--line);opacity:0;transform:translateY(6px);animation:rise .42s ease forwards;}
.qi-stage:last-child{border-bottom:0;}
.qi-stage-head{display:flex;align-items:center;gap:7px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:700;margin-bottom:7px;}
.qi-stage-head svg{color:var(--cyan);}
.qi-stage-body{font-size:13px;line-height:1.5;color:#dbe2ee;}
.qi-plan{color:#dbe2ee;}
.qi-readrow{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:6px;}
.qi-chip{font-size:11.5px;font-weight:600;padding:4px 10px;border-radius:20px;color:var(--ch,#fff);background:color-mix(in srgb,var(--ch,#888) 16%,transparent);border:1px solid color-mix(in srgb,var(--ch,#888) 45%,transparent);}
.qi-chip-iv{--ch:#cbd3e4;display:inline-flex;align-items:center;gap:5px;color:#e8edf6;background:var(--raise);border:1px solid var(--line2);}
.qi-why{font-size:11.8px;color:var(--muted);font-style:italic;}
.qi-conf{display:flex;align-items:center;gap:10px;font-size:11.8px;color:var(--muted);margin-bottom:5px;}
.qi-conf span{flex:none;}
.qi-conf-track{flex:1;height:7px;border-radius:6px;background:var(--ink);overflow:hidden;border:1px solid var(--line);}
.qi-conf-fill{height:100%;border-radius:6px;transition:width .6s cubic-bezier(.2,.7,.2,1);}
.qi-conf b{font-family:var(--mono);font-size:12px;color:var(--text);}
.qi-gov{font-size:12.8px;color:var(--muted);}
.qi-gov.flag{color:var(--amber);}
.qi-mem{display:flex;flex-direction:column;gap:7px;}
.qi-mem>div{display:flex;align-items:center;gap:7px;flex-wrap:wrap;}
.qi-mem-k{font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;text-transform:uppercase;padding:2px 7px;border-radius:5px;}
.qi-mem-k.ok{color:var(--green);background:rgba(123,216,143,.12);}
.qi-mem-k.shaky{color:var(--amber);background:rgba(231,169,62,.12);}
.qi-mem em{font-style:normal;font-size:12px;color:#dbe2ee;background:var(--ink);border:1px solid var(--line);padding:3px 9px;border-radius:7px;}
.qi-none{color:var(--faint);font-size:12px;}
.qi-lm{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:9px;padding-top:9px;border-top:1px solid var(--line);}
.qi-chip-lm{font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:20px;color:var(--muted);background:var(--ink);border:1px solid var(--line2);}
.qi-chip-revisit{display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:600;padding:3px 9px;border-radius:20px;color:var(--blue);background:rgba(106,163,255,.12);border:1px solid rgba(106,163,255,.4);}

@keyframes rise{from{opacity:0;transform:translateY(10px);}to{opacity:1;transform:translateY(0);}}
@keyframes blink{0%,60%,100%{opacity:.3;}30%{opacity:1;}}

/* ONBOARDING SCREEN */
.qi-onboard{position:relative;z-index:1;display:grid;place-items:center;min-height:100vh;padding:28px 20px;}
.qi-onboard-card{background:var(--ink2);border:1px solid var(--line);border-radius:20px;padding:36px 40px;max-width:520px;width:100%;display:flex;flex-direction:column;gap:18px;animation:rise .5s ease both;}
.qi-ob-logo{width:52px;height:52px;border-radius:14px;display:grid;place-items:center;color:#0a0d16;background:linear-gradient(135deg,var(--cyan),#3fae9f);box-shadow:0 6px 22px rgba(95,208,197,.3);}
.qi-ob-title{font-family:var(--disp);font-weight:600;font-size:26px;letter-spacing:.2px;margin:0;}
.qi-ob-sub{font-size:13px;color:var(--muted);margin:0;}
.qi-ob-label{display:flex;flex-direction:column;gap:8px;font-size:13px;font-weight:600;color:var(--text);}
.qi-ob-label small{color:var(--muted);font-weight:400;}
.qi-ob-consent{background:var(--ink3);border:1px solid var(--line);border-radius:12px;padding:14px 16px;}
.qi-ob-consent p{margin:0;font-size:13px;line-height:1.65;color:#cfd6e4;}
.qi-ob-consent em{font-style:normal;font-weight:600;color:var(--text);}
.qi-ob-btns{display:flex;flex-direction:column;gap:8px;}
.qi-ob-skip{border:1px solid var(--line);background:var(--ink3);color:var(--muted);font-family:var(--ui);font-size:13.5px;font-weight:600;padding:11px 18px;border-radius:11px;cursor:pointer;transition:.16s;}
.qi-ob-skip:hover:not(:disabled){color:var(--text);border-color:var(--line2);}
.qi-ob-skip:disabled{opacity:.5;cursor:not-allowed;}

/* DEMO-MODE BANNER */
.qi-demo-banner{position:relative;z-index:1;padding:9px 26px;background:rgba(231,169,62,.07);border-bottom:1px solid rgba(231,169,62,.22);font-size:12.5px;color:var(--amber);font-weight:600;text-align:center;letter-spacing:.01em;}
`;
