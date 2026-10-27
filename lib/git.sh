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
    git add -A -- "$file"
}

git_is_file_deleted() {
    local file="$1"
    if [[ ! -e "$file" ]]; then
        if git status --porcelain -uall -- "$file" 2>/dev/null | grep -q '^.D\|^D'; then
            return 0
        fi
        if git ls-files --error-unmatch -- "$file" >/dev/null 2>&1; then
            return 0
        fi
        if git ls-tree -r --name-only HEAD -- "$file" 2>/dev/null | grep -qx "$file"; then
            return 0
        fi
    fi
    return 1
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

git_get_head_hash() {
    local short="${1:-true}"
    if [[ "$short" == "true" ]]; then
        git rev-parse --short HEAD 2>/dev/null || echo ""
    else
        git rev-parse HEAD 2>/dev/null || echo ""
    fi
}
