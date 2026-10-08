# UI and bounded conversation preview

## 1. Baseline and scope

Branch: `codex/ui-conversation-preview`, starting at
`feature/bounded-conversation-restoration` / `3a414d6`.
Presentation source: `feature/ui-layout-refactor` / `0bd2def`.
Main and both source branches are unchanged. This is a presentation port onto the
authenticated restoration branch, not a whole-branch merge. CC-B1 ancestry and
B2-B4 work are excluded. No push or pull request is created.

## 2. Completed steps and commits

1. `fix(dev): reject overlapping loopback listeners` (`37cd7d6`). Detect existing
   IPv4/IPv6 listeners before startup; do not stop unrelated processes. Nineteen
   hermetic local-host tests passed.
2. `fix(conversations): preserve live signals and recover missing history`
   (`9fc167a`). Return bounded, screened, learner-visible Glass Box summaries only
   on first live delivery, after completion. Keep transcripts/replays free of
   these summaries and drafts. Recheck membership before recovering from 404;
   permit explicit new attempts or unsaved tutoring and retry failed startup.
3. `feat(frontend): integrate UI with authenticated conversation restoration`.
   Port layout, theme, logo and safe Markdown; retain host credentials, optional
   saving and authoritative scoped history. Send the actual typed question,
   display pack-independent run results, keep successful live replies visible
   when history fetching fails, and discard stale identity/attempt responses.

All commits use Annabelle <3141330934@qq.com> as author/committer with DCO sign-off.
No new database migration is required; the existing repeatable local migration
and deletion ledger initialization remain in the launcher.

## 3. Run and inspect

From `backend`, use `python -m app.local_dev --save-dialogue`; open its printed
127.0.0.1 URL and opt into saving. This starts both servers and supplies the
synthetic authenticated host. A plain static server does not supply credentials.
`--save-dialogue` enables the provisional one-hour local policy, not production
institutional approval. Normal peer turns still need the configured model service.

The inspected machine had occupied default/alternate ports. Its isolated preview
uses `--api-port 8002 --frontend-port 5175 --data-dir ..\deployment\local\ui-preview`.
`http://127.0.0.1:5175/dev-client.html` uses peer stance by default. An explicit
`?stance=control` is useful for a no-model smoke check, with a fixed support reply.
Synthetic preview examples and screenshots remain under the ignored local folder.

## 4. What output is restored

New live replies render with current Glass Box summaries. Reload restores saved
learner/tutor messages; live signals and run outputs are not conversation history.
Expired/deleted/unavailable attempts clear their pointers and never auto-create a
replacement. Choose New attempt or turn saving off. Current membership is checked
again, and authentication failures still clear the old namespace. Switching ports,
data directories, exercise versions or identities can select a different history.

## 5. Validation and remaining work

Backend: 617 passed, 8 existing/environment skips; Ruff check/format and mypy pass.
After correcting stage timing names to the actual orchestrator contract, all 28
related HTTP/safety tests and the quality gates were rerun successfully.
Frontend: 26 hermetic tests pass. Browser control-mode checks show live replies,
signals, starter-code results and isolated exercise restoration. Desktop/mobile
layouts have no horizontal overflow, and no console errors were observed.
No real identity service or model was called by these checks. PostgreSQL remains
an unconfigured optional check for this preview; previous restoration validation
and the deployment requirements remain in `docs/conversations.md`.

Review the presentation and actual EduCloud host lifecycle before a production
pilot. Institutional retention/backup/ledger approval, issuer/roster integration
and the inherited trace cost/call-field and analysis-reader issues remain open.
This branch adds no queue or shared budget.

Markdown versions are pinned from the primary upstream releases:
[marked 18.0.14](https://github.com/markedjs/marked/releases) and
[DOMPurify 3.4.16](https://github.com/cure53/DOMPurify/releases/tag/3.4.16).

## 6. Suggested pull request

Title: `Integrate Sol UI with authenticated conversation restoration`

Port the responsive Sol presentation onto the authenticated bounded-restoration
dependency while preserving scoped APIs and optional saving. Restore live replies
and screened Glass Box summaries without persisting hidden drafts or transient
signals; allow explicit recovery from unavailable history and prevent overlapping
local listeners. Validate with 617 backend tests, 26 frontend tests, offline browser
checks and Ruff/mypy. The authentication/restoration dependencies remain unmerged;
institutional identity and retention approval are still required for production.

## 7. Student-facing UI follow-up

`1cf3534 fix(frontend): show readable run output instead of API JSON` replaces
the raw response dump with program stdout, execution/check status and optional
check details. Literal output remains safe, and full results still reach Sol.

`feat(frontend): compact the tutoring workspace and conversation controls`
unifies button sizing, padding and gaps; bounds the desktop workspace to the
viewport with internal panel scrolling; puts the composer by the replies; moves
secondary history actions into More; and collapses connection/Glass Box details.
Narrow screens show the conversation first. Optional saving, retention and all
authentication/isolation operations remain intact.

Validation: 28 frontend tests and Ruff check/format/mypy passed. Live control-mode
checks show readable output and no whole-page vertical scroll at 1280x720 and
1024x768; 390x844 shows the composer above the editor without horizontal overflow.
The full backend suite was not repeated for these frontend-only changes.
