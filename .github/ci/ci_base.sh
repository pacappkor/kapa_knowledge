#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
# Resolve once for both changed-path selection and whitespace checking.
set -euo pipefail
base=
all=true
rewind=false
candidate=${CI_BEFORE:-}
if [ "${CI_EVENT:-}" = pull_request ]; then
  candidate=${CI_BASE:-}
fi
if [ "${CI_EVENT:-}" != workflow_dispatch ] && [ -n "$candidate" ] &&
   [[ ! "$candidate" =~ ^0+$ ]] &&
   git rev-parse --verify --quiet "$candidate^{commit}" >/dev/null; then
  if [ "${CI_EVENT:-}" = pull_request ]; then
    if git merge-base "$candidate" HEAD >/dev/null; then
      base=$candidate
      all=false
    fi
  elif git merge-base --is-ancestor "$candidate" HEAD; then
    base=$candidate
    all=false
  else
    # A rewritten branch must run every group, even with a common ancestor.
    base=$(git merge-base "$candidate" HEAD) || base=
    # Rewinding to an ancestor otherwise produces an empty HEAD..HEAD diff.
    if [ "$base" = "$(git rev-parse HEAD)" ]; then
      rewind=true
    fi
  fi
fi
whitespace=$base
if [ "$rewind" = true ]; then
  whitespace=$(git rev-parse HEAD)
  note='Whitespace check skipped: rewind introduces no new commits; all other checks selected.'
  printf '%s\n' "$note" >&2
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    printf '\n- %s\n' "$note" >> "$GITHUB_STEP_SUMMARY"
  fi
elif ! git rev-parse --verify --quiet 'HEAD^' >/dev/null; then
  whitespace=$(git hash-object -t tree /dev/null)
elif [ "${CI_EVENT:-}" = workflow_dispatch ]; then
  whitespace=$(git rev-parse 'HEAD^')
elif [ -z "$whitespace" ]; then
  whitespace=$(git hash-object -t tree /dev/null)
fi
printf 'base=%s\nall=%s\nwhitespace_base=%s\n' "$base" "$all" "$whitespace"
