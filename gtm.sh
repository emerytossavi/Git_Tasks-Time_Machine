#!/usr/bin/env bash
# gtm.sh - Git Tasks Time Machine
# Compatible: bash 3.2+ (macOS), bash 4/5 (Linux), Git Bash (Windows)
set -euo pipefail

# Resolve the actual script location (follow symlinks, cross-platform bash 3.2+)
SOURCE="${BASH_SOURCE[0]}"
while [[ -h "$SOURCE" ]]; do
    TARGET="$(readlink "$SOURCE")"
    if [[ "$TARGET" == /* ]]; then
        SOURCE="$TARGET"
    else
        SOURCE="$(dirname "$SOURCE")/$TARGET"
    fi
done
GTM_DIR="$(cd -P "$(dirname "$SOURCE")" && pwd)"
GTM_FILE="$GTM_DIR/$(basename "$SOURCE")"

# Load default remote repo configuration if available
DEFAULT_REPO_URL="https://github.com/emerytossavi/Git_Tasks-Time_Machine.git"
DEFAULT_RAW_URL="https://raw.githubusercontent.com/emerytossavi/Git_Tasks-Time_Machine/main/gtm.sh"
DEFAULT_BRANCH="main"

if [[ -f "$GTM_DIR/config.env" ]]; then
    # shellcheck disable=SC1091
    source "$GTM_DIR/config.env"
fi

REPO_URL="${REPO_URL:-$DEFAULT_REPO_URL}"
RAW_FILE_URL="${RAW_FILE_URL:-$DEFAULT_RAW_URL}"
REPO_BRANCH="${REPO_BRANCH:-$DEFAULT_BRANCH}"

PLAN_FILE="${2:-commit-plan.json}"


# ---------------------------------------------------------------------------
# Cross-platform ISO 8601 date parsing
#
# Strategy detection is done once in _detect_date_cmd, called from main().
# DATE_CMD  : the `date` binary to use ("gdate" or "date")
# DATE_STRATEGY : "gnu" or "bsd"
#
# iso_to_epoch <iso8601-string>  -> prints Unix timestamp, returns 1 on error
# is_valid_date <iso8601-string> -> returns 0 if parseable, 1 otherwise
# ---------------------------------------------------------------------------
DATE_CMD="date"
DATE_STRATEGY="gnu"

_detect_date_cmd() {
    # 1. gdate (GNU coreutils installed via Homebrew on macOS)
    if command -v gdate >/dev/null 2>&1; then
        DATE_CMD="gdate"
        DATE_STRATEGY="gnu"
        return
    fi

    # 2. Native date with GNU -d flag (Linux, Git Bash)
    if date -d "2000-01-01T00:00:00+00:00" '+%s' >/dev/null 2>&1; then
        DATE_CMD="date"
        DATE_STRATEGY="gnu"
        return
    fi

    # 3. BSD date (macOS system date without gdate)
    DATE_CMD="date"
    DATE_STRATEGY="bsd"
}

# Convert ISO 8601 string (with optional +HH:MM offset) to Unix timestamp.
# Prints the epoch integer; returns 1 on error.
iso_to_epoch() {
    local iso="$1"

    if [[ "$DATE_STRATEGY" == "gnu" ]]; then
        "$DATE_CMD" -d "$iso" '+%s' 2>/dev/null
        return $?
    fi

    # BSD: strptime %z accepts "+0100" but not "+01:00" — strip the colon.
    local normalized
    normalized=$(printf '%s' "$iso" | sed 's/\([+-][0-9][0-9]\):\([0-9][0-9]\)$/\1\2/')

    "$DATE_CMD" -j -f '%Y-%m-%dT%H:%M:%S%z' "$normalized" '+%s' 2>/dev/null
    return $?
}

# Return 0 if the string is a parseable ISO 8601 date, 1 otherwise.
is_valid_date() {
    iso_to_epoch "$1" >/dev/null 2>&1
}

# ---------------------------------------------------------------------------
# Compatibility helper: read lines from a process substitution into an array.
# Usage: read_lines_into array_name < <(command)
#   but because bash 3.2 does not have mapfile/readarray, we use a while loop.
#
# Call as:  _readarray myarray "$(command)"
# (passes output as a single string to avoid subshell scope issues)
# ---------------------------------------------------------------------------
_readarray() {
    local _arr_name="$1"
    local _input="$2"
    local IFS=$'\n'
    local _line
    local _i=0

    # Reset the named array
    eval "${_arr_name}=()"

    while IFS= read -r _line; do
        eval "${_arr_name}+=(\"\$_line\")"
        _i=$((_i + 1))
    done <<EOF
$_input
EOF
}

# ---------------------------------------------------------------------------

print_report() {
    local level="$1"
    local message="$2"
    printf '[%s] %s\n' "$level" "$message"
}

# Expand a glob pattern into the local `matches` array.
# Compatible with bash 3.2 (no globstar).
_expand_pattern() {
    local pattern="$1"
    local _old_nullglob
    local IFS=$'\n'
    _old_nullglob=$(shopt -p nullglob 2>/dev/null || true)

    shopt -s nullglob
    # SC2206: intentional word-splitting for glob expansion; keep spaces in paths
    # shellcheck disable=SC2206
    matches=($pattern)

    eval "$_old_nullglob" 2>/dev/null || true
}

load_plan() {
    if [[ ! -f "$PLAN_FILE" ]]; then
        print_report "ERROR" "Fichier plan introuvable: $PLAN_FILE"
        exit 1
    fi

    if ! jq -e '.' "$PLAN_FILE" >/dev/null 2>&1; then
        print_report "ERROR" "JSON invalide dans $PLAN_FILE"
        exit 1
    fi

    if ! jq -e '.commits | type == "array"' "$PLAN_FILE" >/dev/null 2>&1; then
        print_report "ERROR" "Le plan doit contenir une clé 'commits' de type tableau"
        exit 1
    fi

    local count
    count=$(jq '.commits | length' "$PLAN_FILE")

    if (( count == 0 )); then
        print_report "ERROR" "Le plan ne contient aucun commit"
        exit 1
    fi
}

process_commit() {
    local commit="$1"

    COMMIT_DATE=$(jq -r '.date' <<<"$commit" | tr -d '\r')
    COMMIT_MESSAGE=$(jq -r '.message' <<<"$commit" | tr -d '\r')
    COMMIT_FILES_JSON=$(jq -c '.files' <<<"$commit" | tr -d '\r')
}

validate_plan() {
    load_plan

    local prev_epoch=""
    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        if ! is_valid_date "$COMMIT_DATE"; then
            print_report "ERROR" "Commit #$idx: date invalide (ISO8601 attendu): $COMMIT_DATE"
            exit 1
        fi

        local current_epoch
        current_epoch=$(iso_to_epoch "$COMMIT_DATE")

        if [[ -n "$prev_epoch" ]] && (( current_epoch < prev_epoch )); then
            print_report "ERROR" "Commit #$idx: ordre chronologique invalide"
            exit 1
        fi

        prev_epoch="$current_epoch"

        if [[ -z "${COMMIT_MESSAGE//[[:space:]]/}" ]]; then
            print_report "ERROR" "Commit #$idx: message vide"
            exit 1
        fi

        if ! jq -e 'type=="array" and length>0' <<<"$COMMIT_FILES_JSON" >/dev/null 2>&1; then
            print_report "ERROR" "Commit #$idx: 'files' doit être un tableau non vide"
            exit 1
        fi

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        _readarray patterns "$patterns_output"

        local p
        for p in "${patterns[@]}"; do
            local matches=()
            _expand_pattern "$p"

            if (( ${#matches[@]} == 0 )); then
                print_report "ERROR" "Commit #$idx: pattern sans correspondance: $p"
                exit 1
            fi

            local m
            for m in "${matches[@]}"; do
                if [[ ! -e "$m" ]]; then
                    print_report "ERROR" "Commit #$idx: fichier inexistant: $m"
                    exit 1
                fi
            done
        done

    done < <(jq -c '.commits[]' "$PLAN_FILE")

    print_report "OK" "Validation réussie ($idx commit(s))"
}

dry_run() {
    validate_plan >/dev/null

    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        _readarray patterns "$patterns_output"

        local expanded=()
        local p
        for p in "${patterns[@]}"; do
            local matches=()
            _expand_pattern "$p"
            expanded+=("${matches[@]}")
        done

        print_report "DRY-RUN" "Commit #$idx"
        echo "Date: $COMMIT_DATE"
        echo "Message:"
        printf '%s\n' "$COMMIT_MESSAGE"
        echo "Fichiers:"
        printf '  - %s\n' "${expanded[@]}"
        echo

    done < <(jq -c '.commits[]' "$PLAN_FILE")
}

run_plan() {
    validate_plan >/dev/null

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        print_report "ERROR" "Le dossier courant n'est pas un dépôt Git"
        exit 1
    fi

    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        print_report "RUN" "Traitement commit #$idx"

        git reset

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        _readarray patterns "$patterns_output"

        local p
        for p in "${patterns[@]}"; do
            local matches=()
            _expand_pattern "$p"

            local m
            for m in "${matches[@]}"; do
                git add -- "$m"
            done
        done

        if git diff --cached --quiet; then
            print_report "WARN" "Commit #$idx: aucun changement indexé, commit ignoré"
            continue
        fi

        GIT_COMMITTER_DATE="$COMMIT_DATE" \
        git commit --date "$COMMIT_DATE" -F - <<EOF
$COMMIT_MESSAGE
EOF

        print_report "OK" "Commit #$idx créé"

    done < <(jq -c '.commits[]' "$PLAN_FILE")
}

update_gtm() {
    print_report "INFO" "Vérification des mises à jour pour Git Tasks-Time Machine..."
    print_report "INFO" "Dépôt distant : $REPO_URL"
    print_report "INFO" "Emplacement local : $GTM_DIR"

    # Vérification si le script fait partie d'un clone Git local
    if git -C "$GTM_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        print_report "INFO" "Mise à jour via Git..."

        # Tirer directement depuis l'URL publique avec fast-forward pour éviter tout blocage SSH/prompt
        if GIT_TERMINAL_PROMPT=0 git -C "$GTM_DIR" pull --ff-only "$REPO_URL" "$REPO_BRANCH" 2>/dev/null || \
           GIT_TERMINAL_PROMPT=0 git -C "$GTM_DIR" pull --ff-only 2>/dev/null; then
            chmod +x "$GTM_FILE" 2>/dev/null || true
            print_report "OK" "Git Tasks-Time Machine a été mis à jour avec succès via Git !"
            return 0
        else
            print_report "WARN" "Impossible d'effectuer un git pull --ff-only direct. Tentative de téléchargement direct..."
        fi
    fi

    # Fallback si ce n'est pas un repo git ou si git pull a échoué
    print_report "INFO" "Téléchargement de la dernière version ($RAW_FILE_URL)..."
    local tmp_file
    tmp_file="$(mktemp "${TMPDIR:-/tmp}/gtm.sh.XXXXXX")"

    local download_ok=1
    if command -v curl >/dev/null 2>&1; then
        if curl -fsSL "$RAW_FILE_URL" -o "$tmp_file"; then
            download_ok=0
        fi
    elif command -v wget >/dev/null 2>&1; then
        if wget -qO "$tmp_file" "$RAW_FILE_URL"; then
            download_ok=0
        fi
    else
        print_report "ERROR" "Ni 'curl' ni 'wget' n'est installé pour télécharger la mise à jour."
        rm -f "$tmp_file"
        return 1
    fi

    if [[ $download_ok -eq 0 && -s "$tmp_file" ]]; then
        # Télécharger également config.env s'il n'existe pas localement
        local raw_config_url
        raw_config_url="$(dirname "$RAW_FILE_URL")/config.env"
        if [[ ! -f "$GTM_DIR/config.env" ]]; then
            curl -fsSL "$raw_config_url" -o "$GTM_DIR/config.env" 2>/dev/null || true
        fi

        mv "$tmp_file" "$GTM_FILE"
        chmod +x "$GTM_FILE"
        print_report "OK" "Git Tasks-Time Machine a été mis à jour avec succès !"
    else
        rm -f "$tmp_file"
        print_report "ERROR" "Échec du téléchargement de la mise à jour depuis $RAW_FILE_URL"
        return 1
    fi
}

main() {
    if [[ $# -lt 1 || $# -gt 2 ]]; then
        cat <<USAGE
Usage: gtm <validate|dry-run|run> [chemin/vers/plan.json]
       gtm <update|--update|-update|--u|-u>

Commandes :
  validate [plan.json]  Vérifie la conformité du plan JSON.
  dry-run  [plan.json]  Simule l'exécution sans toucher à Git.
  run      [plan.json]  Exécute les commits du plan dans le dépôt courant.
  update                Met à jour Git Tasks-Time Machine depuis le dépôt public.
                        (Alias acceptés : --update, -update, --u, -u)

Si le chemin du plan est omis, "./commit-plan.json" (relatif au
dossier courant) est utilisé. "run" et "dry-run" opèrent toujours
sur le dépôt Git du dossier courant.
USAGE
        exit 1
    fi

    # Detect a cross-platform date command once before any subcommand runs
    _detect_date_cmd

    case "$1" in
        update|--update|-update|--u|-u)
            update_gtm
            ;;
        validate)
            validate_plan
            ;;
        dry-run)
            dry_run
            ;;
        run)
            run_plan
            ;;
        *)
            print_report "ERROR" "Commande inconnue: $1"
            print_report "INFO" "Commandes disponibles: validate, dry-run, run, update (--u, -update)"
            exit 1
            ;;
    esac
}

main "$@"