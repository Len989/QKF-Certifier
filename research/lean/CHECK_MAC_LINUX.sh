#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if ! command -v lake >/dev/null 2>&1; then
  echo 'Lean is not installed or this terminal needs to be reopened.'
  echo 'Follow 00_START_HERE_RU.md, then run this script again.'
  exit 1
fi
{
  lake env lean --version
  lake build
} 2>&1 | tee CHECK_LOG.txt
echo 'QKF CHECK PASSED. Full log: CHECK_LOG.txt'
