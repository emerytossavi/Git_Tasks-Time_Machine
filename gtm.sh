#!/usr/bin/env bash
# gtm.sh - Git Tasks Time Machine
# Point d'entrée principal (orchestrateur)
# Compatible: bash 3.2+ (macOS), bash 4/5 (Linux), Git Bash (Windows)
set -euo pipefail

# 1. Résolution de l'emplacement réel du script (support symlinks sous bash 3.2+)
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

# 2. Chargement des modules
MODULES=(
    "logger.sh"
    "config.sh"
    "date.sh"
    "fs.sh"
    "git.sh"
    "validator.sh"
    "runner.sh"
    "updater.sh"
    "doctor.sh"
    "model.sh"
)

for module in "${MODULES[@]}"; do
    module_path="$GTM_DIR/lib/$module"
    if [[ ! -f "$module_path" ]]; then
        printf '[ERROR] Module introuvable: %s\n' "$module_path" >&2
        exit 1
    fi
    # shellcheck disable=SC1090
    source "$module_path"
done

# 3. Initialisation de la configuration
config_init "$SOURCE"
config_set_plan_file "${2:-}"

show_usage() {
    cat <<USAGE
Usage: gtm <plan|validate|dry-run|run|test> [options] [chemin/vers/plan.json]
       gtm <doctor|--doctor>
       gtm <model|config> [nom|--list]
       gtm <update|--update|-update|--u|-u>

Commandes :
  plan     [options] [plan.json] Génère automatiquement un plan de commits via le SLM local configuré.
                                 Options : -a/--all, --dry-run, --date-strategy <last|first>, --start-date YYYY-MM-DD
  validate [plan.json]           Vérifie la conformité et la chronologie du plan JSON.
  dry-run  [plan.json]           Simule l'exécution sans toucher à Git.
  run      [plan.json]           Exécute les commits du plan dans le dépôt courant.
  test                           Lance l'intégralité de la suite de tests automatisés (unitaires et intégration).
  model    [nom|--list]          Affiche, sélectionne ou définit le modèle SLM par défaut dans config.env.
                                 (Sans argument: menu interactif de sélection parmi les modèles locaux).
  doctor                         Diagnostique l'environnement (Git, jq, date, Python, Ollama, modèle actif).
  update                         Met à jour Git Tasks-Time Machine depuis le dépôt public.
                                 (Alias acceptés : --update, -update, --u, -u)

Si le chemin du plan est omis, ".gtm/commit-plan.json" (ou "./commit-plan.json"
pour rétrocompatibilité) relatif au dossier courant est utilisé. "run" et "dry-run"
opèrent toujours sur le dépôt Git du dossier courant.
USAGE
}

main() {
    if [[ $# -lt 1 ]]; then
        show_usage
        exit 1
    fi

    case "$1" in
        help|--help|-h)
            show_usage
            exit 0
            ;;
        plan)
            shift
            if ! command -v python3 >/dev/null 2>&1; then
                log_error "Python 3 est requis pour la génération de plan avec le SLM local."
                exit 1
            fi
            config_ensure_gtm_dir ".gtm"
            python3 "$GTM_DIR/lib/planner.py" "$@"
            ;;
        doctor|--doctor)
            doctor_check_all
            ;;
        model|models)
            shift
            model_cmd "$@"
            ;;
        config)
            shift
            if [[ "${1:-}" == "model" ]]; then
                shift
            fi
            model_cmd "$@"
            ;;
        update|--update|-update|--u|-u)
            updater_run
            ;;
        validate)
            if [[ $# -gt 2 ]]; then show_usage; exit 1; fi
            date_init_engine
            validator_validate_plan "$PLAN_FILE"
            ;;
        dry-run)
            if [[ $# -gt 2 ]]; then show_usage; exit 1; fi
            date_init_engine
            runner_dry_run "$PLAN_FILE"
            ;;
        run)
            if [[ $# -gt 2 ]]; then show_usage; exit 1; fi
            date_init_engine
            runner_run "$PLAN_FILE"
            ;;
        test|tests)
            shift
            "$GTM_DIR/tests/run_tests.sh" "$@"
            ;;
        *)
            log_error "Commande inconnue: $1"
            log_info "Commandes disponibles: plan, validate, dry-run, run, test, doctor, model, update (--u, -update)"
            exit 1
            ;;
    esac
}

main "$@"