# Deploying to Jetstream2 / ACCESS

This is the proposal's cyberinfrastructure commitment, made concrete. The whole
system runs on NSF-funded ACCESS infrastructure end to end — application, data,
quantum simulation, **and** model inference — with no commercial cloud.

Jetstream2 (Indiana University-led ACCESS resource) is an OpenStack cloud:
hundreds of AMD EPYC Milan compute nodes, large-memory nodes, and NVIDIA A100 /
H100 / L40S GPU nodes, on a 14 PB Ceph backend with 4×100 Gbps to Internet2.

## 1. Allocation

Request an **ACCESS allocation** and exchange credits to the Jetstream2
resources you need (`1 ACCESS credit = 1 Jetstream2 SU`; the CPU, GPU, and
Large-Memory resources are exchanged into separately):

- **For the classroom deployment**, request an **Education** allocation — it is
  intended for teaching/workshops and carries higher quotas (e.g. 200 CPU cores
  and 25 floating IPs). Exchange credits into **Jetstream2 (CPU)**.
- ACCESS project tiers scale Explore → Discover → Accelerate → Maximize; the
  entry **Explore** tier comfortably covers the footprint below, and you can
  scale the request up with pilot results.
- **Storage:** every allocation gets **1 TB by default** — more than enough for
  the research trace — so no separate storage exchange is needed for a pilot.

## 2. Instance sizing (right-sized, not over-asked)

The tutor's compute footprint is light: a FastAPI backend, a small Postgres
trace DB, a static front-end, and the agentic loop. The ≤4-qubit simulator is
negligible; model inference lives on the JS2 inference service (next section).

| Phase | Flavor | vCPU / RAM | Notes |
|---|---|---|---|
| Dev / build | `m3.small` | 2 / 6 GB | install + configure; resize up after |
| **Pilot (one section)** | **`m3.medium`** | 8 / 30 GB | app + Postgres + static + reverse proxy |
| Scale (multi-section) | `m3.large` + **Octavia** | 16 / 60 GB | or 2× `m3.medium` behind the load balancer |

SU budget (always-on = SU/hr × 24 × 365): an `m3.medium` is ~70,000 CPU SU/year
(about half that if shelved over breaks). That sits inside an Explore/Education
allocation with room to spare.

## 3. Bring up an instance

Use the Jetstream2 web interface (**Exosphere**) or **CACAO** (Terraform-based
templates) to launch an Ubuntu instance with Docker; attach a floating (public)
IP and open 443/80 (plus 22 for admin).

```bash
git clone <this repo> && cd quantum-inventioneers-mvp
cp .env.example .env            # defaults already target the JS2 inference service
docker compose up -d --build    # backend on :8000
```

For a real cohort, enable the Postgres service in `docker-compose.yml` and point
`DATABASE_URL` at it (the SQLAlchemy models are portable as-is). Put the trace
DB on a **persistent volume** (the default 1 TB quota covers it) and snapshot it
regularly — it is the research dataset.

**Schema migration — `learner_state.concepts`.** The persistent learner model
added a `concepts JSON` column to `LearnerState` (v2). `create_all`/`init_db` will
**not** alter an existing table. On a fresh deploy there is nothing to do. To
upgrade a Postgres trace DB that predates the column **without dropping data**:

```sql
ALTER TABLE learner_state ADD COLUMN concepts JSON DEFAULT '{}';
```

(For a throwaway dev SQLite DB with no real data, just `rm backend/qimvp.db` and
re-init.) See VALIDATION.md §2 for the same note on the validation path.

## 4. Model inference (the AWS/Nova replacement)

The model layer is the **Jetstream2 Inference Service**: OpenAI-compatible,
US-origin, open-weight models hosted at IU, at **no per-token cost and no SU
cost**. Defaults (`config.py` / `.env.example`):

- **strong** = `gpt-oss-120b` (reasoning, `REASONING_STRONG=high`) — Peer-Reasoner
- **fast** = `llama-4-scout` — Planner + Self-Evaluator

Because the backend runs **on a Jetstream2 instance**, it reaches the direct
endpoints with **no token** (access is restricted to JS2/IU networks):

- `https://llm.jetstream-cloud.org/gpt-oss-120b/v1`  (model `gpt-oss-120b`)
- `https://llm.jetstream-cloud.org/llama-4-scout/v1`  (model `llama-4-scout`)

Off-instance dev points `LLM_BASE_*` at the Open WebUI proxy
(`https://llm.jetstream-cloud.org/api`) with a token, or tunnels through an
instance. Prompts stay within IU's data center and are not used for training —
the basis for the §6 / IRB data-handling story.

**Optional dedicated inference.** If you want a frozen model version and
guaranteed latency during the controlled study, stand up a GPU instance and
serve the model yourself with vLLM: a single **`g5.xl`** (H100 80 GB, 128 SU/hr)
or **`g3.2xl`** (2× A100 80 GB, 128 SU/hr) runs gpt-oss-120b; a quantized ≤70B
fits a **`g3.xl`** (A100 40 GB, 64 SU/hr). Budget this only for the study window
(e.g. ~350 GPU-hours ≈ ~45,000 GPU SU), not always-on. Otherwise the shared
service costs zero GPU SUs.

## 5. Reverse proxy + TLS

Put Caddy/nginx in front of `:8000` to terminate TLS and serve the static
front-end:

```
your-host.jetstream-cloud.org {
    handle /api/*   { reverse_proxy localhost:8000 }
    handle /healthz { reverse_proxy localhost:8000 }
    handle          { root * /srv/frontend; file_server }
}
```

Set `window.QI_BACKEND_URL` (or the dev client's backend field) to the public
host, and set `CORS_ORIGINS` accordingly.

## 6. Quantum execution

The local simulator (≤4 qubits) runs on the app node at negligible cost; Classiq
execution is external (`QUANTUM_BACKEND=classiq`, after
`pip install -r backend/requirements-classiq.txt` and `classiq.authenticate()`).
Run the Bell-pair **endianness smoke test** (exercise *03 · Entanglement*) the
first time you wire a live Classiq backend; if `01`/`10` appear where `00`/`11`
are expected, flip `REVERSE_BITS` in `quantum/classiq_backend.py`. Scaling to
larger qubit counts later (cuQuantum) is a GPU option but is not needed for the
curriculum.

## 7. Secrets & operations

- On a JS2 instance the model layer needs **no commercial key**. If you use the
  Open WebUI proxy or `LLM_PROVIDER=anthropic`, keep those tokens server-side
  (env / secrets manager) — never in the browser.
- Back up the database (it is the research dataset); see `DATA_AND_IRB.md`.
- `GET /healthz` for liveness behind the proxy.
