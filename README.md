# Git Tasks-Time Machine

Git Tasks-Time Machine est un helper Bash qui rejoue un historique Git à partir d'un plan JSON prédéfini.

Il **n'invente jamais** de commits : il exécute strictement ce qui est décrit dans un fichier de plan (dates, messages, fichiers, ordre chronologique).

## Prérequis

- Bash (Linux ou Git Bash sous Windows)
- `jq`
- Git
- GNU `date` (fourni par défaut avec Git Bash sous Windows)

## Installation

Le script (`gtm.sh`) n'a pas besoin d'être copié dans chaque projet. Il s'installe une seule fois, globalement, sur chaque machine, via un lien symbolique pointant vers ce dépôt — et reste ensuite utilisable depuis n'importe quel dossier sous le nom `gtm`.

### Sur une nouvelle machine

Après avoir cloné ce dépôt (une seule fois par machine) :

```bash
git https://github.com/emerytossavi/Git_Tasks-Time_Machine.git
bash ~/WorkSpace/Helpers/git-helpers/install.sh
```

`install.sh` :

- rend `gtm.sh` exécutable
- crée un lien symbolique `gtm` dans `~/.local/bin` (ou dans un dossier déjà présent dans le `PATH`, ex. `~/bin` sous Git Bash)
- ajoute ce dossier au `PATH` dans `~/.bashrc` s'il n'y est pas déjà
- ne fait rien si c'est déjà installé (idempotent — relançable sans risque après un `git pull`)

Ouvrir un nouveau terminal (ou `source ~/.bashrc`) ensuite pour que `gtm` soit reconnu.

Fonctionne à l'identique sous Linux et sous Windows (Git Bash) — le script détecte lui-même le dossier `bin` approprié.

### Installation manuelle (alternative)

```bash
chmod +x ~/WorkSpace/Helpers/git-helpers/gtm.sh
mkdir -p ~/.local/bin   # ou ~/bin sous Git Bash
ln -sf ~/WorkSpace/Helpers/git-helpers/gtm.sh ~/.local/bin/gtm
```

Une fois le lien créé, `gtm` est disponible dans tous les terminaux (ouvrir un nouveau terminal si le `PATH` vient d'être modifié). Toute mise à jour de `gtm.sh` dans ce dépôt est immédiatement prise en compte, sans réinstallation.

## Utilisation depuis n'importe quel projet

`gtm` opère toujours sur le dépôt Git du **répertoire courant** (celui depuis lequel il est appelé), jamais sur celui où réside physiquement le script. Le fichier de plan, lui, peut se trouver n'importe où — il n'a pas besoin d'être versionné dans ce dépôt.

```bash
cd ~/mon-autre-projet
gtm validate ./commit-plan.json
gtm dry-run  ./commit-plan.json
gtm run      ./commit-plan.json
```

Le chemin du plan est optionnel : s'il est omis, `gtm` cherche `./commit-plan.json` dans le dossier courant.

```bash
gtm run   # équivalent à: gtm run ./commit-plan.json
```

## Structure de ce dépôt

```text
git-helpers/
├── gtm.sh                    # le script
├── install.sh                # installation globale (voir ci-dessus)
├── sample-commit-plan.json   # exemple de plan
├── README.md
└── LICENSE
```

`commit-plan.json` (ou tout autre nom choisi) vit dans **le projet cible**, pas dans ce dépôt.

## Format du plan JSON

```json
{
  "commits": [
    {
      "date": "2026-07-03T18:22:00+01:00",
      "message": "feat(auth): ajout des permissions\n\nAjout du middleware de vérification des permissions afin de centraliser le contrôle d'accès.",
      "files": [
        "app/Models/User.php",
        "routes/web.php"
      ]
    }
  ]
}
```

### Règles importantes

- `message` est une chaîne JSON unique (avec `\n` pour les retours à la ligne).
- Ne pas séparer `title` / `body`.
- `files` peut contenir des chemins explicites et des glob patterns (`src/**/*.php`).
- Les chemins dans `files` sont résolus relativement au dossier courant (le projet cible), pas au dossier du plan.

## Commandes disponibles

### 1) Validation seule

```bash
gtm validate [chemin/vers/plan.json]
```

Vérifie :

- JSON valide
- dates ISO8601
- ordre chronologique
- message non vide
- tableau `files` non vide
- existence des fichiers
- expansion correcte des glob patterns

Aucune modification Git.

### 2) Simulation

```bash
gtm dry-run [chemin/vers/plan.json]
```

Affiche pour chaque commit :

- la date
- le message complet
- les fichiers réellement ciblés (après expansion des globs)

Aucune modification Git.

### 3) Exécution

```bash
gtm run [chemin/vers/plan.json]
```

Pour chaque commit du plan :

1. `git reset` (nettoyage de l'index)
2. `git add` des fichiers listés
3. vérification qu'il y a bien des changements indexés
4. commit avec la date du plan via `GIT_COMMITTER_DATE` et `git commit --date`

Le message est injecté via heredoc pour conserver les retours à la ligne.

Si aucun changement n'est indexé pour une entrée, un avertissement est affiché et le script passe au commit suivant.

## Exemple complet

```bash
cd ~/mon-projet

# 1. Préparer le dépôt et les fichiers
# 2. Écrire commit-plan.json

gtm validate
gtm dry-run
gtm run
```
