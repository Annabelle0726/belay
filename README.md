<p align="center">
  <img src="assets/readme/belay-hero.png" width="100%" alt="A belay rope connects a notebook and conversation to a protective gate, illustrating supported learning with safety boundaries">
</p>

<h1 align="center">Belay</h1>

Belay is a self-hosted peer tutor for programming exercises. In the data-science
course, a learner can run their code and ask the tutor, Sol, about the result.
Before Sol replies, Belay checks the draft against the exercise to catch feedback
that would give away the solution.

## Try a sample exercise

You can try the learner interface with Node.js and Python 3. From the repository
root, run these two commands:

```sh
node frontend/tests/build-feedback-fixture.cjs
python -m http.server 5173 --bind 127.0.0.1 --directory frontend
```

Open the [local preview](http://127.0.0.1:5173/tests/fixtures/generated-feedback-preview.html),
choose **Grouped summaries**, and click **Run code**. You’ll see a sample result
and tutor feedback. The preview plays back examples, so you can explore it
without a model key or a running backend. Press Ctrl+C in the terminal to stop.

## Run your own copy

To execute learner code and try the full conversation flow, follow the
[local setup guide](deployment/controls/README.md). It walks through preparing
the code runner, starting the tutor and opening the learner page. The example
uses a test learner and a local stand-in for the model. When you’re ready to
generate replies, the [provider guide](deployment/controls/controlled-runtime.md)
covers OpenAI-compatible endpoints and Anthropic.

If you’re developing against the API alone, run `docker compose up --build`
and open the [health endpoint](http://localhost:8000/healthz). Compose starts
the API with SQLite. Learner requests need a signed token and assignment
permissions. To use PostgreSQL, enable the `postgres` profile and point
`DATABASE_URL` at that database. See the [Compose file](docker-compose.yml)
and [authentication guide](docs/authentication.md).

## How access and budgets work

**Assignment access.** Belay checks which learner, class and assignment version
a signed request can access. Older grants allow only `study/peer`. Other
combinations require explicit permission from the assignment. The
[assignment policy](docs/assignment-pedagogy-policy.md) shows how to grant them.

**Model spending.** Models and providers in one controlled installation share a
budget. If one model uses up the weekly allowance, a request to another model
is subject to the same limit. Operators set the limits and the window boundaries.
A new week leaves earlier spending and outstanding reservations on the ledger.
See the [budget guide](deployment/controls/budget-policy.md) for the settings.

Work on live platform identity, revocation, data retention and deletion, and
Portage billing is tracked in [issue #22](https://github.com/EduCloud-Ecosystem/belay/issues/22).

## Develop with Belay

| If you want to… | Start here |
| --- | --- |
| Understand how a tutor turn works | [Architecture](ARCHITECTURE.md) |
| Add exercises for a new subject | Copy the [skeleton pack](backend/app/packs/_skeleton/), implement the [domain contract](backend/app/core/domain/pack.py) and register it in the [pack registry](backend/app/core/registry.py). |
| Embed the tutor in another application | The [frontend guide](frontend/README.md) covers the widget and development client. The [Quad integration](backend/app/integrations/quad/) exposes tutor turns under `/quad/v1`. |
| Run tests or contribute a change | [Validation guide](VALIDATION.md) and [contributor guide](CONTRIBUTING.md) |

## License

The [domain contract](backend/app/core/domain/LICENSE) uses Apache-2.0.
The tutor, code runner and reference pack use [AGPL-3.0-only](LICENSE).
See [Licensing](LICENSING.md) for the full breakdown and corpus terms.
