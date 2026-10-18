#!/usr/bin/env bash
# tests/test_model_config.sh - Tests d'intégration pour gtm model et lib/config.sh
# Compatible: bash 3.2+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/gtm_test_config.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

cd "$SANDBOX"

# Copier le code dans un environnement bac à sable
mkdir -p lib
cp "$PROJECT_ROOT/gtm.sh" ./
cp "$PROJECT_ROOT/lib/"*.sh ./lib/
chmod +x gtm.sh lib/*.sh

PASSED=0
FAILED=0

assert_equals() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"

    if [[ "$expected" == "$actual" ]]; then
        printf "  \033[0;32m✔\033[0m %s (valeur: '%s')\n" "$test_name" "$actual"
        PASSED=$((PASSED + 1))
    else
        printf "  \033[0;31m✘\033[0m %s (attendu: '%s', obtenu: '%s')\n" "$test_name" "$expected" "$actual"
        FAILED=$((FAILED + 1))
    fi
}

assert_exit_code() {
    local test_name="$1"
    local expected_code="$2"
    shift 2
    local actual_code=0
    "$@" >/dev/null 2>&1 || actual_code=$?

    if (( actual_code == expected_code )); then
        printf "  \033[0;32m✔\033[0m %s (code: %d)\n" "$test_name" "$expected_code"
        PASSED=$((PASSED + 1))
    else
        printf "  \033[0;31m✘\033[0m %s (attendu: %d, obtenu: %d)\n" "$test_name" "$expected_code" "$actual_code"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== Exécution des tests pour 'gtm model' et 'config.env' ==="

# 1. Modèle par défaut quand config.env n'existe pas
# Source lib/config.sh
source ./lib/config.sh
config_init "$PWD/gtm.sh"
assert_equals "Modèle de repli par défaut" "qwen2.5-coder:1.5b" "$DEFAULT_MODEL"

# 2. Définition d'un nouveau modèle (création de config.env)
./gtm.sh model custom-coder:14b >/dev/null 2>&1
assert_equals "config.env créé" "1" "$([[ -f config.env ]] && echo 1 || echo 0)"

val_saved=$(grep "^DEFAULT_MODEL=" config.env | cut -d'=' -f2 | tr -d '"')
assert_equals "Valeur persistée dans config.env" "custom-coder:14b" "$val_saved"

# 3. Modification d'un modèle existant dans config.env
./gtm.sh model llama3.2:3b >/dev/null 2>&1
val_updated=$(grep "^DEFAULT_MODEL=" config.env | cut -d'=' -f2 | tr -d '"')
assert_equals "Mise à jour idempotente dans config.env" "llama3.2:3b" "$val_updated"

# 4. gtm model --list doit renvoyer 0
assert_exit_code "gtm model --list termine avec 0" 0 ./gtm.sh model --list

# 5. gtm model sans argument avec nom vide échoue
assert_exit_code "gtm model avec argument vide" 1 ./gtm.sh model ""

# 6. Test OLLAMA_HOST configuration & persistance
config_set_ollama_host "192.168.1.80:11435/"
assert_equals "OLLAMA_HOST normalisé et exporté" "http://192.168.1.80:11435" "$OLLAMA_HOST"
val_host=$(grep "^OLLAMA_HOST=" config.env | cut -d'=' -f2 | tr -d '"')
assert_equals "OLLAMA_HOST persisté dans config.env" "http://192.168.1.80:11435" "$val_host"

# 7. Test gtm lang & DEFAULT_LANG configuration
assert_exit_code "gtm lang sans argument termine avec 0" 0 ./gtm.sh lang
assert_exit_code "gtm lang avec argument vide échoue" 1 ./gtm.sh lang ""
assert_exit_code "gtm lang --list termine avec 0" 0 ./gtm.sh lang --list
assert_exit_code "gtm lang --help termine avec 0" 0 ./gtm.sh lang --help
assert_exit_code "gtm lang avec code invalide échoue" 1 ./gtm.sh lang "invalid_long_code"
./gtm.sh lang fr >/dev/null 2>&1
val_lang=$(grep "^DEFAULT_LANG=" config.env | cut -d'=' -f2 | tr -d '"')
assert_equals "DEFAULT_LANG persisté dans config.env" "fr" "$val_lang"

# 8. Test gtm config lang (sous-commande config)
./gtm.sh config lang es >/dev/null 2>&1
val_lang_es=$(grep "^DEFAULT_LANG=" config.env | cut -d'=' -f2 | tr -d '"')
assert_equals "Sous-commande config lang persistée" "es" "$val_lang_es"

echo
if (( FAILED > 0 )); then
    printf "\033[0;31mÉchec : %d test(s) échoué(s) sur %d.\033[0m\n" "$FAILED" "$((PASSED + FAILED))"
    exit 1
else
    printf "\033[0;32mSuccès : %d test(s) validé(s).\033[0m\n" "$PASSED"
    exit 0
fi
