# Spécification Technique : `commit-plan.json`

> **Version de la spécification** : 1.1.0  
> **Statut** : Stable  
> **Compatibilité JSON Schema** : Draft-07 / 2020-12

Ce document définit la spécification formelle du fichier de plan d'exécution `commit-plan.json` utilisé par **Git Tasks-Time Machine (`gtm`)**.

---

## 1. Vue d'ensemble

Le fichier `commit-plan.json` est le contrat d'échange principal entre :
1. Les moteurs de planification (l'utilisateur humain, le SLM local via `gtm plan`, ou un agent d'intelligence artificielle).
2. Le moteur d'exécution et de validation (`gtm validate`, `gtm dry-run`, `gtm run`).

### 1.1 Emplacement standard et isolation des résidus (`.gtm/`)

Par défaut, le plan est généré et recherché dans le dossier dédié :
```text
.gtm/
├── .gitignore         # Contient '*' pour ignorer 100% des fichiers du dossier
└── commit-plan.json   # Plan de commits généré
```

**Garantie d'invisibilité Git (Zéro résidu)** :  
Grâce au fichier `.gtm/.gitignore` généré automatiquement avec la directive `*`, le dossier `.gtm/` et l'ensemble de ses fichiers temporaires sont **totalement ignorés** par Git dans tout dépôt cible, sans qu'il soit nécessaire de modifier le fichier `.gitignore` racine de votre projet.

*Rétrocompatibilité* : Si un fichier `commit-plan.json` existe à la racine du projet, `gtm` le prend en charge automatiquement en solution de repli.

---

## 2. Schéma JSON Formel

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "GtmCommitPlan",
  "description": "Schéma de validation pour le plan de commits GTM",
  "type": "object",
  "required": ["commits"],
  "additionalProperties": false,
  "properties": {
    "commits": {
      "type": "array",
      "description": "Liste ordonnée chronologiquement des commits à exécuter",
      "minItems": 1,
      "items": {
        "$ref": "#/$defs/CommitItem"
      }
    }
  },
  "$defs": {
    "CommitItem": {
      "type": "object",
      "required": ["date", "message", "files"],
      "additionalProperties": false,
      "properties": {
        "date": {
          "type": "string",
          "description": "Timestamp ISO 8601 strict avec fuseau horaire obligatoire",
          "pattern": "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}([+-][0-9]{2}:[0-9]{2}|Z)$"
        },
        "message": {
          "type": "string",
          "description": "Message de commit respectant Conventional Commits v1.0.0 avec description multi-lignes",
          "minLength": 5
        },
        "files": {
          "type": "array",
          "description": "Liste des chemins relatifs ou glob patterns des fichiers à indexer dans ce commit",
          "minItems": 1,
          "items": {
            "type": "string",
            "minLength": 1
          }
        }
      }
    }
  }
}
```

---

## 3. Propriétés et Règles Métier

### 3.1. `date`
- **Format** : Horodatage ISO 8601 / RFC 3339 étendu.
- **Exemples valides** :
  - `2026-10-16T09:15:00+01:00`
  - `2026-10-16T08:15:00Z`
- **Invariance chronologique** :  
  Pour tout index $i \ge 0$, la condition suivante doit être vérifiée :  
  $$\text{timestamp}(commits[i].date) \le \text{timestamp}(commits[i+1].date)$$
  Si un commit a une date antérieure à son prédécesseur, `gtm validate` rejette le plan avec le code d'erreur 1.

### 3.2. `message`
- **Format** : Conforme aux spécifications `@commitlint/config-conventional` et **Conventional Commits v1.0.0**.
- **Structure attendue** :
  ```text
  <type>(<scope>): <résumé impératif en minuscules>

  <corps optionnel mais obligatoire pour les modifications substantielles>

  - <détail par fichier ou endpoint impacté>
  ```
- **Types autorisés** :
  `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.
- **Règles d'en-tête** :
  - Pas de majuscule en début de sujet (ex: `feat(api): add auth` et non `feat(api): Add auth`).
  - Pas de point final dans la première ligne.
  - Longueur recommandée de l'en-tête : $\le 72$ caractères (maximum toléré : 100 caractères).
- **Règle de séparation du corps** :  
  Une ligne vide (`\n\n`) doit séparer l'en-tête du corps de message.

### 3.3. `files`
- **Format** : Tableau de chaînes représentant des chemins relatifs à la racine du dépôt de travail.
- **Patterns acceptés** :
  - Fichier exact : `"src/auth/jwt.js"`
  - Fichier racine : `"Dockerfile"`, `".dockerignore"`
  - Glob patterns : `"src/**/*.ts"`, `"migrations/*.sql"`
- **Vérification d'existence** :  
  `gtm validate` s'assure qu'au moins un fichier réel correspond à chaque entrée (ou pattern) sur le système de fichiers local.

---

## 4. Exemples Concrets

### 4.1. Exemple Minimaliste (Un seul commit)
```json
{
  "commits": [
    {
      "date": "2026-10-16T14:00:00+01:00",
      "message": "docs(readme): update installation instructions for macos",
      "files": [
        "README.md"
      ]
    }
  ]
}
```

### 4.2. Exemple Avancé (Multi-fichiers avec Corps Sémantique Détaillé)
```json
{
  "commits": [
    {
      "date": "2026-10-16T07:04:27+01:00",
      "message": "feat(docker): add containerization configuration files\n\nProvide reproducible build instructions and runtime entrypoint for container deployments.\n\n- Dockerfile: define multi-stage build and non-root execution user\n- .dockerignore: exclude local node_modules, logs, and Git metadata\n- docker-entrypoint.sh: initialize environment variables and exec main process",
      "files": [
        "Dockerfile",
        ".dockerignore",
        "docker-entrypoint.sh"
      ]
    },
    {
      "date": "2026-10-16T09:15:00+01:00",
      "message": "feat(formalites): implement writing formalities and registration requests\n\nImplement POST /webServTiers/save endpoints in the formalites folder.\n\n- 01-Creation-Personne-Morale.bru: POST /webServTiers/save - Formalité : Création d'entreprise (Personne Morale) - Processus : `ImmPMProcess`\n- 02-Creation-Personne-Physique.bru: POST /webServTiers/save - Formalité : Création d'entreprise (Personne Physique) - Processus : `ImmPPProcess`\n- folder.bru: folder order and metadata",
      "files": [
        "01-Formalites-Ecriture/*.bru"
      ]
    }
  ]
}
```

---

## 5. Résolution des Erreurs Fréquentes

| Message d'erreur `gtm validate` | Cause racine | Solution corrective |
| :--- | :--- | :--- |
| `Le plan n'est pas un JSON valide` | Erreur de syntaxe JSON (virgule manquante, guillemet non échappé). | Valider le fichier avec `jq . commit-plan.json`. |
| `Le plan doit contenir une clé "commits"` | Structure de premier niveau incorrecte. | Encapsuler la liste dans un objet `{"commits": [...]}`. |
| `Date invalide (ISO 8601 requis)` | Format date incomplet (ex: `2026-10-16 10:00:00` sans `T` ni timezone). | Utiliser le format `YYYY-MM-DDTHH:MM:SS+01:00`. |
| `Ordre chronologique invalide` | `commits[i].date` est plus récente que `commits[i+1].date`. | Trier le tableau par ordre croissant des dates. |
| `Format de message invalide` | Le message ne respecte pas `<type>(<scope>): <sujet>` en minuscules. | Corriger l'en-tête selon Conventional Commits. |
| `Fichier inexistant : <path>` | Le fichier listé n'a pas été trouvé sur le disque. | Corriger le chemin ou vérifier `git status`. |
