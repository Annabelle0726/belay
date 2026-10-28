# Development page rendering assets

These browser files are copied unchanged from the pinned npm packages in
`frontend/package-lock.json`. The development page needs no build or CDN access
for Markdown rendering. This keeps the existing Marked → DOMPurify renderer and
adds Highlight.js for language-tagged fenced code. Unknown languages stay literal.
Student text is never parsed as Markdown. The widget is unchanged.

| File | Package / version | Upstream file | License |
|---|---|---|---|
| marked.umd.js | marked 18.0.14 | lib/marked.umd.js | MIT, marked.LICENSE.md |
| purify.min.js | dompurify 3.4.16 | dist/purify.min.js | Apache-2.0 OR MPL-2.0, dompurify.LICENSE / dompurify.LICENSE-MPL |
| highlight.min.js | @highlightjs/cdn-assets 11.11.1 | highlight.min.js | BSD-3-Clause, highlight.LICENSE |

Install test dependencies with `npm ci --ignore-scripts` in `frontend`.
When deliberately upgrading an asset, copy its listed upstream file and license
from `node_modules`, then run `npm test`. Asset equality and actual sanitized DOM
rendering are checked by the tests. Never edit the vendored library source.
