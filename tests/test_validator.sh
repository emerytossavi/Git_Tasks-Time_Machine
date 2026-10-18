#!/usr/bin/env bash
# tests/test_validator.sh - Tests d'intégration pour gtm validate (lib/validator.sh)
# Compatible: bash 3.2+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/gtm_test_validator.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

cd "$SANDBOX"

# Initialiser un faux dépôt pour isoler l'exécution
git init -q
echo "hello" > file1.txt
echo "world" > file2.txt

PASSED=0
FAILED=0

assert_exit_code() {
    local test_name="$1"
    local expected_code="$2"
    shift 2
    local actual_code=0
    "$@" >/dev/null 2>&1 || actual_code=$?

    if (( actual_code == expected_code )); then
        printf "  \033[0;32m✔\033[0m %s (code attendu: %d)\n" "$test_name" "$expected_code"
        PASSED=$((PASSED + 1))
    else
        printf "  \033[0;31m✘\033[0m %s (attendu: %d, obtenu: %d)\n" "$test_name" "$expected_code" "$actual_code"
        FAILED=$((FAILED + 1))
    fi
}

echo "=== Exécution des tests pour 'gtm validate' ==="

# 1. Plan valide
cat <<EOF > valid_plan.json
{
  "commits": [
    {
      "date": "2026-10-18T09:00:00+01:00",
      "message": "feat(core): initial commit",
      "files": ["file1.txt"]
    },
    {
      "date": "2026-10-18T10:00:00+01:00",
      "message": "feat(core): second commit",
      "files": ["file2.txt"]
    }
  ]
}
EOF
assert_exit_code "Plan valide conforme" 0 "$PROJECT_ROOT/gtm.sh" validate valid_plan.json

# 2. Plan avec fichier inexistant
cat <<EOF > missing_file_plan.json
{
  "commits": [
    {
      "date": "2026-10-18T09:00:00+01:00",
      "message": "feat: missing file",
      "files": ["non_existent_file.txt"]
    }
  ]
}
EOF
assert_exit_code "Plan avec fichier inexistant rejeté" 1 "$PROJECT_ROOT/gtm.sh" validate missing_file_plan.json

# 3. Plan avec dates non chronologiques
cat <<EOF > unordered_dates_plan.json
{
  "commits": [
    {
      "date": "2026-10-18T11:00:00+01:00",
      "message": "feat: first commit in list with later date",
      "files": ["file1.txt"]
    },
    {
      "date": "2026-10-18T09:00:00+01:00",
      "message": "feat: second commit in list with earlier date",
      "files": ["file2.txt"]
    }
  ]
}
EOF
assert_exit_code "Plan avec dates non chronologiques rejeté" 1 "$PROJECT_ROOT/gtm.sh" validate unordered_dates_plan.json

# 4. Plan avec date invalide (non-ISO8601)
cat <<EOF > invalid_date_plan.json
{
  "commits": [
    {
      "date": "18/10/2026 09:00",
      "message": "feat: invalid date format",
      "files": ["file1.txt"]
    }
  ]
}
EOF
assert_exit_code "Plan avec format de date invalide rejeté" 1 "$PROJECT_ROOT/gtm.sh" validate invalid_date_plan.json

# 5. Plan avec message vide
cat <<EOF > empty_msg_plan.json
{
  "commits": [
    {
      "date": "2026-10-18T09:00:00+01:00",
      "message": "   ",
      "files": ["file1.txt"]
    }
  ]
}
EOF
assert_exit_code "Plan avec message vide rejeté" 1 "$PROJECT_ROOT/gtm.sh" validate empty_msg_plan.json

# 6. JSON malformé
echo "{ commits: [ malformed" > malformed_plan.json
assert_exit_code "JSON malformé rejeté" 1 "$PROJECT_ROOT/gtm.sh" validate malformed_plan.json

echo
if (( FAILED > 0 )); then
    printf "\033[0;31mÉchec : %d test(s) échoué(s) sur %d.\033[0m\n" "$FAILED" "$((PASSED + FAILED))"
    exit 1
else
    printf "\033[0;32mSuccès : %d test(s) validé(s).\033[0m\n" "$PASSED"
    exit 0
fi
