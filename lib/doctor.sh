#!/usr/bin/env bash
# lib/doctor.sh - Diagnostic de l'environnement et des dépendances GTM
# Compatible: bash 3.2+ (macOS, Linux, Git Bash)

doctor_check_all() {
    echo "=== Diagnostic Git Tasks-Time Machine (gtm doctor) ==="
    echo
    local issues=0

    # 1. Shell & Git
    printf "• Shell bash    : "
    if [[ -n "${BASH_VERSION:-}" ]]; then
        echo "OK ($BASH_VERSION)"
    else
        echo "WARN (version non détectée)"
    fi

    printf "• Git CLI       : "
    if command -v git >/dev/null 2>&1; then
        local git_v
        git_v=$(git --version | head -n1)
        echo "OK ($git_v)"
    else
        echo "MANQUANT"
        issues=$((issues + 1))
    fi

    # 2. jq
    printf "• jq parser     : "
    if command -v jq >/dev/null 2>&1; then
        local jq_v
        jq_v=$(jq --version 2>/dev/null || echo "installé")
        echo "OK ($jq_v)"
    else
        echo "MANQUANT (requis pour le parsing JSON)"
        issues=$((issues + 1))
    fi

    # 3. Date engine
    printf "• Moteur date   : "
    date_init_engine
    if [[ "$DATE_STRATEGY" == "gnu" ]]; then
        echo "OK (GNU date via $DATE_CMD)"
    else
        echo "OK (BSD date native macOS - note: 'brew install coreutils' recommandé pour gdate)"
    fi

    # 4. Python 3 (pour gtm plan)
    printf "• Python 3      : "
    if command -v python3 >/dev/null 2>&1; then
        local py_v
        py_v=$(python3 --version 2>&1 | head -n1)
        echo "OK ($py_v)"
    else
        echo "MANQUANT (requis pour 'gtm plan')"
        issues=$((issues + 1))
    fi

    # 5. Ollama daemon & modèles
    local ollama_url="${OLLAMA_HOST:-http://localhost:11434}"
    printf "• Démon Ollama  : "
    local ollama_online=0
    if curl -s --max-time 2 "$ollama_url/api/tags" >/dev/null 2>&1; then
        echo "OK (en ligne sur $ollama_url)"
        ollama_online=1
    else
        echo "HORS LIGNE ou NON ACCESSIBLE sur $ollama_url"
        echo "  -> Note : requis pour 'gtm plan'. Lancez Ollama ou vérifiez OLLAMA_HOST dans config.env."
    fi

    if (( ollama_online == 1 )); then
        printf "• Modèle SLM    : "
        local configured_model="${DEFAULT_MODEL:-qwen2.5-coder:1.5b}"
        local tags_json
        tags_json=$(curl -s --max-time 2 "$ollama_url/api/tags" 2>/dev/null || echo "{}")
        if echo "$tags_json" | grep -q "\"name\":\"${configured_model}"; then
            echo "OK ($configured_model détecté [actif dans config.env])"
        else
            local found_models
            found_models=$(echo "$tags_json" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | tr '\n' ', ' | sed 's/, $//')
            echo "NON DÉTECTÉ ('$configured_model' configuré mais absent d'Ollama)"
            if [[ -n "$found_models" ]]; then
                echo "  -> Modèles présents sur cette machine : $found_models"
                echo "  -> Pour basculer : gtm model <nom> (ou 'gtm model' pour le menu)"
                echo "  -> Ou pour installer : ollama pull $configured_model"
            else
                echo "  -> Aucun modèle téléchargé. Exécutez : ollama pull $configured_model"
            fi
        fi
    fi

    echo
    # 6. Contexte courant
    printf "• Dépôt Git local : "
    if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        local root_dir
        root_dir=$(git rev-parse --show-toplevel 2>/dev/null)
        echo "OK ($root_dir)"
    else
        echo "Non (le dossier courant n'est pas un dépôt Git)"
    fi

    printf "• Fichier plan    : "
    if [[ -f "commit-plan.json" ]]; then
        local nb_commits
        nb_commits=$(jq '.commits | length' commit-plan.json 2>/dev/null || echo "0")
        echo "Présent (commit-plan.json avec $nb_commits commit(s))"
    else
        echo "Absent (non bloquant - générable via 'gtm plan')"
    fi

    echo
    if (( issues == 0 )); then
        log_ok "Environnement opérationnel pour GTM !"
    else
        log_warn "$issues dépendance(s) essentielle(s) manquante(s). Consultez le README.md pour l'installation."
    fi
}
