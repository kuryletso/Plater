#!/usr/bin/env bash
# Lint changed (staged + unstaged) tracked .py files, excluding tests/.
# Portable: no GNU-only grep/xargs flags; works with macOS bash 3.2.

files=()
while IFS= read -r -d '' f; do
  files+=("$f")
done < <(git diff --name-only --diff-filter=ACMR -z HEAD -- '*.py' ':!tests/*')

if [ ${#files[@]} -eq 0 ]; then
  echo "No changed Python files to check."
  exit 0
fi

exec uv run ruff check "${files[@]}"
