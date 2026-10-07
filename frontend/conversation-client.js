/* SPDX-License-Identifier: AGPL-3.0-only
 * Only attempt pointers/preferences persist in the browser. No tokens or transcripts.
 */
(function () {
  "use strict";
  const uuid = () => window.crypto.randomUUID();
  class Session {
    constructor({base, prefix = "/api", exercise, onChange = () => {}}) {
      this.base = base.replace(/\/$/, ""); this.prefix = prefix; this.exercise = exercise;
      this.onChange = onChange; this.messages = []; this.before = null;
      this.cid = null; this.revision = 0; this.pending = null; this.enabled = false;
    }
    notify(note) { this.note = note; this.onChange(this); }
    async json(path, method = "GET", body) {
      const res = await fetch(this.base + this.prefix + "/conversations" + path, {
        method, headers: await window.BelayAuth.headers(this.base),
        ...(body === undefined ? {} : {body: JSON.stringify(body)})
      });
      if (!res.ok) {
        const error = new Error(res.status === 404 ? "Saved history is unavailable, expired or deleted." :
          res.status === 409 ? "The attempt changed or a turn is unfinished. Refresh before continuing." :
          "Saved dialogue request failed (" + res.status + ").");
        error.status = res.status;
        if (res.status === 401 || res.status === 404) {
          this.messages = []; this.before = null;
          if (res.status === 404 && this.cid) { this.cid = null; this.write({enabled:this.enabled}); }
          this.notify(error.message);
        }
        throw error;
      }
      return res.status === 204 ? null : res.json();
    }
    read() {
      try { return JSON.parse(window.localStorage.getItem(this.key)) || {}; } catch { return {}; }
    }
    write(value) {
      try { window.localStorage.setItem(this.key, JSON.stringify(value)); }
      catch { this.notify("Browser storage is unavailable; restoration needs this attempt ID: " + (this.cid || "")); }
    }
    async scope() {
      const config = await this.json("/config");
      const identity = config.identity;
      const version = config.assignments[this.exercise];
      if (!version) throw new Error("This exercise version is unavailable.");
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
      return config;
    }
    async initialize() {
      try {
        await this.scope();
        if (this.enabled) await this.restore(false);
        else this.notify(this.config.enabled ? "Saving is optional. Enable it to resume this attempt after refresh." :
          "This conversation is unsaved. Course tutoring remains available.");
      } catch (error) { this.messages = []; this.notify(error.message); throw error; }
    }
    async setSaving(enabled) {
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
      if (checkScope) await this.scope();
      if (!this.enabled) throw new Error("Enable optional saving first.");
      const previous = this.read();
      const record = {enabled:true, createRequest:uuid()};
      this.pending = null; this.write(record);
      try { await this.createReserved(record); }
      catch (error) { if (error.status) this.write(previous); throw error; }
    }
    async restore(checkScope = true) {
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
        this.notify(page.pending ? "A turn is unfinished. Refresh after it completes or its lease expires." : "Saved history restored.");
      } catch (error) {
        this.messages = []; this.before = null; this.pending = null;
        if (error.status === 404) { this.cid = null; this.write({enabled:true}); }
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
    async send(input) {
      const previousKey = this.key;
      await this.scope();
      if (previousKey && previousKey !== this.key) throw new Error("Identity changed; refresh before sending a new message.");
      if (!this.enabled || !this.cid) throw new Error("Choose a saved attempt before sending.");
      if (this.activePending) throw new Error("A turn is unfinished; refresh before continuing.");
      const signature = JSON.stringify(input);
      if (this.pending && this.pending.signature !== signature) throw new Error("Retry the previous message or refresh before a new one.");
      if (!this.pending) this.pending = {signature, body: {...input, request_id:uuid(), expected_revision:this.revision}};
      try {
        const result = await this.json("/" + encodeURIComponent(this.cid) + "/turns", "POST", this.pending.body);
        this.pending = null;
        this.revision = result.revision;
        try { await this.restore(false); } catch { this.notify("Turn completed; refresh to reload saved history."); }
        if (result.unsaved_exchange) this.notify("This exchange was not saved; only neutral placeholders will restore.");
        return {...result.response, unsaved_exchange: !!result.unsaved_exchange};
      } catch (error) {
        if (error.status) this.pending = null;
        if (error.status === 404) { this.cid = null; this.messages = []; this.write({enabled:true}); }
        if (error.status === 401 || error.status === 404) this.messages = [];
        this.notify(error.message); throw error;
      }
    }
    async remove() {
      await this.scope();
      if (!this.cid) return;
      await this.json("/" + encodeURIComponent(this.cid), "DELETE");
      this.cid = null; this.messages = []; this.before = null; this.pending = null;
      this.write({enabled:this.enabled}); this.notify("Saved attempt deleted. Choose New attempt to continue saving.");
    }
  }
  function mount({container, base, exercise, prefix = "/api", renderHistory}) {
    const row = document.createElement("div"); row.className = "row"; row.style.flexWrap = "wrap";
    const label = document.createElement("label");
    const check = document.createElement("input"); check.type = "checkbox"; check.style.width = "auto"; check.disabled = true;
    label.appendChild(check); label.appendChild(document.createTextNode(" Save this attempt (optional)"));
    const note = document.createElement("span"); note.className = "note muted"; note.textContent = "Checking saving policy…";
    row.appendChild(label); container.appendChild(row); container.appendChild(note);
    let session, signature, initialization;
    const buttons = {};
    function display(s) {
      if (s !== session) return;
      check.checked = s.enabled; check.disabled = !s.config?.enabled;
      note.textContent = s.note || "";
      if (s.config?.enabled) note.textContent += " Policy: " + s.config.policy_id +
        "; expires " + s.config.retention_seconds + " seconds after creation.";
      for (const button of Object.values(buttons)) button.disabled = !s.enabled;
      buttons.older.disabled = !s.enabled || !s.before;
      buttons.delete.disabled = !s.cid;
      renderHistory(s.messages);
    }
    async function ensure() {
      const next = JSON.stringify([base(), exercise(), window.BELAY_INSTITUTION_ID,
        window.BELAY_CLASS_ID, window.BELAY_LEARNER_ID]);
      if (!session || next !== signature) {
        signature = next;
        session = new Session({base:base(), exercise:exercise(), prefix, onChange:display});
        initialization = session.initialize();
      }
      await initialization;
      return session;
    }
    async function action(fn) {
      try { await fn(await ensure()); } catch (error) { note.textContent = error.message; }
    }
    for (const [key, text, method] of [["refresh","Refresh history","restore"], ["older","Load older","older"],
      ["new","New attempt","newAttempt"], ["delete","Delete saved attempt","remove"]]) {
      const button = document.createElement("button"); button.textContent = text; button.className = "ghost";
      button.disabled = true; buttons[key] = button; row.appendChild(button);
      button.addEventListener("click", () => action(s => s[method]()));
    }
    check.addEventListener("change", () => action(s => s.setSaving(check.checked)));
    ensure().catch(error => { note.textContent = error.message; });
    window.addEventListener?.("belay-auth-changed", () => { signature = null; action(s => s.initialize()); });
    return {refresh: () => action(s => s.initialize()),
      async send(input) {
        const s = await ensure();
        if (!s.enabled) return null;
        const response = await s.send(input);
        if ((await ensure()) !== s) throw new Error("Identity changed; previous reply was discarded.");
        return response;
      }};
  }
  window.BelayConversations = {Session, mount};
})();
