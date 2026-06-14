# 2-worker HTTP smoke check

Validates cross-worker consent routing + event persistence over real HTTP
(multi-process uvicorn + shared Postgres), without requiring the JS2 LLM.
`/api/run` is LLM-free, so this check is fully offline.

## Prerequisites

1. Postgres running and reachable.  With docker-compose:
   ```
   docker compose up -d db
   ```
2. Backend venv with all deps (`pip install -r requirements.txt`).

## Steps

### 1 — Start two workers sharing the Postgres DB

```bash
DATABASE_URL=postgresql+psycopg://qi:qi@localhost:5432/qimvp \
STORE_BACKEND=sql \
uvicorn app.main:app --workers 2 --port 8000
```

Each worker creates its own `ConsentRouter(SqlStore())` with an empty
`_consent_cache`.  The consent routing correctness test (step f in
`smoke_sql.py`) is therefore exercised over HTTP here.

### 2 — Register a participant

```bash
PID=$(curl -s -X POST http://localhost:8000/api/participant \
  -H "Content-Type: application/json" \
  -d '{"anon_code":"smoke_http","consent":true}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
echo "PID = $PID"
```

### 3 — Run the model twice (two different worker processes may handle these)

```bash
for i in 1 2; do
  curl -s -X POST http://localhost:8000/api/run \
    -H "Content-Type: application/json" \
    -d "{\"participant_id\":\"$PID\",\"exercise_id\":\"bell\",\"source\":\"allocate 2\\nsuperpose q0\\nmeasure all\"}" \
  | python3 -c "import sys,json; r=json.load(sys.stdin); print(f'run {$i}: ok={r[\"ok\"]} tvd={r.get(\"tvd\")}')"
done
```

### 4 — Export and verify 2 events

```bash
curl -s "http://localhost:8000/api/session/$PID/events.jsonl" | wc -l
# Expected: 2  (one line per event)
```

If you see 2 lines, cross-worker consent routing and Postgres persistence are
working correctly: both workers resolved the same `participant_id` to the durable
store via `_lookup_consent` reading from Postgres (not from a warm in-process cache).

### 5 — Verify a non-consenter is excluded from the export

```bash
PID_NO=$(curl -s -X POST http://localhost:8000/api/participant \
  -H "Content-Type: application/json" \
  -d '{"anon_code":"smoke_no","consent":false}' | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

curl -s -X POST http://localhost:8000/api/run \
  -H "Content-Type: application/json" \
  -d "{\"participant_id\":\"$PID_NO\",\"exercise_id\":\"bell\",\"source\":\"allocate 1\\nmeasure all\"}" > /dev/null

LINES=$(curl -s "http://localhost:8000/api/session/$PID_NO/events.jsonl" | wc -l)
echo "Non-consenter export lines: $LINES (expected 0)"
```

## Known limitation (document for §6f sticky sessions)

A non-consenting participant's in-session ephemeral state (learner model,
attempt count) is held in the in-process `ConsentRouter._ephemeral` dict of the
worker that handled that request.  If a subsequent request for the same
non-consenting participant lands on a different worker (round-robin), that worker
has an empty ephemeral store for that pid — the learner state is not shared
across workers.

**This is by design for the consent gate:** non-consenting participants' data is
never written to any shared store.  However, it means that a non-consenting
participant's Sol responses may lose continuity if requests fan across workers.

**Mitigation for the pilot:** use sticky sessions (e.g., nginx `ip_hash` or
`--workers 1` on the JS2 instance where a Postgres DSN gives durability for
consenters, and non-consenters are single-session by definition).  Ticket: 6f.
