#!/usr/bin/env bash
# lib/validator.sh - Module de validation et vérification du plan JSON
# Compatible: bash 3.2+

validator_parse_commit() {
    local commit="$1"
    COMMIT_DATE=$(jq -r '.date' <<<"$commit" | tr -d '\r')
    COMMIT_MESSAGE=$(jq -r '.message' <<<"$commit" | tr -d '\r')
    COMMIT_FILES_JSON=$(jq -c '.files' <<<"$commit" | tr -d '\r')
}

# Alias pour compatibilité interne
process_commit() {
    validator_parse_commit "$@"
}

validator_load_plan() {
    local plan_file="${1:-$PLAN_FILE}"

    if [[ ! -f "$plan_file" ]]; then
        log_error "Fichier plan introuvable: $plan_file"
        exit 1
    fi

    if ! jq -e '.' "$plan_file" >/dev/null 2>&1; then
        log_error "JSON invalide dans $plan_file"
        exit 1
    fi

    if ! jq -e '.commits | type == "array"' "$plan_file" >/dev/null 2>&1; then
        log_error "Le plan doit contenir une clé 'commits' de type tableau"
        exit 1
    fi

    local count
    count=$(jq '.commits | length' "$plan_file")

    if (( count == 0 )); then
        log_error "Le plan ne contient aucun commit"
        exit 1
    fi
}

validator_validate_plan() {
    local plan_file="${1:-$PLAN_FILE}"
    validator_load_plan "$plan_file"

    local prev_epoch=""
    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        validator_parse_commit "$commit"

        if ! date_is_valid "$COMMIT_DATE"; then
            log_error "Commit #$idx: date invalide (ISO8601 attendu): $COMMIT_DATE"
            exit 1
        fi

        local current_epoch
        current_epoch=$(date_iso_to_epoch "$COMMIT_DATE")

        if [[ -n "$prev_epoch" ]] && (( current_epoch < prev_epoch )); then
            log_error "Commit #$idx: ordre chronologique invalide"
            exit 1
        fi

        prev_epoch="$current_epoch"

        if [[ -z "${COMMIT_MESSAGE//[[:space:]]/}" ]]; then
            log_error "Commit #$idx: message vide"
            exit 1
        fi

        if ! jq -e 'type=="array" and length>0' <<<"$COMMIT_FILES_JSON" >/dev/null 2>&1; then
            log_error "Commit #$idx: 'files' doit être un tableau non vide"
            exit 1
        fi

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        fs_readarray patterns "$patterns_output"

        local p
        for p in "${patterns[@]}"; do
            local matches=()
            fs_expand_pattern "$p"

            if (( ${#matches[@]} == 0 )); then
                log_error "Commit #$idx: pattern sans correspondance: $p"
                exit 1
            fi

            local m
            for m in "${matches[@]}"; do
                if [[ ! -e "$m" ]]; then
                    if ! git_is_file_deleted "$m"; then
                        log_error "Commit #$idx: fichier inexistant: $m"
                        exit 1
                    fi
                fi
            done
        done

    done < <(jq -c '.commits[]' "$plan_file")

    log_ok "Validation réussie ($idx commit(s))"
}

# Alias pour compatibilité
load_plan() {
    validator_load_plan "$@"
}

validate_plan() {
    validator_validate_plan "$@"
}
