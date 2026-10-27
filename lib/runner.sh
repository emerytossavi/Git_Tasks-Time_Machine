#!/usr/bin/env bash
# lib/runner.sh - Moteur d'exécution des plans (modes simulation et réel avec suivi d'état et archivage)
# Compatible: bash 3.2+

runner_dry_run() {
    local force=false
    local plan_file=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)
                force=true
                shift
                ;;
            -*)
                shift
                ;;
            *)
                if [[ -z "$plan_file" ]]; then
                    plan_file="$1"
                fi
                shift
                ;;
        esac
    done

    plan_file="${plan_file:-$PLAN_FILE}"
    validator_validate_plan "$plan_file" >/dev/null

    local total_commits
    total_commits=$(jq '.commits | length' "$plan_file" 2>/dev/null || echo "0")

    local applied_commits
    applied_commits=$(jq '[.commits[] | select(.status == "applied")] | length' "$plan_file" 2>/dev/null || echo "0")

    if [[ "$force" != "true" ]] && (( total_commits > 0 && applied_commits == total_commits )); then
        log_info "Tous les commits de ce plan ($total_commits/$total_commits) ont déjà été appliqués dans Git."
        log_info "Simulation terminée (0 commit en attente). Utilisez '--force' pour simuler une ré-exécution."
        return 0
    fi

    local idx=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))

        validator_parse_commit "$commit"

        local commit_status
        commit_status=$(jq -r '.status // empty' <<<"$commit" | tr -d '\r')
        local existing_hash
        existing_hash=$(jq -r '.commit_hash // empty' <<<"$commit" | tr -d '\r')

        local status_tag=""
        if [[ "$commit_status" == "applied" ]]; then
            status_tag=" [APPLIQUÉ - ${existing_hash:-déjà commité}]"
        fi

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

        log_report "DRY-RUN" "Commit #$idx$status_tag"
        echo "Date: $COMMIT_DATE"
        echo "Message:"
        printf '%s\n' "$COMMIT_MESSAGE"
        echo "Fichiers:"
        local f
        for f in "${expanded[@]}"; do
            if [[ ! -e "$f" ]]; then
                printf '  - %s [supprimé]\n' "$f"
            else
                printf '  - %s\n' "$f"
            fi
        done
        echo

    done < <(jq -c '.commits[]' "$plan_file")
}

runner_run() {
    local force=false
    local reset=false
    local plan_file=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force|-f)
                force=true
                shift
                ;;
            --reset)
                reset=true
                shift
                ;;
            -*)
                log_error "Option inconnue pour run: $1"
                exit 1
                ;;
            *)
                if [[ -z "$plan_file" ]]; then
                    plan_file="$1"
                fi
                shift
                ;;
        esac
    done

    plan_file="${plan_file:-$PLAN_FILE}"
    validator_validate_plan "$plan_file" >/dev/null

    if ! git_is_worktree; then
        log_error "Le dossier courant n'est pas un dépôt Git"
        exit 1
    fi

    if [[ "$reset" == "true" ]]; then
        local tmp_plan
        tmp_plan="$(mktemp "${TMPDIR:-/tmp}/gtm_plan.XXXXXX")"
        if jq 'del(.commits[].status, .commits[].commit_hash, .commits[].applied_at)' "$plan_file" > "$tmp_plan"; then
            mv "$tmp_plan" "$plan_file"
            log_info "Statut d'exécution du plan réinitialisé."
        else
            rm -f "$tmp_plan"
        fi
    fi

    local total_commits
    total_commits=$(jq '.commits | length' "$plan_file" 2>/dev/null || echo "0")

    local applied_commits
    applied_commits=$(jq '[.commits[] | select(.status == "applied")] | length' "$plan_file" 2>/dev/null || echo "0")

    if [[ "$force" != "true" ]] && (( total_commits > 0 && applied_commits == total_commits )); then
        log_info "Tous les commits de ce plan ($total_commits/$total_commits) ont déjà été appliqués dans Git."
        log_info "Aucun nouveau commit à créer. Utilisez 'gtm run --force' pour forcer ou 'gtm plan' pour régénérer un plan."
        return 0
    fi

    local idx=0
    local created_count=0
    local commit

    while IFS= read -r commit; do
        idx=$((idx + 1))
        local zero_idx=$((idx - 1))

        validator_parse_commit "$commit"

        local commit_status
        commit_status=$(jq -r '.status // empty' <<<"$commit" | tr -d '\r')
        local existing_hash
        existing_hash=$(jq -r '.commit_hash // empty' <<<"$commit" | tr -d '\r')

        if [[ "$force" != "true" && "$commit_status" == "applied" ]]; then
            log_info "Commit #$idx: déjà appliqué (hash: ${existing_hash:-inconnu}), ignoré"
            continue
        fi

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
            local tmp_plan
            tmp_plan="$(mktemp "${TMPDIR:-/tmp}/gtm_plan.XXXXXX")"
            if jq --arg idx "$zero_idx" \
                '.commits[($idx | tonumber)] += {status: "applied", commit_hash: "skipped", applied_at: (now | todateiso8601)}' \
                "$plan_file" > "$tmp_plan"; then
                mv "$tmp_plan" "$plan_file"
            else
                rm -f "$tmp_plan"
            fi
            continue
        fi

        git_create_commit "$COMMIT_DATE" "$COMMIT_MESSAGE"
        local new_hash
        new_hash=$(git_get_head_hash true)

        # Mettre à jour atomiquement le plan JSON avec le statut et le hash réel
        local tmp_plan
        tmp_plan="$(mktemp "${TMPDIR:-/tmp}/gtm_plan.XXXXXX")"
        if jq --arg idx "$zero_idx" --arg hash "$new_hash" \
            '.commits[($idx | tonumber)] += {status: "applied", commit_hash: $hash, applied_at: (now | todateiso8601)}' \
            "$plan_file" > "$tmp_plan"; then
            mv "$tmp_plan" "$plan_file"
        else
            rm -f "$tmp_plan"
        fi

        created_count=$((created_count + 1))
        log_ok "Commit #$idx créé ($new_hash)"

    done < <(jq -c '.commits[]' "$plan_file")

    # Archiver une copie dans .gtm/history dès que tous les commits sont appliqués
    local remaining_pending
    remaining_pending=$(jq '[.commits[] | select(.status != "applied")] | length' "$plan_file" 2>/dev/null || echo "0")

    if (( remaining_pending == 0 && created_count > 0 )); then
        local base_dir=".gtm"
        if [[ "$plan_file" == *".gtm"* ]]; then
            base_dir="$(dirname "$plan_file")"
        fi
        config_ensure_gtm_dir "$base_dir"
        local history_dir="$base_dir/history"
        mkdir -p "$history_dir"
        local timestamp
        timestamp="$(date +%Y%m%d_%H%M%S 2>/dev/null || gdate +%Y%m%d_%H%M%S)"
        local archive_file="$history_dir/commit-plan-${timestamp}.json"
        cp "$plan_file" "$archive_file"
        log_ok "Plan entièrement appliqué et archivé dans $archive_file"
    fi
}

# Alias pour compatibilité
dry_run() {
    runner_dry_run "$@"
}

run_plan() {
    runner_run "$@"
}
