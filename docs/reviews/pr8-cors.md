# PR #8 / issue #17: explicit opaque-origin access

Default CORS allows named development origins and rejects `Origin: null`.
Whitespace/empty-entry normalization is retained; an explicitly empty list stays
empty. Tests use independent middleware instances rather than reloading the real
application or its database wiring.

Recommended local launch setting for the current student frontend:

```powershell
$env:CORS_ORIGINS = "http://127.0.0.1:5177"
```

If a deliberate development experiment needs a file/opaque origin, it must
explicitly include `null` in CORS_ORIGINS. All opaque origins share this value;
it does not authenticate a particular local file. Serve the frontend over the
named loopback origin when possible. Production operators configure their actual
origins explicitly. No operating .env or service was changed by this repair.

SQLite/PostgreSQL and quality outcomes are recorded in the final repair summary.
Hosted CI has not been rerun because these commits are local only.


## Recorded validation

Full validation source: `d3ea8d5b173d34ce58147639ef9d014c1c58918f`.

| Gate | Passed | Failed/errors | Skipped |
| --- | --- | --- | --- |
| sqlite | 384 | 0 | 7 |
| postgres | 384 | 0 | 7 |

Ruff lint, format check and configured mypy passed for that full-run source. Seven full-suite skips are the opt-in live evaluation and unavailable sibling-contract schema cases. No paid model request was used.

Existing unsigned commits in the original PR history: 0. New repair/documentation commits are signed off. The old history has not been rewritten. The repair head has not been pushed, merged, or run through hosted CI. No command to start, stop or restart the actual API/worker service was issued. Live serving state was not revalidated.
