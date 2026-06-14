#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "$(git status --porcelain)" ]]; then echo "Uncommitted changes — commit first."; exit 1; fi
mode="${1:-zip}"
if [[ "$mode" == "bundle" ]]; then
  git bundle create ../quantum-inventioneers-sol.bundle --all
  echo "Wrote ../quantum-inventioneers-sol.bundle (clone with: git clone <bundle> quantum-inventioneers)"
else
  git archive --format=zip -o ../quantum-inventioneers-sol.zip HEAD
  echo "Wrote ../quantum-inventioneers-sol.zip (tracked files at HEAD; no secrets/db/traces)"
fi
