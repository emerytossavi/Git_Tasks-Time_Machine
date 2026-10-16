#!/usr/bin/env bash
# lib/config.sh - Module de configuration et résolution de chemins
# Compatible: bash 3.2+

DEFAULT_REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
DEFAULT_RAW_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"
DEFAULT_BRANCH="main"

config_init() {
    local source_script="$1"

    # Résoudre l'emplacement réel du script (suivre les liens symboliques sous bash 3.2+)
    local target
    while [[ -h "$source_script" ]]; do
        target="$(readlink "$source_script")"
        if [[ "$target" == /* ]]; then
            source_script="$target"
        else
            source_script="$(dirname "$source_script")/$target"
        fi
    done

    GTM_DIR="$(cd -P "$(dirname "$source_script")" && pwd)"
    GTM_FILE="$GTM_DIR/$(basename "$source_script")"

    # Charger le fichier config.env s'il est présent
    if [[ -f "$GTM_DIR/config.env" ]]; then
        # shellcheck disable=SC1091
        source "$GTM_DIR/config.env"
    fi

    REPO_URL="${REPO_URL:-$DEFAULT_REPO_URL}"
    RAW_FILE_URL="${RAW_FILE_URL:-$DEFAULT_RAW_URL}"
    REPO_BRANCH="${REPO_BRANCH:-$DEFAULT_BRANCH}"
}

config_set_plan_file() {
    local candidate="${1:-commit-plan.json}"
    PLAN_FILE="$candidate"
}
