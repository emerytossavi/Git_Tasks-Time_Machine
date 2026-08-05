#!/usr/bin/env bash
set -euo pipefail

print_report() {
  printf '[%s] %s\n' "$1" "$2"
}

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GTM_SRC="$REPO_DIR/gtm.sh"

if [[ ! -f "$GTM_SRC" ]]; then
  print_report "ERROR" "gtm.sh introuvable dans $REPO_DIR"
  exit 1
fi

chmod +x "$GTM_SRC"

# Choix du dossier bin : celui déjà présent et déjà dans le PATH est
# préféré, sinon ~/.local/bin (convention Linux), sinon ~/bin (Git Bash).
BIN_DIR=""
for candidate in "$HOME/.local/bin" "$HOME/bin"; do
  if [[ ":$PATH:" == *":$candidate:"* ]] && [[ -d "$candidate" ]]; then
    BIN_DIR="$candidate"
    break
  fi
done

if [[ -z "$BIN_DIR" ]]; then
  BIN_DIR="$HOME/.local/bin"
fi

mkdir -p "$BIN_DIR"
ln -sf "$GTM_SRC" "$BIN_DIR/gtm"
print_report "OK" "Lien créé : $BIN_DIR/gtm -> $GTM_SRC"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  RC_FILE="$HOME/.bashrc"
  EXPORT_LINE="export PATH=\"$BIN_DIR:\$PATH\""

  if [[ -f "$RC_FILE" ]] && grep -qF "$EXPORT_LINE" "$RC_FILE" 2>/dev/null; then
    print_report "INFO" "$BIN_DIR est déjà ajouté dans $RC_FILE (redémarre le terminal)"
  else
    printf '\n# Ajouté par git-helpers/install.sh\n%s\n' "$EXPORT_LINE" >> "$RC_FILE"
    print_report "OK" "$BIN_DIR ajouté au PATH dans $RC_FILE"
  fi

  print_report "INFO" "Ouvre un nouveau terminal (ou lance: source $RC_FILE) pour que 'gtm' soit reconnu"
else
  print_report "OK" "$BIN_DIR est déjà dans le PATH"
fi

print_report "OK" "Installation terminée. Teste avec: gtm"
