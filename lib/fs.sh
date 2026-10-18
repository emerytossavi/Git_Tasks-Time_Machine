#!/usr/bin/env bash
# lib/fs.sh - Utilitaires système de fichiers et compatibilité bash 3.2
# Compatible: bash 3.2+

# Lecture de lignes dans un tableau (alternative à mapfile/readarray sous bash 3.2)
# Usage: fs_readarray nom_du_tableau "$chaine_multiligne"
fs_readarray() {
    local _arr_name="$1"
    local _input="$2"
    local IFS=$'\n'
    local _line
    local _i=0

    # Réinitialisation du tableau cible
    eval "${_arr_name}=()"

    while IFS= read -r _line; do
        eval "${_arr_name}+=(\"\$_line\")"
        _i=$((_i + 1))
    done <<EOF
$_input
EOF
}

# Développer un pattern glob dans le tableau 'matches'.
# Compatible bash 3.2 (sans globstar).
fs_expand_pattern() {
    local pattern="$1"
    local _old_nullglob
    local IFS=$'\n'
    _old_nullglob=$(shopt -p nullglob 2>/dev/null || true)

    shopt -s nullglob
    # SC2206: découpage de mots intentionnel pour l'expansion de globs
    # shellcheck disable=SC2206
    matches=($pattern)

    eval "$_old_nullglob" 2>/dev/null || true

    # Si aucun fichier n'a été trouvé sur le disque, vérifier si le pattern correspond à des fichiers suivis dans Git (notamment supprimés)
    if (( ${#matches[@]} == 0 )); then
        if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
            local git_files
            git_files=$(git ls-files --deleted -- "$pattern" 2>/dev/null || true)
            if [[ -z "$git_files" ]]; then
                git_files=$(git ls-tree -r --name-only HEAD -- "$pattern" 2>/dev/null || true)
            fi
            if [[ -n "$git_files" ]]; then
                fs_readarray matches "$git_files"
            elif [[ "$pattern" != *"*"* && "$pattern" != *"?"* ]]; then
                if git ls-files -- "$pattern" 2>/dev/null | grep -qx "$pattern" || \
                   git ls-tree -r --name-only HEAD -- "$pattern" 2>/dev/null | grep -qx "$pattern"; then
                    matches=("$pattern")
                fi
            fi
        fi
    fi
}

# Alias pour compatibilité
_readarray() {
    fs_readarray "$@"
}

_expand_pattern() {
    fs_expand_pattern "$@"
}
