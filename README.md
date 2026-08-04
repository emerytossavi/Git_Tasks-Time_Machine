# Git Time Machine

Git Time Machine est un helper Bash qui rejoue un historique Git à partir d’un plan JSON prédéfini.

Il **n’invente jamais** de commits : il exécute strictement ce qui est décrit dans `commit-plan.json` (dates, messages, fichiers, ordre chronologique).

## Prérequis

- Bash
- `jq`
- Git
- GNU `date`

## Structure

```text
git-time-machine/
├── gtm.sh
├── commit-plan.json
├── README.md
└── LICENSE

Format du plan JSON

Le fichier  commit-plan.json  doit respecter cette structure :

{ "commits": [
    {
      "date": "2026-07-03T18:22:00+01:00",
      "message": "feat(auth): ajout des permissions\n\nAjout du middleware de vérification des permissions afin de centraliser le contrôle d'accès.",
      "files": [
        "app/Models/User.php",
        "routes/web.php"
      ]
    } ]
}

Règles importantes

•  message  est une chaîne JSON unique (avec  \n  pour les retours à la ligne).
• Ne pas séparer  title  /  body .
•  files  peut contenir des chemins explicites et des glob patterns ( src/**/*.php ).

Commandes disponibles

Rendre le script exécutable :

chmod +x gtm.sh

1) Validation seule

./gtm.sh validate

Vérifie :

• JSON valide
• dates ISO8601
• ordre chronologique
• message non vide
• tableau  files  non vide
• existence des fichiers
• expansion correcte des glob patterns

Aucune modification Git.

2) Simulation

./gtm.sh dry-run

Affiche pour chaque commit :

• la date
• le message complet
• les fichiers réellement ciblés (après expansion des globs)

Aucune modification Git.

3) Exécution

./gtm.sh run

Pour chaque commit du plan :

1.  git reset  (nettoyage de l’index)
2.  git add  des fichiers listés
3. vérification qu’il y a bien des changements indexés
4. commit avec la date du plan via :
•  GIT_COMMITTER_DATE 
•  git commit --date 

Le message est injecté via heredoc pour conserver les retours à la ligne.

Si aucun changement n’est indexé pour une entrée, un avertissement est affiché et le script passe au commit suivant.

Exemple complet

1. Préparer votre dépôt et vos fichiers.
2. Éditer  commit-plan.json .
3. Valider :

./gtm.sh validate

4. Simuler :

./gtm.sh dry-run

5. Exécuter :

./gtm.sh run