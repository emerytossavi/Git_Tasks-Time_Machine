#!/usr/bin/env bash
# lib/config.sh - Module de configuration et résolution de chemins
# Compatible: bash 3.2+

DEFAULT_REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
DEFAULT_RAW_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"
DEFAULT_BRANCH="main"
DEFAULT_SLM_MODEL="qwen2.5-coder:1.5b"

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
    DEFAULT_MODEL="${DEFAULT_MODEL:-$DEFAULT_SLM_MODEL}"
    export DEFAULT_MODEL
}

config_set_plan_file() {
    local candidate="${1:-commit-plan.json}"
    PLAN_FILE="$candidate"
}

config_set_default_model() {
    local new_model="$1"
    local config_file="$GTM_DIR/config.env"

    if [[ -z "$new_model" ]]; then
        return 1
    fi

    # Nettoyer les guillemets ou espaces superflus
    new_model="$(echo "$new_model" | tr -d '\"'"'" | tr -d ' ')"

    if [[ ! -f "$config_file" ]]; then
        cat <<EOF > "$config_file"
# Git Tasks-Time Machine Configuration
# Standards: POSIX shell variable assignment / sourceable config

REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
REPO_BRANCH="main"
RAW_FILE_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"

# Modèle SLM local par défaut pour 'gtm plan'
DEFAULT_MODEL="$new_model"
EOF
    elif grep -q "^DEFAULT_MODEL=" "$config_file" 2>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp "${TMPDIR:-/tmp}/gtm_config.XXXXXX")"
        sed "s|^DEFAULT_MODEL=.*|DEFAULT_MODEL=\"$new_model\"|" "$config_file" > "$tmp_file"
        mv "$tmp_file" "$config_file"
    else
        printf '\n# Modèle SLM local par défaut pour '\''gtm plan'\''\nDEFAULT_MODEL="%s"\n' "$new_model" >> "$config_file"
    fi

    DEFAULT_MODEL="$new_model"
    export DEFAULT_MODEL
}
