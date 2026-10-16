#!/usr/bin/env bash
# lib/date.sh - Gestion cross-platform des dates ISO 8601 et conversions Epoch
# Compatible: bash 3.2+ (macOS BSD date, Linux GNU date, Git Bash)

DATE_CMD="date"
DATE_STRATEGY="gnu"

date_init_engine() {
    # 1. gdate (GNU coreutils installé via Homebrew sur macOS)
    if command -v gdate >/dev/null 2>&1; then
        DATE_CMD="gdate"
        DATE_STRATEGY="gnu"
        return
    fi

    # 2. Date native avec option GNU -d (Linux, Git Bash sous Windows)
    if date -d "2000-01-01T00:00:00+00:00" '+%s' >/dev/null 2>&1; then
        DATE_CMD="date"
        DATE_STRATEGY="gnu"
        return
    fi

    # 3. BSD date (macOS standard sans gdate)
    DATE_CMD="date"
    DATE_STRATEGY="bsd"
}

# Convertir une chaîne ISO 8601 en timestamp Unix.
# Affiche l'entier epoch et retourne 0, ou retourne 1 en cas d'erreur.
date_iso_to_epoch() {
    local iso="$1"

    if [[ "$DATE_STRATEGY" == "gnu" ]]; then
        "$DATE_CMD" -d "$iso" '+%s' 2>/dev/null
        return $?
    fi

    # BSD: strptime %z accepte "+0100" mais pas "+01:00" — suppression du deux-points.
    local normalized
    normalized=$(printf '%s' "$iso" | sed 's/\([+-][0-9][0-9]\):\([0-9][0-9]\)$/\1\2/')

    "$DATE_CMD" -j -f '%Y-%m-%dT%H:%M:%S%z' "$normalized" '+%s' 2>/dev/null
    return $?
}

# Vérifier si la chaîne est une date ISO 8601 valide.
date_is_valid() {
    date_iso_to_epoch "$1" >/dev/null 2>&1
}

# Alias pour compatibilité
iso_to_epoch() {
    date_iso_to_epoch "$@"
}

is_valid_date() {
    date_is_valid "$@"
}
