#!/usr/bin/env bash
# tests/run_tests.sh - Lanceur global de la suite de tests GTM (TDD)
# Compatible: bash 3.2+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================================"
echo "    Git Tasks-Time Machine (GTM) - Suite de tests TDD   "
echo "========================================================"
echo

SUITES_PASSED=0
SUITES_FAILED=0

run_suite() {
    local name="$1"
    shift
    echo "--------------------------------------------------------"
    printf "▶ Lancement de la suite : \033[1;34m%s\033[0m\n" "$name"
    echo "--------------------------------------------------------"

    if "$@"; then
        printf "\n\033[0;32m[PASS]\033[0m Suite '%s' validée avec succès.\n\n" "$name"
        SUITES_PASSED=$((SUITES_PASSED + 1))
    else
        printf "\n\033[0;31m[FAIL]\033[0m Suite '%s' a échoué.\n\n" "$name"
        SUITES_FAILED=$((SUITES_FAILED + 1))
    fi
}

# 1. Tests unitaires Python (lib/planner.py)
run_suite "Tests unitaires Planner (Python unittest)" python3 "$PROJECT_ROOT/tests/test_planner.py"

# 2. Tests d'intégration du Validator (gtm validate)
run_suite "Tests d'intégration Validator (Shell)" "$PROJECT_ROOT/tests/test_validator.sh"

# 3. Tests d'intégration Config & Model (gtm model)
run_suite "Tests d'intégration Model & Config (Shell)" "$PROJECT_ROOT/tests/test_model_config.sh"

# 4. Tests d'intégration Runner & Dry-run (gtm run & dry-run)
run_suite "Tests d'intégration Runner & Dry-run (Shell)" "$PROJECT_ROOT/tests/test_runner_and_dryrun.sh"

echo "========================================================"
echo "                RÉSUMÉ FINAL DES TESTS                  "
echo "========================================================"
printf "Suites validées : \033[0;32m%d\033[0m\n" "$SUITES_PASSED"
printf "Suites échouées : \033[0;31m%d\033[0m\n" "$SUITES_FAILED"
echo "========================================================"

if (( SUITES_FAILED > 0 )); then
    printf "\033[0;31m[ÉCHEC]\033[0m Des tests ont échoué. Corrigez les anomalies avant de commiter.\n"
    exit 1
else
    printf "\033[0;32m[SUCCÈS TOTAL]\033[0m Toutes les suites de tests sont au vert !\n"
    exit 0
fi
