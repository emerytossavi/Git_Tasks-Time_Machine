#!/usr/bin/env bash
set -euo pipefail

PLAN_FILE="${2:-commit-plan.json}"

# Variables globales chargées depuis le plan
PLAN_DATES=()
PLAN_MESSAGES=()
PLAN_FILES_JSON=()

print_report() {
  local level="$1"
  local message="$2"
  printf '[%s] %s\n' "$level" "$message"
}

load_plan_old() {
  if [[ ! -f "$PLAN_FILE" ]]; then
    print_report "ERROR" "Fichier plan introuvable: $PLAN_FILE"
    exit 1
  fi

  if ! jq -e '.' "$PLAN_FILE" >/dev/null 2>&1; then
    print_report "ERROR" "JSON invalide dans $PLAN_FILE"
    exit 1
  fi

  if ! jq -e '.commits and (.commits | type == "array")' "$PLAN_FILE" >/dev/null 2>&1; then
    print_report "ERROR" "Le plan doit contenir une clé 'commits' de type tableau"
    exit 1
  fi

  mapfile -t PLAN_DATES < <(jq -r '.commits[].date' "$PLAN_FILE")
  mapfile -t PLAN_MESSAGES < <(jq -r '.commits[].message' "$PLAN_FILE")
  mapfile -t PLAN_FILES_JSON < <(jq -c '.commits[].files' "$PLAN_FILE")
}

load_plan() {
  if [[ ! -f "$PLAN_FILE" ]]; then
    print_report "ERROR" "Fichier plan introuvable: $PLAN_FILE"
    exit 1
  fi

  if ! jq -e '.' "$PLAN_FILE" >/dev/null 2>&1; then
    print_report "ERROR" "JSON invalide dans $PLAN_FILE"
    exit 1
  fi

  if ! jq -e '.commits | type == "array"' "$PLAN_FILE" >/dev/null 2>&1; then
    print_report "ERROR" "Le plan doit contenir une clé 'commits' de type tableau"
    exit 1
  fi

  local count
  count=$(jq '.commits | length' "$PLAN_FILE")

  if (( count == 0 )); then
    print_report "ERROR" "Le plan ne contient aucun commit"
    exit 1
  fi
}


validate_plan_old() {
  load_plan

  local count="${#PLAN_DATES[@]}"
  if [[ "$count" -eq 0 ]]; then
    print_report "ERROR" "Le plan ne contient aucun commit"
    exit 1
  fi

  local prev_epoch=""
  local i
  for ((i=0; i<count; i++)); do
    local idx=$((i + 1))
    local date="${PLAN_DATES[$i]}"
    local message="${PLAN_MESSAGES[$i]}"
    local files_json="${PLAN_FILES_JSON[$i]}"

    # Validation ISO8601 via GNU date
    if ! date -d "$date" '+%s' >/dev/null 2>&1; then
      print_report "ERROR" "Commit #$idx: date invalide (ISO8601 attendu): $date"
      exit 1
    fi
    local current_epoch
    current_epoch="$(date -d "$date" '+%s')"

    if [[ -n "$prev_epoch" ]] && (( current_epoch < prev_epoch )); then
      print_report "ERROR" "Commit #$idx: ordre chronologique invalide"
      exit 1
    fi
    prev_epoch="$current_epoch"

    # Message non vide
    if [[ -z "${message//[[:space:]]/}" ]]; then
      print_report "ERROR" "Commit #$idx: message vide"
      exit 1
    fi

    # files non vide
    if ! jq -e 'type == "array" and length > 0' <<<"$files_json" >/dev/null 2>&1; then
      print_report "ERROR" "Commit #$idx: 'files' doit être un tableau non vide"
      exit 1
    fi

    # Existence des fichiers + expansion glob
    mapfile -t patterns < <(jq -r '.[]' <<<"$files_json")
    local p
    for p in "${patterns[@]}"; do
      shopt -s nullglob globstar
      local matches=()
      # shellcheck disable=SC2206
      matches=($p)
      shopt -u nullglob globstar

      if [[ "${#matches[@]}" -eq 0 ]]; then
        print_report "ERROR" "Commit #$idx: pattern sans correspondance: $p"
        exit 1
      fi

      local m
      for m in "${matches[@]}"; do
        if [[ ! -e "$m" ]]; then
          print_report "ERROR" "Commit #$idx: fichier inexistant: $m"
          exit 1
        fi
      done
    done
  done

  print_report "OK" "Validation réussie ($count commit(s))"
}

