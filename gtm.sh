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
config_set_plan_file "${2:-commit-plan.json}"

show_usage() {
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
}

main() {
    if [[ $# -lt 1 || $# -gt 2 ]]; then
        show_usage
        exit 1
    fi

    # Détection cross-platform de la commande de date
    date_init_engine

    case "$1" in
        update|--update|-update|--u|-u)
            updater_run
            ;;
        validate)
            validator_validate_plan "$PLAN_FILE"
            ;;
        dry-run)
            runner_dry_run "$PLAN_FILE"
            ;;
        run)
            runner_run "$PLAN_FILE"
            ;;
        *)
            log_error "Commande inconnue: $1"
            log_info "Commandes disponibles: validate, dry-run, run, update (--u, -update)"
            exit 1
            ;;
    esac
}

main "$@"