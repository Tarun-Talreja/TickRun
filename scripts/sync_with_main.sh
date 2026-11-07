#!/usr/bin/env bash
# Pull while keeping this job's changes. Two jobs can regenerate the same data file,
# and the conflict used to fail the commit and lose the rest of the run's work. The
# other job's copy wins: these files are generated, so the next run refreshes them.
set -euo pipefail

git pull --rebase --autostash origin main

conflicted=$(git diff --name-only --diff-filter=U)
if [ -n "$conflicted" ]; then
  echo "Kept the newer copy of: $conflicted"
  echo "$conflicted" | xargs git checkout HEAD --
  git reset -q
  git stash drop -q
fi