validate_plan() {
    load_plan

    local prev_epoch=""
    local idx=0

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        if ! date -d "$COMMIT_DATE" '+%s' >/dev/null 2>&1; then
            print_report "ERROR" "Commit #$idx: date invalide (ISO8601 attendu): $COMMIT_DATE"
            exit 1
        fi

        current_epoch=$(date -d "$COMMIT_DATE" '+%s')

        if [[ -n "$prev_epoch" ]] && (( current_epoch < prev_epoch )); then
            print_report "ERROR" "Commit #$idx: ordre chronologique invalide"
            exit 1
        fi

        prev_epoch="$current_epoch"

        if [[ -z "${COMMIT_MESSAGE//[[:space:]]/}" ]]; then
            print_report "ERROR" "Commit #$idx: message vide"
            exit 1
        fi

        if ! jq -e 'type=="array" and length>0' <<<"$COMMIT_FILES_JSON" >/dev/null; then
            print_report "ERROR" "Commit #$idx: 'files' doit être un tableau non vide"
            exit 1
        fi

        mapfile -t patterns < <(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        for p in "${patterns[@]}"; do
            shopt -s nullglob globstar
            matches=($p)
            shopt -u nullglob globstar

            if (( ${#matches[@]} == 0 )); then
                print_report "ERROR" "Commit #$idx: pattern sans correspondance: $p"
                exit 1
            fi

            for m in "${matches[@]}"; do
                [[ -e "$m" ]] || {
                    print_report "ERROR" "Commit #$idx: fichier inexistant: $m"
                    exit 1
                }
            done
        done

    done < <(jq -c '.commits[]' "$PLAN_FILE")

    print_report "OK" "Validation réussie ($idx commit(s))"
}

dry_run_old() {
  validate_plan >/dev/null

  local count="${#PLAN_DATES[@]}"
  local i
  for ((i=0; i<count; i++)); do
    local idx=$((i + 1))
    local date="${PLAN_DATES[$i]}"
    local message="${PLAN_MESSAGES[$i]}"
    local files_json="${PLAN_FILES_JSON[$i]}"

    mapfile -t patterns < <(jq -r '.[]' <<<"$files_json")
    local expanded=()
    local p
    for p in "${patterns[@]}"; do
      shopt -s nullglob globstar
      local matches=()
      # shellcheck disable=SC2206
      matches=($p)
      shopt -u nullglob globstar
      expanded+=("${matches[@]}")
    done

    print_report "DRY-RUN" "Commit #$idx"
    echo "Date: $date"
    echo "Message:"
    printf '%s\n' "$message"
    echo "Fichiers:"
    printf '  - %s\n' "${expanded[@]}"
    echo
  done
}

dry_run() {
    validate_plan >/dev/null

    local idx=0

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        mapfile -t patterns < <(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        expanded=()

        for p in "${patterns[@]}"; do
            shopt -s nullglob globstar
            matches=($p)
            shopt -u nullglob globstar
            expanded+=("${matches[@]}")
        done

        print_report "DRY-RUN" "Commit #$idx"

        echo "Date: $COMMIT_DATE"

        echo "Message:"
        printf '%s\n' "$COMMIT_MESSAGE"

        echo "Fichiers:"
        printf '  - %s\n' "${expanded[@]}"
        echo

    done < <(jq -c '.commits[]' "$PLAN_FILE")
}

process_commit_old() {
    local mode="$1"
    local index="$2"
    local commit="$3"

    local date
    local message
    local files_json

    date=$(jq -r '.date' <<<"$commit")
    message=$(jq -r '.message' <<<"$commit")
    files_json=$(jq -c '.files' <<<"$commit")

    case "$mode" in
        validate)
            validate_plan "$index" "$date" "$message" "$files_json"
            ;;

        dry-run)
            dry_run "$index" "$date" "$message" "$files_json"
            ;;

        run)
            run_plan "$index" "$date" "$message" "$files_json"
            ;;

        *)
            print_report "ERROR" "Mode inconnu : $mode"
            return 1
            ;;
    esac
}

process_commit() {
    local commit="$1"

    COMMIT_DATE=$(jq -r '.date' <<<"$commit" | tr -d '\r')
    COMMIT_MESSAGE=$(jq -r '.message' <<<"$commit" | tr -d '\r')
    COMMIT_FILES_JSON=$(jq -c '.files' <<<"$commit" | tr -d '\r')
}

run_plan_old() {
  validate_plan >/dev/null

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    print_report "ERROR" "Le dossier courant n'est pas un dépôt Git"
    exit 1
  fi

  local count="${#PLAN_DATES[@]}"
  local i
  for ((i=0; i<count; i++)); do
    local idx=$((i + 1))
    local date="${PLAN_DATES[$i]}"
    local message="${PLAN_MESSAGES[$i]}"
    local files_json="${PLAN_FILES_JSON[$i]}"

    print_report "RUN" "Traitement commit #$idx"

    # Remet l'index propre sans toucher au working tree
    git reset

    mapfile -t patterns < <(jq -r '.[]' <<<"$files_json")
    local p
    for p in "${patterns[@]}"; do
      shopt -s nullglob globstar
      local matches=()
      # shellcheck disable=SC2206
      matches=($p)
      shopt -u nullglob globstar

      local m
      for m in "${matches[@]}"; do
        git add -- "$m"
      done
    done

    if git diff --cached --quiet; then
      print_report "WARN" "Commit #$idx: aucun changement indexé, commit ignoré"
      continue
    fi

    GIT_COMMITTER_DATE="$date" git commit --date "$date" -F - <<EOF
$message
EOF

    print_report "OK" "Commit #$idx créé"
  done
}

run_plan() {
    validate_plan >/dev/null

    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
        print_report "ERROR" "Le dossier courant n'est pas un dépôt Git"
        exit 1
    fi

    local idx=0

    while IFS= read -r commit; do
        idx=$((idx + 1))

        process_commit "$commit"

        print_report "RUN" "Traitement commit #$idx"

        git reset

        mapfile -t patterns < <(jq -r '.[]' <<<"$COMMIT_FILES_JSON" | tr -d '\r')

        for p in "${patterns[@]}"; do
            shopt -s nullglob globstar
            matches=($p)
            shopt -u nullglob globstar

            for m in "${matches[@]}"; do
                git add -- "$m"
            done
        done

        if git diff --cached --quiet; then
            print_report "WARN" "Commit #$idx: aucun changement indexé, commit ignoré"
            continue
        fi

        GIT_COMMITTER_DATE="$COMMIT_DATE" \
        git commit --date "$COMMIT_DATE" -F - <<EOF
$COMMIT_MESSAGE
EOF

        print_report "OK" "Commit #$idx créé"

    done < <(jq -c '.commits[]' "$PLAN_FILE")
}

main() {
  if [[ $# -lt 1 || $# -gt 2 ]]; then
    cat <<USAGE
Usage: gtm <validate|dry-run|run> [chemin/vers/plan.json]

Si le chemin du plan est omis, "./commit-plan.json" (relatif au
dossier courant) est utilisé. "run" et "dry-run" opèrent toujours
sur le dépôt Git du dossier courant.
USAGE
    exit 1
  fi

  case "$1" in
    validate)
      validate_plan
      ;;
    dry-run)
      dry_run
      ;;
    run)
      run_plan
      ;;
    *)
      print_report "ERROR" "Commande inconnue: $1"
      print_report "INFO" "Commandes disponibles: validate, dry-run, run"
      exit 1
      ;;
  esac
}

main "$@"