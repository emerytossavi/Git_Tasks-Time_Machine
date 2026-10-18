#!/usr/bin/env bash
# tests/test_runner_and_dryrun.sh - Tests d'intégration pour gtm dry-run et gtm run
# Compatible: bash 3.2+

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SANDBOX="$(mktemp -d "${TMPDIR:-/tmp}/gtm_test_runner.XXXXXX")"
trap 'rm -rf "$SANDBOX"' EXIT

cd "$SANDBOX"

# Initialiser un dépôt git isolé
git init -q
git config user.name "GTM Test User"
git config user.email "gtm-test@example.com"
git config commit.gpgsign false

echo "content file 1" > file1.txt
echo "content file 2" > file2.txt

PASSED=0
FAILED=0

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

echo "=== Exécution des tests pour 'gtm dry-run' et 'gtm run' ==="

cat <<EOF > test_plan.json
{
  "commits": [
    {
      "date": "2026-10-18T09:15:00+01:00",
      "message": "feat(core): add first module file\n\nDetailed technical explanation of module 1.",
      "files": ["file1.txt"]
    },
    {
      "date": "2026-10-18T10:30:00+01:00",
      "message": "feat(core): add second module file\n\nDetailed technical explanation of module 2.",
      "files": ["file2.txt"]
    }
  ]
}
EOF

# 1. Simulation via gtm dry-run
assert_exit_code "gtm dry-run termine avec code 0" 0 "$PROJECT_ROOT/gtm.sh" dry-run test_plan.json

# Vérifier qu'aucun commit n'a encore été créé
commits_before=$(git rev-list --count HEAD 2>/dev/null || echo "0")
if [[ "$commits_before" == "0" ]]; then
    printf "  \033[0;32m✔\033[0m gtm dry-run ne modifie pas l'historique git\n"
    PASSED=$((PASSED + 1))
else
    printf "  \033[0;31m✘\033[0m gtm dry-run a modifié l'historique git\n"
    FAILED=$((FAILED + 1))
fi

# 2. Exécution réelle via gtm run
assert_exit_code "gtm run applique le plan avec code 0" 0 "$PROJECT_ROOT/gtm.sh" run test_plan.json

# Vérifier que 2 commits ont été créés
commits_after=$(git rev-list --count HEAD)
if [[ "$commits_after" == "2" ]]; then
    printf "  \033[0;32m✔\033[0m 2 commits ont été créés\n"
    PASSED=$((PASSED + 1))
else
    printf "  \033[0;31m✘\033[0m Mauvais nombre de commits : %s (attendu 2)\n" "$commits_after"
    FAILED=$((FAILED + 1))
fi

# Vérifier que le statut de l'espace de travail est propre
git_status_output=$(git status --porcelain)
# On exclut test_plan.json s'il n'est pas tracké
untracked=$(echo "$git_status_output" | grep -v "test_plan.json" || true)
if [[ -z "$untracked" ]]; then
    printf "  \033[0;32m✔\033[0m Espace de travail propre après gtm run\n"
    PASSED=$((PASSED + 1))
else
    printf "  \033[0;31m✘\033[0m Espace de travail non propre : %s\n" "$untracked"
    FAILED=$((FAILED + 1))
fi

# Vérifier que la date du commit correspond à celle du plan
commit_1_date=$(git log -1 --skip=1 --format="%aI")
if [[ "$commit_1_date" == "2026-10-18T09:15:00+01:00" ]]; then
    printf "  \033[0;32m✔\033[0m Date historique préservée sur le commit #1 (%s)\n" "$commit_1_date"
    PASSED=$((PASSED + 1))
else
    printf "  \033[0;31m✘\033[0m Date historique incorrecte : %s\n" "$commit_1_date"
    FAILED=$((FAILED + 1))
fi

# 3. Test d'exécution par défaut avec .gtm/commit-plan.json et zéro résidu
rm -f test_plan.json
mkdir -p .gtm
echo "*" > .gtm/.gitignore
echo "content file 3" > file3.txt
cat <<EOF > .gtm/commit-plan.json
{
  "commits": [
    {
      "date": "2026-10-18T11:00:00+01:00",
      "message": "feat(module): add isolated file3\n\nExplanation of file 3.",
      "files": ["file3.txt"]
    }
  ]
}
EOF

assert_exit_code "gtm dry-run sans argument résout .gtm/commit-plan.json" 0 "$PROJECT_ROOT/gtm.sh" dry-run
assert_exit_code "gtm run sans argument applique .gtm/commit-plan.json" 0 "$PROJECT_ROOT/gtm.sh" run

# Vérifier que git status est 100% propre (zéro résidu de .gtm dans git status)
gtm_residue=$(git status --porcelain)
if [[ -z "$gtm_residue" ]]; then
    printf "  \033[0;32m✔\033[0m Zéro résidu git : le dossier .gtm est 100%% ignoré par git status\n"
    PASSED=$((PASSED + 1))
else
    printf "  \033[0;31m✘\033[0m Résidu détecté dans git status : %s\n" "$gtm_residue"
    FAILED=$((FAILED + 1))
fi

echo
if (( FAILED > 0 )); then
    printf "\033[0;31mÉchec : %d test(s) échoué(s) sur %d.\033[0m\n" "$FAILED" "$((PASSED + FAILED))"
    exit 1
else
    printf "\033[0;32mSuccès : %d test(s) validé(s).\033[0m\n" "$PASSED"
    exit 0
fi
