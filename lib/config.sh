#!/usr/bin/env bash
# lib/config.sh - Module de configuration et résolution de chemins
# Compatible: bash 3.2+

DEFAULT_REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
DEFAULT_RAW_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"
DEFAULT_BRANCH="main"
DEFAULT_SLM_MODEL="qwen2.5-coder:1.5b"
DEFAULT_OLLAMA_HOST="http://localhost:11434"

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

    OLLAMA_HOST="${OLLAMA_HOST:-${OLLAMA_BASE_URL:-$DEFAULT_OLLAMA_HOST}}"
    if [[ "$OLLAMA_HOST" != http://* ]] && [[ "$OLLAMA_HOST" != https://* ]]; then
        OLLAMA_HOST="http://$OLLAMA_HOST"
    fi
    OLLAMA_HOST="${OLLAMA_HOST%/}"
    export OLLAMA_HOST

    DEFAULT_LANG="${DEFAULT_LANG:-en}"
    DEFAULT_LANG="$(echo "$DEFAULT_LANG" | tr '[:upper:]' '[:lower:]' | tr -d ' ')"
    export DEFAULT_LANG
}

config_ensure_gtm_dir() {
    local target_dir="${1:-.gtm}"
    if [[ ! -d "$target_dir" ]]; then
        mkdir -p "$target_dir"
    fi
    if [[ ! -f "$target_dir/.gitignore" ]]; then
        printf '*\n' > "$target_dir/.gitignore"
    fi
}

config_set_plan_file() {
    local candidate="${1:-}"
    if [[ -n "$candidate" ]]; then
        PLAN_FILE="$candidate"
    elif [[ -f ".gtm/commit-plan.json" ]]; then
        PLAN_FILE=".gtm/commit-plan.json"
    elif [[ -f "commit-plan.json" ]]; then
        PLAN_FILE="commit-plan.json"
    else
        PLAN_FILE=".gtm/commit-plan.json"
    fi
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

config_set_ollama_host() {
    local new_host="$1"
    local config_file="$GTM_DIR/config.env"

    if [[ -z "$new_host" ]]; then
        return 1
    fi

    # Nettoyer les guillemets ou espaces superflus
    new_host="$(echo "$new_host" | tr -d '\"'"'" | tr -d ' ')"
    if [[ "$new_host" != http://* ]] && [[ "$new_host" != https://* ]]; then
        new_host="http://$new_host"
    fi
    new_host="${new_host%/}"

    if [[ ! -f "$config_file" ]]; then
        cat <<EOF > "$config_file"
# Git Tasks-Time Machine Configuration
# Standards: POSIX shell variable assignment / sourceable config

REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
REPO_BRANCH="main"
RAW_FILE_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"

# Modèle SLM local par défaut pour 'gtm plan'
DEFAULT_MODEL="qwen2.5-coder:1.5b"

# Hôte du serveur Ollama
OLLAMA_HOST="$new_host"
EOF
    elif grep -q "^OLLAMA_HOST=" "$config_file" 2>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp "${TMPDIR:-/tmp}/gtm_config.XXXXXX")"
        sed "s|^OLLAMA_HOST=.*|OLLAMA_HOST=\"$new_host\"|" "$config_file" > "$tmp_file"
        mv "$tmp_file" "$config_file"
    else
        printf '\n# Hôte du serveur Ollama\nOLLAMA_HOST="%s"\n' "$new_host" >> "$config_file"
    fi

    OLLAMA_HOST="$new_host"
    export OLLAMA_HOST
}

config_set_default_lang() {
    local new_lang="$1"
    local config_file="$GTM_DIR/config.env"

    if [[ -z "$new_lang" ]]; then
        return 1
    fi

    # Nettoyer les guillemets ou espaces superflus et convertir en minuscules
    new_lang="$(echo "$new_lang" | tr -d '\"'"'" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"

    if [[ ! -f "$config_file" ]]; then
        cat <<EOF > "$config_file"
# Git Tasks-Time Machine Configuration
# Standards: POSIX shell variable assignment / sourceable config

REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
REPO_BRANCH="main"
RAW_FILE_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"

DEFAULT_MODEL="qwen2.5-coder:1.5b"
OLLAMA_HOST="http://localhost:11434"
DEFAULT_LANG="$new_lang"
EOF
    elif grep -q "^DEFAULT_LANG=" "$config_file" 2>/dev/null; then
        local tmp_file
        tmp_file="$(mktemp "${TMPDIR:-/tmp}/gtm_config.XXXXXX")"
        sed "s|^DEFAULT_LANG=.*|DEFAULT_LANG=\"$new_lang\"|" "$config_file" > "$tmp_file"
        mv "$tmp_file" "$config_file"
    else
        printf '\n# Langue des messages de commit générés\nDEFAULT_LANG="%s"\n' "$new_lang" >> "$config_file"
    fi

    DEFAULT_LANG="$new_lang"
    export DEFAULT_LANG
}

lang_cmd() {
    if [[ $# -eq 0 ]]; then
        echo "=== Configuration de la langue des commits (config.env) ==="
        printf "• Langue active : \033[1;32m%s\033[0m\n" "${DEFAULT_LANG:-en}"
        echo
        echo "Pour changer la langue par défaut :"
        echo "  gtm lang <en|fr|es|de|...>"
        echo
        echo "Options :"
        echo "  -l, --list    Lister les principales langues supportées"
        echo "  -h, --help    Afficher l'aide de la commande"
        echo
        echo "Note : Les types Conventional Commits (feat, fix, docs...) restent toujours standardisés."
        return 0
    fi

    case "$1" in
        --help|-h)
            echo "Usage: gtm lang [code_langue]"
            echo
            echo "Consulte ou configure la langue par défaut pour la rédaction des commits."
            echo "Options :"
            echo "  -l, --list    Lister les principales langues supportées"
            echo "  -h, --help    Afficher cette aide"
            return 0
            ;;
        --list|-l)
            echo "=== Langues supportées pour la génération des commits ==="
            echo "  • en : English (défaut)"
            echo "  • fr : Français"
            echo "  • es : Español"
            echo "  • de : Deutsch"
            echo "  • it : Italiano"
            echo "  • pt : Português"
            echo "  • nl : Nederlands"
            echo "  • ru : Русский"
            echo "  • zh : 中文"
            echo "  • ja : 日本語"
            return 0
            ;;
    esac

    local target_lang="$1"
    target_lang="$(echo "$target_lang" | tr -d '\"'"'" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
    if [[ -z "$target_lang" ]]; then
        log_error "Code de langue vide ou non spécifié."
        return 1
    fi

    if [[ ! "$target_lang" =~ ^[a-z]{2}(-[a-z]{2,4})?$ ]]; then
        log_error "Code de langue invalide : '$1'. Utilisez un code ISO court (ex: en, fr, es, de, pt-br)."
        return 1
    fi

    if config_set_default_lang "$target_lang"; then
        log_ok "Langue par défaut mise à jour avec succès : '$DEFAULT_LANG' (sauvegardée dans config.env)"
        return 0
    else
        log_error "Impossible d'enregistrer la langue dans config.env"
        return 1
    fi
}
