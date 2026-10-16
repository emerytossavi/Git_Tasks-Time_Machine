#!/usr/bin/env bash
# lib/runner.sh - Moteur d'exécution des plans (modes simulation et réel)
# Compatible: bash 3.2+

runner_dry_run() {
    local plan_file="${1:-$PLAN_FILE}"
    validator_validate_plan "$plan_file" >/dev/null

    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        validator_parse_commit "$commit"

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        fs_readarray patterns "$patterns_output"

        local expanded=()
        local p
        for p in "${patterns[@]}"; do
            local matches=()
            fs_expand_pattern "$p"
            expanded+=("${matches[@]}")
        done

        log_report "DRY-RUN" "Commit #$idx"
        echo "Date: $COMMIT_DATE"
        echo "Message:"
        printf '%s\n' "$COMMIT_MESSAGE"
        echo "Fichiers:"
        printf '  - %s\n' "${expanded[@]}"
        echo

    done < <(jq -c '.commits[]' "$plan_file")
}

runner_run() {
    local plan_file="${1:-$PLAN_FILE}"
    validator_validate_plan "$plan_file" >/dev/null

    if ! git_is_worktree; then
        log_error "Le dossier courant n'est pas un dépôt Git"
        exit 1
    fi

    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        validator_parse_commit "$commit"

        log_report "RUN" "Traitement commit #$idx"

        git_reset_stage

        local patterns_output
        patterns_output=$(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        local patterns=()
        fs_readarray patterns "$patterns_output"

        local p
        for p in "${patterns[@]}"; do
            local matches=()
            fs_expand_pattern "$p"

            local m
            for m in "${matches[@]}"; do
                git_stage_file "$m"
            done
        done

        if ! git_has_staged_changes; then
            log_warn "Commit #$idx: aucun changement indexé, commit ignoré"
            continue
        fi

        git_create_commit "$COMMIT_DATE" "$COMMIT_MESSAGE"

        log_ok "Commit #$idx créé"

    done < <(jq -c '.commits[]' "$plan_file")
}

# Alias pour compatibilité
dry_run() {
    runner_dry_run "$@"
}

run_plan() {
    runner_run "$@"
}
