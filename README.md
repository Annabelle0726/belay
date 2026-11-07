<p align="center">
  <img src="assets/readme/belay-hero.png" width="100%" alt="A belay rope connects a notebook and conversation to a protective gate, illustrating supported learning with safety boundaries">
</p>

<h1 align="center">Belay</h1>

<p align="center"><strong>A self-hosted peer tutor for learning to program.</strong></p>

<p align="center">
  <img src="assets/readme/badge-python.svg" alt="Python">
  <img src="assets/readme/badge-javascript.svg" alt="JavaScript">
  <img src="assets/readme/badge-html5.svg" alt="HTML5">
  <img src="assets/readme/badge-css.svg" alt="CSS">
</p>

<p align="center"><a href="#quickstart">Run Belay</a> · <a href="#how-sol-builds-a-reply">How the tutor works</a> · <a href="#adding-a-domain-pack">Add a domain pack</a> · <a href="#development-and-evaluation">Development and evaluation</a></p>

## What it is

Belay pairs a code editor and an exercise grader with a conversational tutor
called Sol. A learner can try a solution, inspect the result, and ask a question
about the code they just ran. A course author supplies the exercises, grading
rules and reference material. Belay supplies the tutoring loop, the code runner
and the checks that decide what feedback reaches the learner.

The reference data-science pack has three runnable exercises. **Grouped
summaries** asks learners to compute a mean for each category in a sales file.
**Held-out regression** asks them to fit on the training split and predict on
unseen data. The third exercise trains a small neural network in NumPy.
Each gives Sol something concrete to discuss, such as a program that runs
successfully but misses an exercise check.

## Quickstart

### Run the local tutor

