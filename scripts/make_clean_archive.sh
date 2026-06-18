#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain)" ]]; then echo "Uncommitted changes — commit first."; exit 1; fi
mode="${1:-zip}"
if [[ "$mode" == "bundle" ]]; then
  git bundle create ../peer-tutor-sol.bundle --all
  echo "Wrote ../peer-tutor-sol.bundle (clone with: git clone <bundle> peer-tutor-framework)"
else
  git archive --format=zip -o ../peer-tutor-sol.zip HEAD
  echo "Wrote ../peer-tutor-sol.zip (tracked files at HEAD; no secrets/db/traces)"
fi
