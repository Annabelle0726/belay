// SPDX-License-Identifier: AGPL-3.0-only
// Integration preview: UI rendering over verified identity and server-owned attempts.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const base = () => $("backend").value.replace(/\/$/, "");
  const assignedStance = new URL(window.location.href).searchParams.get("stance") || "peer";
  const stance = ["peer", "oracle", "control"].includes(assignedStance) ? assignedStance : "peer";
  let exercises = {}, dialogue, scope, identity, lastResult = null, busy = false;
  let temporaryMessages = [], recent = [], savedView = false;

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>]/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;"}[c]));
  }
  function renderSafeMarkdown(text) {
    if (!window.marked || !window.DOMPurify) return escapeHtml(text);
    const clean = window.DOMPurify.sanitize(window.marked.parse(String(text || "")), {
      USE_PROFILES: {html: true}
    });
    const container = document.createElement("div");
    container.innerHTML = clean;
    container.querySelectorAll("a").forEach(link => {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
    return container.innerHTML;
  }
  function bubble(message) {
    const feed = $("chat-feed");
    if (feed.children.length === 1 && feed.children[0].className === "chat-empty") feed.replaceChildren();
    const element = document.createElement("div");
    const student = message.role === "student";
    element.className = "bubble " + (student ? "bubble-user" : "bubble-tutor markdown-body");
    if (student) element.textContent = message.text;
    else element.innerHTML = renderSafeMarkdown(message.text);
    if (message.status && message.status !== "completed") {
      const state = document.createElement("div");
      state.className = "muted";
      state.textContent = message.status === "pending" ? "Awaiting reply…" : "Reply unfinished. Refresh before continuing.";
      element.appendChild(state);
    }
    feed.appendChild(element);
    feed.scrollTop = feed.scrollHeight;
  }
  function renderFeed(messages) {
    const feed = $("chat-feed");
    feed.replaceChildren();
    if (!messages.length) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.textContent = "— Conversation history will appear here —";
      feed.appendChild(empty);
    } else messages.forEach(bubble);
    feed.scrollTop = feed.scrollHeight;
  }
  function clearTelemetry() {
    for (const id of ["affect", "interv", "planner", "selfeval", "gov", "mem", "timings"]) {
      $(id).textContent = "—"; $(id).title = "";
    }
    $("confbar").style.width = "0%"; $("conf").textContent = "—";
  }
  function clearTransient() {
    temporaryMessages = []; recent = []; lastResult = null;
    $("question").value = ""; $("result").textContent = "Run your code to see its output.";
    clearTelemetry();
  }
  function renderHistory(messages, session) {
    if (!session.authorized) {
      identity = null; clearTransient(); renderFeed([]); return;
    }
    if (scope !== session.key || savedView !== session.enabled) clearTransient();
    scope = session.key; savedView = session.enabled; identity = session.config.identity;
    if (savedView) { clearTelemetry(); renderFeed(messages); }
    else renderFeed(temporaryMessages);
  }
  function telemetry(out) {
    out = out.live_signals || out;
    if (!out.components) { clearTelemetry(); return; }
    $("affect").textContent = "affect: " + (out.affective_state || "—");
    $("interv").textContent = "intervention: " + (out.intervention || "—");
    const confidence = typeof out.confidence === "number" ? Math.round(out.confidence * 100) : null;
    $("confbar").style.width = (confidence ?? 0) + "%";
    $("conf").textContent = confidence === null ? "—" : confidence + "%";
    $("planner").textContent = out.planner_note || "—";
    const selfEval = out.components.self_eval || {};
    $("selfeval").textContent = `${out.self_critique || "—"} (leak_risk=${selfEval.leak_risk ?? "—"})`;
    $("gov").textContent = out.components.governance?.prose || out.governance || "—";
    $("mem").textContent = `grasped: ${(out.memory?.grasped || []).join(", ") || "—"} | shaky: ${(out.memory?.shaky || []).join(", ") || "—"}`;
    $("timings").textContent = Object.entries(out.components.timings_ms || {}).map(([k,v]) => `${k}=${v}`).join(" ") || "—";
  }
  async function json(path, body) {
    const response = await fetch(base() + path, {
      method: body === undefined ? "GET" : "POST",
      headers: await window.BelayAuth.headers(base()),
      ...(body === undefined ? {} : {body: JSON.stringify({ ...body,
        ...(identity ? {institution_id: identity.institution_id, class_id: identity.class_id} : {})
      })})
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 404) {
        identity = null; clearTransient(); renderFeed([]);
      }
      throw new Error(`Request failed (${response.status}). Check authentication and assignment access.`);
    }
    return response.json();
  }
  function setBusy(value) {
    busy = value;
    for (const id of ["ask", "run", "exercise", "backend", "mode"]) $(id).disabled = value;
  }
  function pick() {
    clearTransient(); renderFeed([]);
    const exercise = exercises[$("exercise").value];
    $("prompt").textContent = exercise?.prompt || "No authorized exercises available.";
    $("source").value = exercise?.starter || "";
    if (dialogue && exercise) dialogue.refresh();
  }
  async function loadCurriculum() {
    try {
      const data = await json("/api/curriculum");
      exercises = {}; $("exercise").replaceChildren();
      data.modules.forEach(module => module.exercises.forEach(exercise => {
        exercises[exercise.id] = exercise;
        const option = document.createElement("option");
        option.value = exercise.id; option.textContent = exercise.title;
        $("exercise").appendChild(option);
      }));
      pick();
      if (!dialogue && Object.keys(exercises).length) {
        dialogue = window.BelayConversations.mount({
          container: $("conversation-controls"), base, exercise: () => $("exercise").value,
          renderHistory, compact:true
        });
      }
      $("status").textContent = "";
    } catch (error) {
      identity = null; clearTransient(); renderFeed([]);
      $("status").textContent = "Curriculum load failed: " + error.message;
    }
  }
  async function run() {
    if (busy) return false;
    setBusy(true); $("status").textContent = "Running…";
    lastResult = null; $("result").textContent = "Running your code…";
    try {
      const learner = identity?.learner_id || window.BELAY_LEARNER_ID;
      lastResult = await json("/api/run", {participant_id: learner,
        exercise_id: $("exercise").value, source: $("source").value});
      renderRunResult(lastResult);
      $("status").textContent = lastResult.ok ? "Run completed." : "Run failed.";
      return !!lastResult.ok;
    } catch (error) {
      lastResult = null; $("status").textContent = error.message;
      $("result").textContent = "Could not run your code. " + error.message;
      return false;
    } finally { setBusy(false); }
  }
  function renderRunResult(result) {
    const target = $("result"), pack = result.pack || {};
    target.replaceChildren();
    const status = document.createElement("p"); status.className = "run-status";
    status.textContent = !result.ok ? "Your code could not finish." :
      result.goalMet === true ? "Code ran successfully. Exercise checks passed." :
      result.goalMet === false ? "Code ran. Some exercise checks need attention." : "Code ran successfully.";
    target.appendChild(status);
    const output = document.createElement("pre"); output.className = "run-stdout";
    output.textContent = typeof pack.stdout === "string" && pack.stdout.length ? pack.stdout :
      "No printed output. Use print(...) to display a result.";
    target.appendChild(output);
    if (result.error) {
      const error = document.createElement("pre"); error.className = "run-error";
      error.textContent = result.error; target.appendChild(error);
    }
    const checks = Array.isArray(pack.checks) ? pack.checks : [];
    if (checks.length) {
      const details = document.createElement("details"), summary = document.createElement("summary");
      summary.textContent = `Check details · ${checks.filter(c => c.ok).length}/${checks.length} passed`;
      details.appendChild(summary);
      checks.forEach((check, index) => {
        const item = document.createElement("p");
        item.textContent = `Check ${index + 1}: ${check.ok ? "Passed" : "Needs attention"}` +
          (typeof check.detail === "string" && check.detail ? " — " + check.detail : "");
        details.appendChild(item);
      });
      target.appendChild(details);
    } else if (typeof pack.summary === "string") {
      const summary = document.createElement("p"); summary.textContent = pack.summary; target.appendChild(summary);
    }
  }
  async function ask(event = "chat") {
    if (busy || !dialogue) return;
    const typed = $("question").value.trim();
    const message = typed || (event === "run" ? "Help me understand the result of this run." : "Help me understand this code.");
    const originalScope = scope;
    setBusy(true); $("status").textContent = "Sol is thinking…";
    try {
      const input = {message, source: $("source").value, result: lastResult,
        mode: $("mode").value, stance};
      let out = await dialogue.send(input);
      if (originalScope && originalScope !== scope) throw new Error("Identity changed; enter a new question.");
      if (!out) {
        // Unsaved history stays in RAM, in the legacy edge's who/text format.
        const current = {who: "student", text: message};
        out = await json("/api/sol/turn", {
          participant_id: identity.learner_id, exercise_id: $("exercise").value,
          event, mode: input.mode, stance: input.stance, source: input.source, result: input.result,
          recent: [...recent.slice(-10), current]
        });
        const reply = out.message + (out.check_question ? "\n\n" + out.check_question : "");
        recent = [...recent, current, {who: "sol", text: reply}].slice(-12);
        temporaryMessages.push({role: "student", text: message}, {role: "assistant", text: reply});
        // Keep the transient feed bounded as well; nothing is written to storage.
        temporaryMessages = temporaryMessages.slice(-200);
        renderFeed(temporaryMessages);
      } else if (out.history_unavailable) {
        // Successful live delivery remains visible when the history request fails.
        bubble({role: "student", text: message});
        bubble({role: "assistant", text: out.message + (out.check_question ? "\n\n" + out.check_question : "")});
      } else if (out.unsaved_exchange) {
        // The live support response is transient; restored history has placeholders.
        bubble({role: "assistant", text: out.message + (out.check_question ? "\n\n" + out.check_question : "")});
      }
      telemetry(out); $("question").value = ""; $("status").textContent = "";
    } catch (error) { $("status").textContent = error.message; }
    finally { setBusy(false); }
  }
  $("exercise").addEventListener("change", pick);
  $("backend").addEventListener("change", loadCurriculum);
  $("run").addEventListener("click", async () => { if (await run()) await ask("run"); });
  $("ask").addEventListener("click", () => ask());
  $("question").addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); ask(); }
  });
  window.addEventListener("belay-auth-changed", () => {
    identity = null; scope = null; clearTransient(); renderFeed([]);
  });
  loadCurriculum();
})();
