#!/usr/bin/env bash
# lib/git.sh - Module d'abstraction des commandes Git
# Compatible: bash 3.2+

git_is_worktree() {
    git rev-parse --is-inside-work-tree >/dev/null 2>&1
}

git_reset_stage() {
    git reset >/dev/null 2>&1
}

git_stage_file() {
    local file="$1"
    git add -- "$file"
}

git_has_staged_changes() {
    ! git diff --cached --quiet
}

git_create_commit() {
    local commit_date="$1"
    local commit_message="$2"

    GIT_COMMITTER_DATE="$commit_date" \
    git commit --date "$commit_date" -F - <<EOF
$commit_message
EOF
}
