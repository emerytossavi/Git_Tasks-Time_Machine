#!/usr/bin/env bash
# lib/model.sh - Gestion et sélection du modèle SLM local pour GTM
# Compatible: bash 3.2+ (macOS, Linux, Git Bash)

model_get_active() {
    echo "${DEFAULT_MODEL:-qwen2.5-coder:1.5b}"
}

model_fetch_ollama_models() {
    local tags_json
    tags_json=$(curl -s --max-time 3 http://localhost:11434/api/tags 2>/dev/null || echo "")
    if [[ -z "$tags_json" ]] || [[ "$tags_json" == "{}" ]]; then
        return 1
    fi

    if command -v jq >/dev/null 2>&1; then
        echo "$tags_json" | jq -r '.models[]? | select(.name | contains("embed") | not) | "\(.name)\t\(.details.parameter_size // "")"' 2>/dev/null
    else
        # Fallback sans jq
        echo "$tags_json" | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | grep -v "embed"
    fi
}

model_list() {
    local active_model
    active_model=$(model_get_active)

    echo "=== Modèle SLM configuré dans config.env ==="
    printf "• Modèle actif : \033[1;32m%s\033[0m\n" "$active_model"
    echo

    if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        log_warn "Le démon Ollama n'est pas accessible sur http://localhost:11434."
        echo "  -> Impossible d'interroger la liste des modèles installés."
        return 0
    fi

    echo "Modèles de génération détectés dans Ollama sur cette machine :"
    local raw_list
    raw_list=$(model_fetch_ollama_models)

    if [[ -z "$raw_list" ]]; then
        echo "  (Aucun modèle textuel/code détecté)"
        echo "  -> Pour installer le modèle sobre par défaut : ollama pull qwen2.5-coder:1.5b"
        return 0
    fi

    local num=1
    while IFS=$'\t' read -r m_name m_size; do
        [[ -z "$m_name" ]] && continue
        local extra=""
        [[ -n "$m_size" ]] && extra=" ($m_size)"

        local tag=""
        if [[ "$m_name" == "$active_model" ]]; then
            tag=" \033[1;32m[actif]\033[0m"
        fi
        if [[ "$m_name" == "qwen2.5-coder:1.5b" ]]; then
            tag="$tag \033[0;33m(Recommandé par défaut)\033[0m"
        fi

        printf "  %2d) %-30s%b\n" "$num" "$m_name$extra" "$tag"
        num=$((num + 1))
    done <<< "$raw_list"
}

model_set() {
    local target_model="$1"
    if [[ -z "$target_model" ]]; then
        log_error "Veuillez spécifier le nom d'un modèle (ex: gtm model qwen2.5-coder:7b)."
        return 1
    fi

    # Vérification dans Ollama si accessible
    local is_installed=0
    if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        local tags_json
        tags_json=$(curl -s --max-time 2 http://localhost:11434/api/tags 2>/dev/null || echo "")
        if echo "$tags_json" | grep -q "\"name\":\"${target_model}"; then
            is_installed=1
        fi
    fi

    config_set_default_model "$target_model"
    log_ok "Modèle par défaut configuré : '$target_model' (sauvegardé dans config.env)"

    if (( is_installed == 0 )); then
        log_warn "Le modèle '$target_model' n'a pas été détecté dans Ollama."
        echo "  -> Si vous ne l'avez pas encore récupéré, exécutez : ollama pull $target_model"
    fi
}

model_interactive() {
    local active_model
    active_model=$(model_get_active)

    printf "Modèle actuel dans config.env : \033[1;32m%s\033[0m\n" "$active_model"
    echo

    if ! curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
        log_warn "Le démon Ollama n'est pas accessible sur http://localhost:11434."
        echo "Vous pouvez néanmoins saisir manuellement le nom d'un modèle :"
        printf "Nom du modèle (ou 'q' pour annuler) : "
        read -r manual_choice
        if [[ -n "$manual_choice" ]] && [[ "$manual_choice" != "q" ]] && [[ "$manual_choice" != "Q" ]]; then
            model_set "$manual_choice"
        fi
        return 0
    fi

    local raw_list
    raw_list=$(model_fetch_ollama_models)

    local model_names=()
    local model_labels=()

    while IFS=$'\t' read -r m_name m_size; do
        [[ -z "$m_name" ]] && continue
        model_names+=("$m_name")
        local lbl="$m_name"
        [[ -n "$m_size" ]] && lbl="$lbl ($m_size)"
        if [[ "$m_name" == "$active_model" ]]; then
            lbl="$lbl [actif]"
        fi
        if [[ "$m_name" == "qwen2.5-coder:1.5b" ]]; then
            lbl="$lbl (Recommandé)"
        fi
        model_labels+=("$lbl")
    done <<< "$raw_list"

    local count=${#model_names[@]}

    if (( count == 0 )); then
        log_warn "Aucun modèle de génération compatible trouvé dans Ollama."
        echo "Modèle recommandé sobre : qwen2.5-coder:1.5b"
        echo
        printf "Nom du modèle à configurer (ou 'q' pour quitter) : "
        read -r manual_choice
        if [[ -n "$manual_choice" ]] && [[ "$manual_choice" != "q" ]] && [[ "$manual_choice" != "Q" ]]; then
            model_set "$manual_choice"
        fi
        return 0
    fi

    echo "Modèles disponibles dans Ollama sur votre machine :"
    local i=0
    while (( i < count )); do
        local display_num=$((i + 1))
        local line_lbl="${model_labels[$i]}"
        if [[ "$line_lbl" == *"[actif]"* ]]; then
            printf "  \033[1;32m%2d) %s\033[0m\n" "$display_num" "$line_lbl"
        else
            printf "  %2d) %s\n" "$display_num" "$line_lbl"
        fi
        i=$((i + 1))
    done

    echo
    printf "Entrez le numéro du modèle [1-%d], un nom personnalisé, ou 'q' pour annuler : " "$count"
    read -r user_choice

    if [[ -z "$user_choice" ]] || [[ "$user_choice" == "q" ]] || [[ "$user_choice" == "Q" ]]; then
        echo "Aucune modification enregistrée."
        return 0
    fi

    # Vérifier si c'est un numéro valide
    if [[ "$user_choice" =~ ^[0-9]+$ ]] && (( user_choice >= 1 && user_choice <= count )); then
        local selected_index=$((user_choice - 1))
        local selected_model="${model_names[$selected_index]}"
        model_set "$selected_model"
    else
        # Considéré comme un nom de modèle saisi directement
        model_set "$user_choice"
    fi
}

model_cmd() {
    case "${1:-}" in
        --list|-l|list)
            model_list
            ;;
        --help|-h|help)
            echo "Usage: gtm model [nom_du_modele|--list]"
            echo
            echo "Options :"
            echo "  (sans argument)  Ouvre le menu interactif pour sélectionner un modèle local"
            echo "  <nom>            Configure directement le modèle par défaut dans config.env"
            echo "  --list, -l       Liste les modèles installés et indique le modèle actif"
            ;;
        "")
            if [[ -t 0 ]]; then
                model_interactive
            else
                model_list
            fi
            ;;
        -i|--interactive)
            model_interactive
            ;;
        *)
            model_set "$1"
            ;;
    esac
}