Use PowerShell from the repository root with Python 3.12 and Docker running.
For a **new installation**, create and activate a Python environment, install
the backend and data-science pack, then build the isolated code runner:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt -r backend/requirements-packs.txt
docker build -t belay-sandbox:0.1.0 -f backend/Dockerfile.sandbox backend
.\deployment\controls\prepare-local-stub.ps1
```

The last command prepares a local database, test identity and model stub.
It runs once and refuses to overwrite existing configuration or data.
For an **already prepared installation**, activate its Python environment and
start here:

```powershell
.\start-belay.ps1 -Check
.\start-belay.ps1
```

The first command reports the selected provider and any queued work. The second
starts the API, learner page and worker. Once the launcher reports `ready` and
`worker_alive` as true, open the [learner page](http://127.0.0.1:5177/dev-client.html).
You can also check [API health](http://127.0.0.1:8004/healthz).

1. Select **01 · Grouped summaries** and click **Run code**. Read the program
   output and exercise checks, then the tutor feedback. The fresh installation
   labels its sample replies **Local model stub** and runs learner code in Docker.
2. Use **Ask Sol** to ask a follow-up. Expand **Glass Box · Latest response** to
   see which evidence the tutor used and why it chose that kind of help.
3. Try another edit and run it again. If you want to revisit a conversation,
   enable optional saving for the exercise.

Stop with **Ctrl+C** in the launch terminal, or run this from a second PowerShell
in the repository root:

```powershell
.\stop-belay.ps1
```

The [local setup guide](deployment/controls/README.md) covers existing
installations, custom paths, queued work and startup errors.

### Preview the interface without a backend

For a walkthrough with simulated code output and tutor replies, run these
commands from the repository root with Node.js and Python 3:

```sh
node frontend/tests/build-feedback-fixture.cjs
python -m http.server 5173 --bind 127.0.0.1 --directory frontend
```

Open the [offline preview](http://127.0.0.1:5173/tests/fixtures/generated-feedback-preview.html)
and select an exercise. Press Ctrl+C in the terminal to stop the preview server.

## How Sol builds a reply

The **planner** chooses a teaching move based on the learner’s question, the
exercise and available run results. For a failed check, it might ask the learner
to inspect one category of data. The **reasoner** drafts the reply. A
**self-evaluator** checks whether it fits the assigned teaching stance, and a
bounded revision step can try again. Belay updates its learner model as the
conversation progresses. The [agent implementation](backend/app/agent/) and
[architecture guide](ARCHITECTURE.md) describe the stages.

Two checks matter when Sol helps with a graded exercise:

- **Giving a hint without giving away the solution.** The domain pack supplies
  evidence about whether a draft solves the exercise. A final governance check
  can withhold or rewrite a reply. Retrieved passages are also screened before
  they reach the model. An optional input classifier can flag attempts to
  override the tutor’s instructions.
- **Showing where an explanation came from.** The data-science pack searches
  a local collection of teaching notes. When the grounding check matches a
  claim to a passage, it places a citation beside that claim. The corpus records
  the source and license for each passage. See the [knowledge base](backend/app/packs/datascience/knowledge/)
  and [grounding checks](docs/reviews/pr5-grounding.md).

## Code execution, conversations and access

**Code execution.** The runner executes learner Python in a container with
network access disabled and limits on CPU, wall time and output. The grader
stays on the host, where it can use the reference solution without putting it
in the learner’s container. The interface shows execution errors and exercise
checks separately, so a learner can see whether the program failed to run or
produced a result that missed the goal. See the [runner](backend/app/core/runner/)
and [grading specifications](backend/app/packs/datascience/specs/).

**Saved conversations.** Learners can use Sol with saving off. When the
installation permits saving and the learner opts in, they can reopen a saved
conversation for the same exercise. Belay checks the learner, class, assignment
and content version before returning it. Research consent is a separate choice.
If a queued request is interrupted, the client can check its status without
automatically sending it to the model a second time. See [conversation storage
and recovery](docs/conversations.md).

**Assignment access.** A host supplies a short-lived signed token. Operator-managed
grants specify the class, assignment version and permitted teaching modes and
stances. Legacy grants allow only `study/peer`. Broader access requires an explicit
pair on the assignment. See the [authentication contract](docs/authentication.md)
and [assignment policy](docs/assignment-pedagogy-policy.md).

## Pointing at a provider

The local quickstart uses `local_stub`. For generated replies, configure a
provider in the installation’s private environment file. The planner and
self-evaluator use the fast tier, and the reasoner uses the strong tier.

| Provider | Configuration |
| --- | --- |
| `openai_compatible` | Set `OPENAI_BASE_URL`, `MODEL_FAST`, `MODEL_STRONG` and the endpoint credential. A local Ollama or vLLM endpoint can serve this API. |
| `anthropic` | Install the optional Anthropic SDK and configure `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL_FAST` and `ANTHROPIC_MODEL_STRONG`. |
| `bedrock` | The repository includes tier mappings. Inference through this adapter is unimplemented. |

A metered installation requires reviewed input and output prices. Models and
providers in the same deployment share a budget. The operator chooses any short
and weekly spending windows and their UTC boundaries. A window refresh preserves
cumulative spending and outstanding reservations. See the [provider setup](deployment/controls/controlled-runtime.md)
and [budget guide](deployment/controls/budget-policy.md).

## Host integration and the Quad sidecar

For API development, start the standalone service from the repository root:

```sh
docker compose up --build
```

The API serves [its health endpoint](http://localhost:8000/healthz) on port
8000 and uses SQLite by default. To use PostgreSQL, point `DATABASE_URL` at the
Compose database service and start with `docker compose --profile postgres up --build`.
Protected routes require the host credentials and assignment grants described
in the [authentication guide](docs/authentication.md). Use the local tutor
quickstart above when you also need the browser client and managed worker.

A host can inspect `GET /quad/v1/capabilities` and submit a tutor turn through
`POST /quad/v1/turn`. Grading results supply read-only context. Belay has no
grade-writing endpoint. The [reference widget and embedding example](frontend/README.md)
show how a host presents the tutor while keeping provider credentials on the
server. Live identity binding, durable revocation, deletion and retention rules,
and authoritative Portage accounting are tracked in [issue #22](https://github.com/EduCloud-Ecosystem/belay/issues/22).

## Adding a domain pack

1. Start from the [skeleton pack](backend/app/packs/_skeleton/). Implement the
   [domain contract](backend/app/core/domain/pack.py) for curriculum, exercise
   lookup, execution and grading, worked-example verification, misconceptions
   and solution-leak evidence.
2. For a pack with reference material, implement `knowledge()`. The [corpus
   pipeline](backend/app/knowledge/) preserves attribution during ingestion and
   builds a searchable index. The [data-science pack](backend/app/packs/datascience/)
   shows how exercises, grading specs and reference notes fit together.
3. Register the factory in the [pack registry](backend/app/core/registry.py)
   and set `TUTOR_PACK` to its ID. The tutor and browser can then use the
   curriculum exposed by that pack.

## Development and evaluation

From the repository root, install the test dependencies in your active backend
environment and run the Python and browser-client tests:

```sh
python -m pip install -r backend/requirements-dev.txt
python -m pytest backend/tests/test_domain_seam.py backend/tests/test_governance.py
npm ci --prefix frontend --ignore-scripts
npm test --prefix frontend
```

The Python command exercises the domain-pack interface and the tutor’s final
feedback checks. The [validation guide](VALIDATION.md)
and [CI workflow](.github/workflows/ci.yml) cover the full backend suite,
SQLite and PostgreSQL, real-container execution, linting and type checking.

### Behavioral benchmark

To evaluate a configured tutor model, run this from `backend/`. It makes tutor
model calls and writes a JSON report:

```sh
python -m evals.behavioral --pack datascience --families no_solution,never_leak --no-judge --out report.json
```

These two families check the emitted answers for solution leaks using the pack’s
evidence. Other families can use a separately configured judge model to assess
the quality of the tutor’s help. Run `python -m evals.behavioral --help` to see
the provider, judge and repeat options.

## License and contributions

The [domain contract](backend/app/core/domain/LICENSE) is licensed under
Apache-2.0. The tutor, runner, reference pack and integrations are licensed under
[AGPL-3.0-only](LICENSE). See [Licensing](LICENSING.md) for corpus terms and the
[contributor guide](CONTRIBUTING.md) for the development workflow and sign-off.
