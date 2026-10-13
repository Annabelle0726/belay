/* SPDX-License-Identifier: AGPL-3.0-only
 * Only attempt pointers/preferences persist in the browser. No tokens or transcripts.
 */
(function () {
  "use strict";
  const uuid = () => window.crypto.randomUUID();
  class Session {
    constructor({base, prefix = "/api", exercise, onChange = () => {}, onProcessing = () => {}, onRequest = () => {}, quietProgress = false}) {
      this.base = base.replace(/\/$/, ""); this.prefix = prefix; this.exercise = exercise;
      this.onChange = onChange; this.messages = []; this.before = null;
      this.onProcessing = onProcessing; this.quietProgress = quietProgress;
      this.onRequest = onRequest;
      this.cid = null; this.revision = 0; this.pending = null; this.enabled = false;
      this.jobs = globalThis.belayAskJobs?.(); this.sending = false; this.generation = 0;
    }
    notify(note) { this.note = note; this.onChange(this); }
    async json(path, method = "GET", body) {
      let timer, expired = false;
      const deadline = new Promise((_, reject) => {timer = setTimeout(() => {
        expired = true; reject(globalThis.belayRequestError("request_timeout", true));
      }, 90000);});
      try {
        return await Promise.race([deadline, (async () => {
          const headers = await window.BelayAuth.headers(this.base);
          if (expired) throw globalThis.belayRequestError("request_timeout", true);
          return globalThis.belayRequestJSON(this.base + this.prefix + "/conversations" + path, {
            method, headers, ...(body === undefined ? {} : {body:JSON.stringify(body)})
          });
        })()]);
      } catch (error) {
        if (error.status === 404) error.message = "Saved history is unavailable, expired or deleted.";
        if (error.status === 409) error.message = "The attempt changed or a turn is unfinished. Refresh before continuing.";
        if (error.status === 401 || error.status === 404) {
          // An absent attempt does not by itself revoke the authenticated session.
          if (error.status === 401 || path === "/config") this.authorized = false;
          this.messages = []; this.before = null;
          if (error.status === 404 && this.cid) { this.cid = null; this.write({enabled:this.enabled}); }
          this.notify(error.message);
        }
        throw error;
      } finally {expired = true; clearTimeout(timer);}
    }
    read() {
      try { return JSON.parse(window.localStorage.getItem(this.key)) || {}; } catch { return {}; }
    }
    write(value) {
      try { window.localStorage.setItem(this.key, JSON.stringify(value)); }
      catch { this.notify("Browser storage is unavailable; restoration needs this attempt ID: " + (this.cid || "")); }
    }
    async scope() {
      const wasAuthorized = this.authorized;
      const config = await this.json("/config");
      this.authorized = true;
      const identity = config.identity;
      const version = config.assignments[this.exercise];
      if (!version) {
        this.authorized = false; this.messages = [];
        this.notify("This exercise version is unavailable.");
        throw new Error("This exercise version is unavailable.");
      }
      const key = "belay-attempt-v1:" + JSON.stringify([this.base, this.prefix, identity.institution_id,
        identity.class_id, identity.learner_id, this.exercise, version]);
      const changed = key !== this.key;
      if (changed) {
        this.key = key; this.cid = null; this.messages = []; this.before = null; this.pending = null;
        this.revision = 0; this.activePending = false;

      }
      this.config = config; this.version = version;
      this.cid = this.read().cid || this.cid;
      this.enabled = config.enabled && this.read().enabled === true;
      if (changed) this.notify("Identity or exercise changed; loading authorized history.");
      else if (!wasAuthorized) this.notify("Authorized session refreshed.");
      return config;
    }
    async initialize() {
      try {
        await this.scope();
        if (this.enabled) {
          try { await this.restore(false); }
          catch (error) { if (error.status !== 404 || !this.authorized) throw error; }
        }
        else this.notify(this.config.enabled ? "Saving is optional. Enable it to resume this attempt after refresh." :
          "This conversation is unsaved. Course tutoring remains available.");
      } catch (error) { this.authorized = false; this.messages = []; this.notify(error.message); throw error; }
    }
    async setSaving(enabled) {
      this.generation++;
      await this.scope();
      if (enabled && !this.config.enabled) throw new Error("Dialogue saving is disabled.");
      this.write({...this.read(), enabled}); this.enabled = enabled;
      this.pending = null; this.messages = []; this.before = null;
      if (enabled) {
        if (this.read().cid || this.read().createRequest) await this.restore(false);
        else await this.newAttempt(false);
      } else this.notify("New turns are unsaved. Previously saved history remains until expiry or deletion.");
    }
    async createReserved(record) {
      const attempt = await this.json("", "POST", {exercise_id: this.exercise, exercise_version: this.version,
        save: true, request_id: record.createRequest});
      this.cid = attempt.conversation_id; this.revision = attempt.revision;
      this.write({enabled:true, cid:this.cid});
      this.messages = []; this.before = null; this.activePending = false;
      this.notify("New saved attempt. History expires from its creation time.");
    }
    async newAttempt(checkScope = true) {
      this.generation++;
      if (checkScope) await this.scope();
      if (!this.enabled) throw new Error("Enable optional saving first.");
      const previous = this.read();
      const record = {enabled:true, createRequest:uuid()};
      this.pending = null; this.write(record);
      try { await this.createReserved(record); }
      catch (error) { if (error.status) this.write(previous); throw error; }
    }
    async restore(checkScope = true, recoverJob = true) {
      if (checkScope) { this.pending = null; await this.scope(); }
      if (!this.enabled) return;
      const record = this.read();
      if (record.createRequest && !record.cid) return this.createReserved(record);
      this.cid = record.cid;
      if (!this.cid) { this.notify("Choose New attempt to start saving."); return; }
      try {
        const page = await this.json("/" + encodeURIComponent(this.cid) + "/messages");
        this.messages = page.messages; this.before = page.before; this.revision = page.revision;
        this.activePending = page.pending;
        this.notify(page.pending && !(this.quietProgress && this.config.controlled && this.jobs && recoverJob)
          ? "A turn is unfinished. Check its request status before continuing." : "Saved history restored.");
        if (this.config.controlled && this.jobs && recoverJob) {
          const cid = this.cid, generation = this.generation, key = this.key, grant = this.config.recovery_scope;
          this.onProcessing(true);
          try {
            const result = await this.jobs.recover(this.base, this.jobsPrefix(), this.exercise,
              (state, config, ref) => { if (this.cid === cid && generation === this.generation) {
                this.onRequest(state, ref); this.notify(this.jobNote(state));
              }});
            await this.scope();
            if (cid !== this.cid || generation !== this.generation || key !== this.key || grant !== this.config.recovery_scope)
              throw new Error("Attempt or identity changed; previous reply was discarded.");
            if (result) {
              if (result.conversation_id !== cid || !Number.isInteger(result.revision) || result.revision < 2)
                throw globalThis.belayRequestError("invalid_response", true);
              await this.restore(false, false);
              this.jobs.acknowledge(result);
              this.notify("Saved request recovered. History restored; no request was resubmitted.");
            }
          } catch (error) {
            if (error.request_id) this.onRequest("error", {request_id:error.request_id, recovered:true,
              error});
            if (error.status === 401 || error.status === 404) {
              try {await this.scope(); await this.json("/" + encodeURIComponent(cid));}
              catch (denied) {error = denied; this.messages = []; this.before = null;}
            }
            if (["conversation_unavailable", "authorization_revoked"].includes(error.code)) {
              this.messages = []; this.before = null; this.cid = null; this.write({enabled:this.enabled});
            }
            this.notify(error.message);
            // Unknown pointers remain in storage; a new click only queries them.
          } finally { this.onProcessing(false); }
        }
      } catch (error) {
        if (error.request_id) this.onRequest("error", {request_id:error.request_id, error});
        this.messages = []; this.before = null; this.pending = null;
        if (error.status === 404) {
          this.cid = null; this.write({enabled:true});
          // Recheck membership before allowing recovery from an absent resource.
          await this.scope();
          error.message += " Choose New attempt, or turn saving off to continue unsaved.";
        }
        this.notify(error.message); throw error;
      }
    }
    async older() {
      await this.scope();
      if (!this.enabled || !this.cid || !this.before) return;
      const page = await this.json("/" + encodeURIComponent(this.cid) + "/messages?before=" + encodeURIComponent(this.before));
      this.messages = [...page.messages, ...this.messages]; this.before = page.before;
      this.notify("Older saved messages loaded.");
    }
    jobsPrefix() { return this.prefix + "/conversations/" + encodeURIComponent(this.cid) + "/jobs"; }
    jobNote(state) {
      if (this.quietProgress && ["preparing", "queued", "running"].includes(state)) return "";
      return {preparing:"Checking request status…", queued:"Waiting for a worker…", running:"Sol is working…",
        unknown:"The request outcome is unknown. Checking it will not submit again.", completed:"Reply completed."}[state] || "Checking request status…";
    }
    async controlledSend(input) {
      if (!this.jobs) throw new Error("Controlled request client is unavailable.");
      if (this.sending) throw new Error("A request is already being checked.");
      this.sending = true;
      this.onProcessing(true);
      const cid = this.cid, key = this.key, generation = this.generation, grant = this.config.recovery_scope;
      try {
        const result = await this.jobs.ask(this.base, this.jobsPrefix(), {...input,
          exercise_id:this.exercise, expected_revision:this.revision},
          (state, config, ref) => { if (cid === this.cid && generation === this.generation) {
            this.onRequest(state, ref); this.notify(this.jobNote(state));
          }});
        await this.scope();
        if (cid !== this.cid || key !== this.key || generation !== this.generation || grant !== this.config.recovery_scope)
          throw new Error("Attempt or identity changed; previous reply was discarded.");
        if (result.conversation_id !== cid || !Number.isInteger(result.revision) || result.revision < 2)
          throw globalThis.belayRequestError("invalid_response", true);
        this.revision = result.revision;
        let historyUnavailable = false;
        try { await this.restore(false, false); }
        catch (error) {
          if (!this.authorized || error.status === 404) throw error;
          historyUnavailable = true;
          this.notify("Reply completed. Refresh to reload saved history.");
        }
        this.jobs.acknowledge(result);
        return {...result, request_id:this.jobs.reference(result)?.request_id,
          recovered_request:this.jobs.wasRecovered(result), history_unavailable:historyUnavailable};
      } catch (error) {
        if (error.status === 401 || error.status === 404 || error.code === "result_expired") {
          try {await this.restore(true, false);} catch (denied) {error = denied;}
        }
        this.notify(error.message); throw error;
      } finally { this.sending = false; this.onProcessing(false); }
    }
    async send(input) {
      const previousKey = this.key;
      await this.scope();
      if (previousKey && previousKey !== this.key) throw new Error("Identity changed; refresh before sending a new message.");
      if (!this.enabled || !this.cid) throw new Error("Choose a saved attempt before sending.");
      if (this.config.controlled) return this.controlledSend(input);
      if (this.activePending) throw new Error("A turn is unfinished; refresh before continuing.");
      const signature = JSON.stringify(input);
      if (this.pending && this.pending.signature !== signature) throw new Error("Retry the previous message or refresh before a new one.");
      if (!this.pending) this.pending = {signature, body: {...input, request_id:uuid(), expected_revision:this.revision}};
      this.onRequest("preparing", {request_id:this.pending.body.request_id});
      try {
        const attemptId = this.cid;
        const requestId = this.pending.body.request_id;
        const result = await this.json("/" + encodeURIComponent(attemptId) + "/turns", "POST", this.pending.body);
        if (this.cid !== attemptId || this.key !== previousKey) throw new Error("Attempt changed; previous reply was discarded.");
        this.pending = null;
        this.revision = result.revision;
        let historyUnavailable = false;
        try { await this.restore(false); }
        catch (error) {
          if (!this.authorized || error.status === 404) throw error;
          historyUnavailable = true;
          this.notify("Turn completed; refresh to reload saved history.");
        }
        if (result.unsaved_exchange) this.notify("This exchange was not saved; only neutral placeholders will restore.");
        return {...result.response, request_id:requestId, glass_box:result.glass_box, reply_to:result.reply_to, history_unavailable:historyUnavailable,
          unsaved_exchange: !!result.unsaved_exchange};
      } catch (error) {
        if (this.pending) error.request_id = this.pending.body.request_id;
        if (error.status) this.pending = null;
        if (error.status === 404) { this.cid = null; this.messages = []; this.write({enabled:true}); }
        if (error.status === 401 || error.status === 404) this.messages = [];
        this.notify(error.message); throw error;
      }
    }
    async remove() {
      this.generation++;
      await this.scope();
      if (!this.cid) return;
      await this.json("/" + encodeURIComponent(this.cid), "DELETE");
      this.cid = null; this.messages = []; this.before = null; this.pending = null;
      this.write({enabled:this.enabled}); this.notify("Saved attempt deleted. Choose New attempt to continue saving.");
    }
  }
  function mount({container, base, exercise, prefix = "/api", renderHistory, compact = false,
    onProcessing = () => {}, onRequest = () => {}, quietProgress = false}) {
    const row = document.createElement("div"); row.className = compact ? "conversation-toolbar" : "row";
    if (!compact) row.style.flexWrap = "wrap";
    const label = document.createElement("label"); label.className = "save-switch";
    const check = document.createElement("input"); check.type = "checkbox"; check.style.width = "auto"; check.disabled = true;
    label.appendChild(check); label.appendChild(document.createTextNode(compact ? " Save conversation (optional)" : " Save this attempt (optional)"));
    const note = document.createElement("span"); note.className = compact ? "conversation-note muted" : "note muted";
    note.setAttribute("role", "status"); note.textContent = "Checking saving policy…";
    row.appendChild(label); container.appendChild(row); container.appendChild(note);
    let more, menu;
    if (compact) {
      more = document.createElement("details"); more.className = "conversation-more";
      const summary = document.createElement("summary"); summary.textContent = "More";
      more.appendChild(summary);
      menu = document.createElement("div"); menu.className = "conversation-menu";
      more.appendChild(menu);
    }
    let session, signature, initialization;
    const buttons = {};
    function display(s) {
      if (s !== session) return;
      check.checked = s.enabled; check.disabled = !s.config?.enabled;
      note.textContent = s.note || "";
      if (s.config?.enabled) {
        if (compact) {
          const seconds = s.config.retention_seconds;
          const amount = seconds % 3600 === 0 ? seconds / 3600 : seconds / 60;
          const unit = seconds % 3600 === 0 ? "hour" : "minute";
          const retention = `Saved conversations expire ${amount} ${unit}${amount === 1 ? "" : "s"} after creation.`;
          const ordinary = ["Saved history restored.", "New saved attempt. History expires from its creation time.",
            "Saving is optional. Enable it to resume this attempt after refresh."].includes(s.note);
          note.textContent = ordinary ? retention : (s.note || "") + " " + retention;
        } else note.textContent += " Policy: " + s.config.policy_id +
          "; expires " + s.config.retention_seconds + " seconds after creation.";
      }
      if (compact) note.textContent = note.textContent.replaceAll("New attempt", "New conversation");
      for (const button of Object.values(buttons)) button.disabled = !s.enabled;
      buttons.older.disabled = !s.enabled || !s.before;
      buttons.delete.disabled = !s.cid;
      renderHistory(s.messages, s);
    }
    async function ensure() {
      const next = JSON.stringify([base(), exercise(), window.BELAY_INSTITUTION_ID,
        window.BELAY_CLASS_ID, window.BELAY_LEARNER_ID]);
      if (!session || next !== signature) {
        signature = next;
        const nextSession = new Session({base:base(), exercise:exercise(), prefix, onChange:display,
          quietProgress, onRequest: (state, ref) => { if (session === nextSession) onRequest(state, ref); },
          onProcessing: value => { if (session === nextSession) onProcessing(value); }});
        session = nextSession;
        initialization = null;
      }
      if (!initialization) initialization = session.initialize();
      try { await initialization; }
      catch (error) { initialization = null; throw error; }
      return session;
    }
    async function action(fn) {
      try { await fn(await ensure()); } catch (error) { note.textContent = error.message; }
    }
    for (const [key, text, method] of [["refresh","Refresh history","restore"], ["older","Load older","older"],
      ["new","New attempt","newAttempt"], ["delete","Delete saved attempt","remove"]]) {
      const button = document.createElement("button"); button.textContent = text; button.className = "ghost";
      if (compact && key === "new") button.textContent = "New conversation";
      button.disabled = true; buttons[key] = button;
      (compact && key !== "new" ? menu : row).appendChild(button);
      button.addEventListener("click", () => { if (more) more.open = false; return action(s => s[method]()); });
    }
    if (more) row.appendChild(more);
    check.addEventListener("change", () => action(s => s.setSaving(check.checked)));
    ensure().catch(error => { note.textContent = error.message; });
    window.addEventListener?.("belay-auth-changed", () => { signature = null; action(s => s.initialize()); });
    return {ready: ensure, refresh: () => action(s => s.initialize()),
        async send(input) {
        const s = await ensure();
        if (!s.enabled) {
          const key = s.key;
          await s.scope();
          if (key && key !== s.key) throw new Error("Identity changed; refresh before sending a new message.");
          return null;
        }
        const response = await s.send(input);
        if ((await ensure()) !== s) throw new Error("Identity changed; previous reply was discarded.");
        return response;
      }};
  }
  window.BelayConversations = {Session, mount};
})();
