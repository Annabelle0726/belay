// SPDX-License-Identifier: AGPL-3.0-only
// Integration preview: UI rendering over verified identity and server-owned attempts.
(function () {
  "use strict";
  const $ = id => document.getElementById(id);
  const base = () => $("backend").value.replace(/\/$/, "");
  const glassBox = $("glass-box"), signalsStorage = $("signals-storage");
  const assignedStance = new URL(window.location.href).searchParams.get("stance") || "peer";
  const stance = ["peer", "oracle", "control"].includes(assignedStance) ? assignedStance : "peer";
  let exercises = {}, dialogue, scope, identity, lastResult = null, busy = false, generation = 0;
  const askJobs = globalThis.belayAskJobs();
  let temporaryMessages = [], recent = [], savedView = false;
  let historyContext = null, liveContext = null;
  let localBusy = false, sessionBusy = false;
  let records = [], activeRecord = null, feedMessages = [], requestTarget = null;
  let savedConversation = null, glassOwner = null;

  function startRecord(event) {
    const record = {event, source:$("source").value, question:$("question").value.trim(),
      execution:event === "run" ? "running" : "not_run", feedback:"not_submitted", messages:[]};
    records.push(record); activeRecord = record; requestTarget = record;
    clearTelemetry(); renderFeed(feedMessages);
    return record;
  }
  function requestState(state, ref) {
    if (!ref?.request_id) return;
    if (ref.error) {recordFailure(ref.error, null); return;}
    let record = records.find(r => r.request_id === ref.request_id);
    if (!record) {
      record = !ref.recovered && requestTarget && !requestTarget.request_id
        ? requestTarget : {messages:[], execution:"not_retained", restored:true};
      if (!records.includes(record)) records.push(record);
      record.request_id = ref.request_id;
    }
    record.job_id = ref.job_id || record.job_id;
    record.feedback = state;
    if (state === "completed") {record.note = ""; record.code = null;}
    if (ref.recovered && requestTarget && requestTarget !== record) {
      requestTarget.feedback = "not_submitted";
      requestTarget.note = "No new feedback submitted. The original request is being recovered in its own record.";
    }
    renderFeed(feedMessages);
  }
  function recordFailure(error, fallback) {
    const record = records.find(r => r.request_id === error.request_id) || fallback;
    if (!record) return;
    record.feedback = error.uncertain ? "unknown" : error.code === "result_expired" ? "result_expired" : "blocked";
    record.note = error.message;
    record.code = error.code;
    renderFeed(feedMessages);
  }

  function escapeHtml(text) {
    return String(text || "").replace(/[&<>]/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;"}[c]));
  }
  function renderSafeMarkdown(text) {
    if (!window.marked || !window.DOMPurify) return escapeHtml(text);
    const policy = {USE_PROFILES: {html: true}, FORBID_TAGS: ["style"], FORBID_ATTR: ["style"]};
    const clean = window.DOMPurify.sanitize(window.marked.parse(String(text || "")), policy);
    const container = document.createElement("div");
    container.innerHTML = clean;
    container.querySelectorAll("a").forEach(link => {
      const href = link.getAttribute("href");
      if (href) {
        try {
          if (!["http:", "https:", "mailto:"].includes(new URL(href, window.location.href).protocol))
            link.removeAttribute("href");
        } catch { link.removeAttribute("href"); }
      }
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    });
    container.querySelectorAll("pre code").forEach(code => {
      const language = /(?:^|\s)language-([\w-]+)/.exec(code.className)?.[1];
      if (language && window.hljs?.getLanguage(language)) {
        // Highlight literal code only; sanitize generated spans before insertion.
        code.innerHTML = window.DOMPurify.sanitize(window.hljs.highlight(code.textContent,
          {language, ignoreIllegals:true}).value, policy);
      }
    });
    return container.innerHTML;
  }
  function bubble(message, feed = $("chat-feed")) {
    if (feed.children.length === 1 && feed.children[0].className === "chat-empty") feed.replaceChildren();
    const element = document.createElement("div");
    const student = message.role === "student";
    element.className = "bubble " + (student ? "bubble-user" : "bubble-tutor markdown-body");
    if (!student && (!window.marked || !window.DOMPurify)) element.className += " markdown-plain";
    if (student) element.textContent = message.text;
    else element.innerHTML = renderSafeMarkdown(message.text);
    feed.appendChild(element);
    feed.scrollTop = feed.scrollHeight;
  }
  function renderFeed(messages) {
    feedMessages = messages;
    const feed = $("chat-feed");
    if (glassBox) signalsStorage.appendChild(glassBox);
    feed.replaceChildren();
    // Operation notices live inside their own group, never below an unrelated reply.
    $("status").hidden = records.length > 0;
    const unassociated = [];
    for (const message of messages) {
      if (!message.request_id) {unassociated.push(message); continue;}
      let record = records.find(r => r.request_id === message.request_id);
      if (!record) {
        record = {request_id:message.request_id, messages:[], restored:true, execution:"not_retained"};
        records.push(record);
      }
      // Saved server sequence is stable across refresh/pagination; no positional pairing.
      const index = record.messages.findIndex(m => message.sequence != null
        ? m.sequence === message.sequence || (m.sequence == null && m.role === message.role)
        : m.role === message.role);
      if (index < 0) record.messages.push(message); else record.messages[index] = message;
    }
    function draw(record) {
      const group = document.createElement("section"); group.className = "request-record";
      group.setAttribute("aria-label", "Run and tutor feedback record");
      group.setAttribute("data-feedback-state", record.feedback || "restored");
      if (record.request_id) group.setAttribute("data-request-id", record.request_id);
      if (record.question && record.request_id && !record.messages.some(m => m.role === "student"))
        bubble({role:"student", text:record.question}, group);
      record.messages.forEach(m => bubble(m, group));
      const status = document.createElement("p"); status.className = "feedback-state";
      status.setAttribute("role", "note");
      status.setAttribute("aria-label", "System notice");
      const hasAnswer = record.messages.some(m => m.role === "assistant" && (!m.status || m.status === "completed"));
      status.textContent = record.code === "result_expired"
        ? "This response can no longer be restored. For a new response, enter a question and choose Ask Sol."
        : record.note ? "Tutor feedback: " + record.note :
        !hasAnswer && record.feedback === "not_submitted" && record.execution !== "running" && !(record === activeRecord && busy)
          ? "No tutor feedback submitted for this operation." : "";
      if (record === glassOwner && record === activeRecord && hasAnswer && glassBox) group.appendChild(glassBox);
      group.appendChild(status); feed.appendChild(group);
    }
    const sequence = r => Math.min(...r.messages.map(m => m.sequence).filter(Number.isInteger));
    const historical = records.filter(r => r !== activeRecord).sort((a, b) =>
      Number.isFinite(sequence(a)) && Number.isFinite(sequence(b)) ? sequence(a) - sequence(b) : 0);
    if (unassociated.length || historical.length) {
      unassociated.forEach(m => bubble(m)); historical.forEach(draw);
      const boundary = document.createElement("div"); boundary.className = "history-boundary";
      const line = document.createElement("hr"), label = document.createElement("p");
      label.textContent = "Conversation history";
      boundary.appendChild(line); boundary.appendChild(label); feed.appendChild(boundary);
    }
    if (activeRecord) {
      const current = document.createElement("p"); current.className = "request-label";
      current.textContent = "Current feedback"; feed.appendChild(current); draw(activeRecord);
    }
    if (!messages.length && !records.length) {
      const empty = document.createElement("div");
      empty.className = "chat-empty";
      empty.textContent = "— Conversation history will appear here —";
      feed.appendChild(empty);
    }
    feed.scrollTop = feed.scrollHeight;
  }
  function clearTelemetry() {
    liveContext = null; glassOwner = null;
    const box = glassBox;
    if (box) {box.open = false; $("signals-storage").appendChild(box);}
    $("glass-evidence").textContent = "";
    $("glass-approach").textContent = "";
  }
  function clearTransient() {
    records = []; activeRecord = null; requestTarget = null; feedMessages = [];
    temporaryMessages = []; recent = []; lastResult = null;
    $("status").textContent = "";
    $("question").value = ""; $("result").textContent = "Run your code to see its output.";
    clearTelemetry();
  }
  function renderHistory(messages, session) {
    if (!session.authorized) {
      identity = null; clearTransient(); renderFeed([]); return;
    }
    if (scope !== session.key || savedView !== session.enabled) clearTransient();
    else if (savedView && savedConversation !== session.cid) {
      records = []; activeRecord = null; requestTarget = null; feedMessages = [];
    }
    savedConversation = session.cid;
    scope = session.key; savedView = session.enabled; identity = session.config.identity;
    historyContext = JSON.stringify([session.key, session.cid, session.revision]);
    if (savedView) {
      if (liveContext !== historyContext) clearTelemetry(messages.length
        ? "Saved replies restored. Explanations from earlier replies are not saved."
        : undefined);
      renderFeed(messages);
    }
    else renderFeed(temporaryMessages);
  }
  function telemetry(out, owner = activeRecord) {
    const explanation = out.glass_box;
    if (!explanation || typeof explanation.evidence !== "string" || typeof explanation.approach !== "string") {
      clearTelemetry();
      return;
    }
    if (!owner || owner !== activeRecord || owner.feedback === "unknown") return;
    glassOwner = owner; if (glassBox) glassBox.open = false;
    liveContext = historyContext;
    $("glass-evidence").textContent = explanation.evidence;
    $("glass-approach").textContent = explanation.approach;
    renderFeed(feedMessages);
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
    localBusy = value;
    updateBusy();
  }
  function updateBusy() {
    const next = localBusy || sessionBusy;
    if (next !== busy) $("feedback-announcement").textContent = next ? "Preparing tutor feedback." : "Processing finished.";
    busy = next;
    $("chat-feed").setAttribute("aria-busy", String(busy));
    $("feedback-loading").hidden = !busy;
    for (const id of ["ask", "run", "exercise", "backend", "mode"]) $(id).disabled = busy;
  }
  function pick() {
    generation++;
    clearTransient(); renderFeed([]);
    const exercise = exercises[$("exercise").value];
    $("prompt").textContent = exercise?.prompt || "No authorized exercises available.";
    $("source").value = exercise?.starter || "";
    if (dialogue && exercise) dialogue.refresh().then(recoverUnsaved);
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
          renderHistory, compact:true, quietProgress:true,
          onRequest: requestState,
          onProcessing: value => { sessionBusy = value; updateBusy(); }
        });
      }
      $("status").textContent = "";
      await recoverUnsaved();
    } catch (error) {
      identity = null; clearTransient(); renderFeed([]);
      $("status").textContent = "Curriculum load failed: " + error.message;
    }
  }
  async function run() {
    if (busy) return false;
    const record = startRecord("run");
    setBusy(true); $("status").textContent = "";
    lastResult = null; $("result").textContent = "Running your code…";
    try {
      const learner = identity?.learner_id || window.BELAY_LEARNER_ID;
      lastResult = await json("/api/run", {participant_id: learner,
        exercise_id: $("exercise").value, source: $("source").value});
      renderRunResult(lastResult);
      const studentError = lastResult.pack?.execution_status === "student_error";
      record.result = lastResult;
      record.execution = lastResult.ok ? (lastResult.goalMet === false ? "checks_failed" : "completed")
        : studentError ? "student_error" : lastResult.pack?.timed_out ? "timeout" : "infrastructure_error";
      if (!lastResult.ok && !studentError) record.note = lastResult.pack?.timed_out
        ? "Code execution timed out. No tutor feedback was submitted."
        : "Code execution is unavailable. No tutor feedback was submitted.";
      renderFeed(feedMessages);
      $("status").textContent = lastResult.ok ? "Run completed." : studentError
        ? "Your code raised an error. Requesting tutor feedback."
        : "Code execution could not finish. No tutor feedback was submitted.";
      return !!lastResult.ok || studentError;
    } catch (error) {
      record.execution = "unknown"; record.note = "Code execution result not confirmed. No tutor feedback submitted.";
      renderFeed(feedMessages);
      lastResult = null; $("status").textContent = error.message;
      $("result").textContent = "Could not run your code. " + error.message;
      return false;
    } finally { setBusy(false); }
  }
  function renderRunResult(result, target = $("result")) {
    const pack = result.pack || {};
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
      details.open = true;
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
    const record = event === "run" ? activeRecord : startRecord("chat");
    requestTarget = record;
    const typed = $("question").value.trim();
    const message = typed || (event === "run" ? "Help me understand the result of this run." : "Help me understand this code.");
    const originalScope = scope, requestGeneration = generation;
    setBusy(true); $("status").textContent = "";
    try {
      const input = {message, source: $("source").value, result: lastResult,
        mode: $("mode").value, stance};
      let out = await dialogue.send(input);
      if (originalScope && originalScope !== scope) throw new Error("Identity changed; enter a new question.");
      if (!out) {
        // Unsaved history stays in RAM, in the legacy edge's who/text format.
        const current = {who: "student", text: message};
        out = await askJobs.ask(base(), "/api/sol/jobs", {
          participant_id: identity.learner_id, exercise_id: $("exercise").value,
          event, mode: input.mode, stance: input.stance, source: input.source, result: input.result,
          recent: [...recent.slice(-10), current]
        }, (state, config, ref) => {
          if (requestGeneration === generation && originalScope === scope) requestState(state, ref);
        });
        if (requestGeneration !== generation || originalScope !== scope) throw new Error("Identity or exercise changed; previous reply was discarded.");
        const reply = out.message + (out.check_question ? "\n\n" + out.check_question : "");
        const recovered = askJobs.wasRecovered(out);
        const ref = askJobs.reference(out);
        const owner = records.find(r => r.request_id === ref?.request_id) || record;
        if (!recovered) recent = [...recent, current, {who: "sol", text: reply}].slice(-12);
        if (!recovered) temporaryMessages.push({role:"student", text:message, request_id:owner.request_id});
        temporaryMessages.push({role:"assistant", text:reply, request_id:owner.request_id});
        // Keep the transient feed bounded as well; nothing is written to storage.
        temporaryMessages = temporaryMessages.slice(-200);
        renderFeed(temporaryMessages);
        askJobs.acknowledge(out);
        out.recovered_request = recovered;
      } else if (out.history_unavailable) {
        // Successful live delivery remains visible when the history request fails.
        const owner = records.find(r => r.request_id === out.request_id) || record;
        owner.messages = [{role: "student", text: message},
          {role: "assistant", text: out.message + (out.check_question ? "\n\n" + out.check_question : "")}];
        renderFeed(feedMessages);
      } else if (out.unsaved_exchange) {
        // The live support response is transient; restored history has placeholders.
        record.messages.push({role: "assistant", text: out.message + (out.check_question ? "\n\n" + out.check_question : "")});
        renderFeed(feedMessages);
      }
      const completedOwner = out.request_id && records.find(r => r.request_id === out.request_id);
      if (completedOwner) {completedOwner.feedback = "completed"; completedOwner.note = ""; renderFeed(feedMessages);}
      if (out.recovered_request) clearTelemetry("An earlier request was recovered. No new tutor reply was generated.");
      else telemetry(out);
      if (!out.recovered_request) $("question").value = "";
      $("ask").textContent = "Ask Sol";
      $("status").textContent = out.recovered_request
        ? (event === "run" ? "Code ran. Recovered the previous tutor reply; no feedback for this run was submitted."
          : "Recovered the original request. Your current input was not submitted.") : "";
    } catch (error) {
      if (requestGeneration === generation) {
        recordFailure(error, record);
        let message = error.message;
        if (event === "run" && error.code !== "result_expired") {
          const context = error.notSubmitted ? "No new tutor feedback was submitted. "
            : error.recovered_request ? "A previous tutor request is unresolved; no feedback for this run was submitted. "
            : "Tutor feedback: ";
          message = (lastResult?.ok ? "Code ran. " : "Your code raised an error. ") + context + message;
        }
        $("status").textContent = message;
        $("ask").textContent = error.uncertain ? "Check request status" : "Ask Sol";
      }
    }
    finally { setBusy(false); }
  }
  async function recoverUnsaved() {
    if (!dialogue || busy) return;
    const current = generation;
    let session;
    try { session = await dialogue.ready(); }
    catch (error) { if (current === generation) $("status").textContent = error.message; return; }
    // Initialization establishes the authorized scope; capture it after ready.
    const currentScope = session.key;
    if (current !== generation || currentScope !== scope || session.enabled || busy) return;
    setBusy(true);
    try {
      const answer = await askJobs.recover(base(), "/api/sol/jobs", $("exercise").value,
        (state, config, ref) => {if (current === generation && currentScope === scope) requestState(state, ref);});
      if (current !== generation || currentScope !== scope) return;
      if (answer) {
        const ref = askJobs.reference(answer);
        temporaryMessages = [...temporaryMessages, {role:"assistant", request_id:ref?.request_id,
          text:answer.message + (answer.check_question ? "\n\n" + answer.check_question : "")}];
        renderFeed(temporaryMessages);
        clearTelemetry("An earlier request was recovered. No new tutor reply was generated.");
        askJobs.acknowledge(answer);
        $("status").textContent = "Recovered the same request. No request was resubmitted.";
      }
    } catch (error) { if (current === generation) {recordFailure(error, null); $("status").textContent = error.message;} }
    finally { setBusy(false); }
  }
  $("exercise").addEventListener("change", pick);
  $("backend").addEventListener("change", loadCurriculum);
  $("run").addEventListener("click", async () => { if (await run()) await ask("run"); });
  $("ask").addEventListener("click", () => ask());
  $("glass-correct").addEventListener("click", () => {
    if (busy) return;
    const question = $("question");
    if (!question.value.trim()) question.value = "Correction: ";
    question.focus?.();
  });
  $("question").addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.isComposing) { event.preventDefault(); ask(); }
  });
  window.addEventListener("belay-auth-changed", () => {
    generation++; identity = null; scope = null; clearTransient(); renderFeed([]);
  });
  loadCurriculum();
})();
