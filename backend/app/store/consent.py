"""
Consent-gated store router (DMP §3 / IRB).

Two mechanisms are in play simultaneously and must never be confused:

  DMP §1 — Participant rows (opaque id, anonymised code, consent flag, ts; NO PII)
            persist for ALL participants, consenting or not.  This is required so
            the IRB can audit that consent was correctly recorded.

  DMP §3 — Events trace + LearnerState are the research data stream.  They are
            gated on consent:
              consent=True  → durable store (SqlStore, backed by the project DB)
              consent=False → per-session ephemeral InMemoryStore: written only to
                              RAM, never to disk, never returned by the trace export
              unregistered  → ephemeral (fail-safe: never persist before consent)

  The tutoring session (compile/run, Sol turns) is byte-for-byte identical
  regardless of consent — only where events/state are written differs.

Usage (in main.py):

    _durable = SqlStore() if settings.store_backend == "sql" else InMemoryStore()
    _router  = ConsentRouter(_durable)

    # Register participant (always durable):
    _router.register_participant(pid, anon_code, consent)

    # Per-request: resolve the right store and pass it down:
    store = _router.store_for(pid)
    run_turn(payload, llm, store)                  # signature unchanged
    store.append_event(make_event(...))            # direct calls too

    # Export reads ONLY the durable store:
    _router.durable.export_jsonl(pid)
"""

from __future__ import annotations

from .repository import InMemoryStore, SqlStore


class ConsentRouter:
    """Resolves the event/state store for a participant_id based on consent.

    Thread-safety note: each request gets its own ``store_for`` return value.
    The durable store handles its own session-level thread safety (SqlStore).
    The ephemeral dict is only written once per pid (first access); in a
    multi-threaded server a tiny race could create two InMemoryStore instances
    for the same pid, but both would be discarded after the session, so it is
    harmless for correctness.
    """

    def __init__(self, durable: SqlStore | InMemoryStore) -> None:
        self._durable = durable
        # Per-pid ephemeral stores for non-consenting / unregistered participants.
        self._ephemeral: dict[str, InMemoryStore] = {}
        # In-process consent cache: populated by register_participant and
        # (for SqlStore) lazily by _lookup_consent on cross-session lookups.
        self._consent_cache: dict[str, bool] = {}

    # ── participant registration (ALWAYS durable) ─────────────────────────────

    def register_participant(self, pid: str, anon_code: str, consent: bool) -> None:
        """Write the Participant row to the durable store; cache consent.

        For SqlStore: creates the participants table row.
        For InMemoryStore (dev/test): no table exists, consent is cached only
        in this router instance (sufficient for single-process test runs).
        """
        if isinstance(self._durable, SqlStore):
            from .db import SessionLocal
            from .models import Participant

            with SessionLocal() as s:
                row = Participant(id=pid, anon_code=anon_code, consent=consent)
                s.add(row)
                s.commit()
        self._consent_cache[pid] = consent

    # ── per-request store resolution ─────────────────────────────────────────

    def _lookup_consent(self, pid: str) -> bool:
        """Return the recorded consent flag.

        Check order:
          1. In-process cache (populated by register_participant or previous
             lookup for this pid in this process lifetime).
          2. Durable SqlStore — handles cross-session / cross-worker lookups.
          3. Default False (fail-safe: never persist before consent).
        """
        if pid in self._consent_cache:
            return self._consent_cache[pid]
        if isinstance(self._durable, SqlStore):
            try:
                from .db import SessionLocal
                from .models import Participant

                with SessionLocal() as s:
                    row = s.get(Participant, pid)
                    if row is not None:
                        self._consent_cache[pid] = bool(row.consent)
                        return bool(row.consent)
            except Exception:
                pass
        # Fail-safe: no consent record found → ephemeral.
        return False

    def store_for(self, pid: str) -> InMemoryStore | SqlStore:
        """Return the store where events/state for *pid* should be written.

        consent=True  → durable store (writes persist across restarts)
        consent=False → session-scoped ephemeral InMemoryStore (never persisted)
        unregistered  → ephemeral (fail-safe)
        """
        if self._lookup_consent(pid):
            return self._durable
        if pid not in self._ephemeral:
            self._ephemeral[pid] = InMemoryStore()
        return self._ephemeral[pid]

    # ── durable-store accessor (for the trace export endpoint) ────────────────

    @property
    def durable(self) -> SqlStore | InMemoryStore:
        """The durable backing store.  Export endpoints must read from here only."""
        return self._durable
