# DS pack grading-spec format (v0)

Declarative, per-exercise grading specs (JSON). One file per exercise,
`<exercise-id>.json`. Interpreted by `_harness.py` inside the sandboxed
`core/runner`; the pack never grades by executing student code in-process.

**Convergence intent.** This format is deliberately convergent with Quad's
`pkg/gradingspec`: a *host-neutral, declarative* spec run in our own sandboxed
runner, not locked to any CI provider. The check vocabulary below is the seam an
autograder and the tutor's `run`/`leak_evidence` path share. When the framework
integrates with Quad, these specs are the artifact that ports.

## Shape

```json
{
  "id": "<exercise-id>",
  "data_files": ["data/foo.csv", "..."],   // staged into the sandbox workdir
  "checks": [ { "type": "...", ... }, ... ]
}
```

A run's `goalMet` is the AND of all checks (and a clean execution). The check
marked `"primary": true` supplies the run's primary `metric` scalar.

## Check types

| type | fields | passes when |
|---|---|---|
| `stdout_contains` | `text` | student stdout contains `text` |
| `stdout_equals` | `text` | student stdout (stripped) equals `text` |
| `var_numeric` | `var`, `expected` (scalar or `{k: v}`), `tol` | named var within `tol` of expected (per-key for dicts) |
| `var_dataframe` | `var`, `expected` (records), `tol` | DataFrame equals expected (column-order-insensitive, atol=`tol`) |
| `function_contract` | `func`, `cases` (`[{args, expected}]`), `tol` | `func(*args)` within `tol` of expected for every case |
| `metric_threshold` | `metric` (`r2`/`mse`/`mae`/`accuracy`), `pred_var`, `truth_file`, `op`, `threshold`, `primary` | `metric(truth, pred) op threshold` |
| `var_threshold` | `var`, `op`, `threshold`, `primary` | numeric var `op threshold` |

`op` ∈ `>= <= > < ==`.

## Threat / execution note

All checks execute in the restricted subprocess (`core/runner`): no network,
CPU/wall limits, isolated temp workdir. See the runner module docstring and
VALIDATION for the honest threat model (resource/network/isolation boundary, not
adversarial containment; containerized runner is the roadmap convergence point).
