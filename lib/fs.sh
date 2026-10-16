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
}

# Alias pour compatibilité
_readarray() {
    fs_readarray "$@"
}

_expand_pattern() {
    fs_expand_pattern "$@"
}
