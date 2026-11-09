#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Stored source envelopes currently have no trailing-whitespace baseline.
# Check every changed path, including sources/** (no blanket exemption).
set -euo pipefail
base=${1:?whitespace base required}
if [ "$base" = "$(git rev-parse HEAD)" ]; then
  echo 'Whitespace check skipped: no new commits (rewind or unchanged HEAD).'
  exit 0
fi
git diff --check "$base" HEAD
