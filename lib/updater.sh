#!/usr/bin/env bash
# lib/updater.sh - Module de mise à jour automatique de Git Tasks-Time Machine
# Compatible: bash 3.2+

updater_run() {
    log_info "Vérification des mises à jour pour Git Tasks-Time Machine..."
    log_info "Dépôt distant : $REPO_URL"
    log_info "Emplacement local : $GTM_DIR"

    # 1. Vérification si le script fait partie d'un clone Git local
    if git -C "$GTM_DIR" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        log_info "Mise à jour via Git..."

        if GIT_TERMINAL_PROMPT=0 git -C "$GTM_DIR" pull --ff-only "$REPO_URL" "$REPO_BRANCH" 2>/dev/null || \
           GIT_TERMINAL_PROMPT=0 git -C "$GTM_DIR" pull --ff-only 2>/dev/null; then
            chmod +x "$GTM_FILE" 2>/dev/null || true
            chmod +x "$GTM_DIR"/lib/*.sh 2>/dev/null || true
            log_ok "Git Tasks-Time Machine a été mis à jour avec succès via Git !"
            return 0
        else
            log_warn "Impossible d'effectuer un git pull --ff-only direct. Tentative de téléchargement direct..."
        fi
    fi

    # 2. Fallback si ce n'est pas un dépôt git ou si git pull a échoué
    log_info "Téléchargement de la dernière version ($RAW_FILE_URL)..."
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
        log_error "Ni 'curl' ni 'wget' n'est installé pour télécharger la mise à jour."
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
        log_ok "Git Tasks-Time Machine a été mis à jour avec succès !"
    else
        rm -f "$tmp_file"
        log_error "Échec du téléchargement de la mise à jour depuis $RAW_FILE_URL"
        return 1
    fi
}

# Alias pour compatibilité
update_gtm() {
    updater_run "$@"
}
