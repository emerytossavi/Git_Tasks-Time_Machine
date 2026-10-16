#!/usr/bin/env python3
"""
lib/planner.py - Générateur éco-responsable de plan de commits pour Git Tasks-Time Machine.
Analyse les fichiers locaux, détecte les dépendances et relations, et fait appel
au SLM local (Qwen2.5-Coder 1.5B via Ollama) pour structurer le plan JSON.
"""

import sys
import os
import re
import json
import urllib.request
import urllib.error
import subprocess
from datetime import datetime, timedelta, time
from pathlib import Path
import random

SYSTEM_EXCLUDES = {
    ".git",
    ".DS_Store",
    "commit-plan.json"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".bin", ".dylib", ".so", ".a",
    ".mp3", ".mp4", ".mov", ".avi", ".woff", ".woff2", ".ttf", ".eot"
}

def is_system_excluded(rel_path: str) -> bool:
    """Vérifie si un chemin fait partie des exclusions système indispensables (.git, commit-plan.json, .DS_Store)."""
    p = Path(rel_path)
    if any(part == ".git" for part in p.parts):
        return True
    if p.name == ".DS_Store" or p.name == "commit-plan.json":
        return True
    return False

def is_text_file(filepath: Path) -> bool:
    if filepath.suffix.lower() in BINARY_EXTENSIONS:
        return False
    try:
        with open(filepath, "tr", encoding="utf-8") as f:
            f.read(1024)
            return True
    except Exception:
        return False

def get_git_status_files(cwd: Path):
    """Retourne la liste des fichiers modifiés ou non suivis selon git status (y compris dans les sous-dossiers)."""
    try:
        # -uall garantit que les fichiers dans les sous-dossiers non suivis sont tous listés individuellement
        # Git applique automatiquement l'ensemble des règles .gitignore du projet.
        cmd = ["git", "status", "--porcelain", "-uall"]
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
        files = []
        for line in res.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                path_str = parts[1]
                if " -> " in path_str:
                    path_str = path_str.split(" -> ")[1]
                path_clean = path_str.strip('"')
                if is_system_excluded(path_clean):
                    continue
                p = cwd / path_clean
                if p.is_file() and is_text_file(p):
                    files.append(str(p.relative_to(cwd)))
                elif p.is_dir():
                    # Sécurité : si une entrée non suivie est un dossier brut
                    for root, _, filenames in os.walk(p):
                        for fn in filenames:
                            sub_p = Path(root) / fn
                            rel_sub = str(sub_p.relative_to(cwd))
                            if not is_system_excluded(rel_sub) and is_text_file(sub_p):
                                files.append(rel_sub)
        return files
    except Exception:
        return []

def get_all_git_files(cwd: Path):
    """Retourne tous les fichiers du projet en appliquant 100% des règles .gitignore via git ls-files."""
    try:
        cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=True)
        files = []
        for line in res.stdout.splitlines():
            line = line.strip().strip('"')
            if not line or is_system_excluded(line):
                continue
            p = cwd / line
            if p.is_file() and is_text_file(p) and p.stat().st_size < 500 * 1024:
                files.append(line)
        return files
    except Exception:
        return []

def parse_gitignore(cwd: Path) -> list:
    """Lit les motifs d'exclusion d'un fichier .gitignore s'il existe (fallback hors dépôt Git)."""
    gitignore_path = cwd / ".gitignore"
    patterns = []
    if gitignore_path.is_file():
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        patterns.append(line)
        except Exception:
            pass
    return patterns

def matches_gitignore(rel_path: str, patterns: list) -> bool:
    """Vérifie si un chemin relatif correspond à l'un des motifs .gitignore."""
    from fnmatch import fnmatch
    p = Path(rel_path)
    for pat in patterns:
        pat_clean = pat.rstrip("/")
        if fnmatch(rel_path, pat_clean) or fnmatch(p.name, pat_clean):
            return True
        if any(fnmatch(part, pat_clean) for part in p.parts):
            return True
    return False

def scan_directory(cwd: Path, all_files=False):
    """Scanne le dossier courant et sélectionne les fichiers pertinents dans toute l'arborescence."""
    if not all_files:
        git_files = get_git_status_files(cwd)
        if git_files:
            return sorted(set(git_files))

    # 1. Utilisation prioritaire du moteur Git natif (respecte .gitignore racine + sous-dossiers)
    all_git_files = get_all_git_files(cwd)
    if all_git_files:
        return sorted(set(all_git_files))

    # 2. Fallback si hors dépôt Git : lecture directe du .gitignore local + os.walk
    patterns = parse_gitignore(cwd)
    selected = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if not is_system_excluded(d) and not matches_gitignore(d, patterns)]
        for f in files:
            p = Path(root) / f
            rel_p = str(p.relative_to(cwd))
            if is_system_excluded(rel_p) or matches_gitignore(rel_p, patterns):
                continue
            if is_text_file(p) and p.stat().st_size < 500 * 1024:
                selected.append(rel_p)

    return sorted(set(selected))

def extract_file_intent(cwd: Path, rel_path: str) -> str:
    """Extrait l'intention métier/technique réelle du fichier (via git diff ou docstrings/commentaires)."""
    full_path = cwd / rel_path

    # 1. Si le fichier est suivi et modifié, extraire les lignes clés du git diff
    try:
        cmd = ["git", "diff", "-U0", "--no-color", "--", rel_path]
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if res.stdout:
            added = []
            for l in res.stdout.splitlines():
                if l.startswith("+") and not l.startswith("+++"):
                    clean = l[1:].strip()
                    # Ignorer les lignes de pure syntaxe
                    if len(clean) > 5 and clean not in ("{", "}", ");", "];", "end"):
                        added.append(clean)
            if added:
                # Filtrer les commentaires et déclarations ajoutées
                meaningful = [l for l in added if any(l.startswith(x) for x in ("#", "//", "/*", "*", "def ", "class ", "function ", "public ", "const ", "var ", "let "))]
                summary = meaningful if meaningful else added
                return "changes: " + " | ".join(summary[:3])
    except Exception:
        pass

    # 2. Détection d'intention spécifique pour Docker, CI, build, config et docs
    name_lower = full_path.name.lower()
    ext_lower = full_path.suffix.lower()
    rel_lower = rel_path.lower()

    if "docker" in rel_lower or name_lower.startswith("dockerfile") or name_lower.startswith(".dockerignore"):
        if name_lower.startswith(".dockerignore"):
            return "define build context exclusions for container packaging"
        elif "entrypoint" in name_lower or ext_lower in (".sh", ".bash"):
            return "manage container runtime startup and entrypoint initialization"
        elif name_lower.startswith("docker-compose"):
            return "orchestrate multi-container services and network environment"
        else:
            return "configure container build environment and runtime image"
    elif name_lower == ".gitignore":
        return "configure repository ignore rules for untracked files"
    elif name_lower in ("readme.md", "readme"):
        return "provide project documentation, architecture overview and usage guides"
    elif name_lower in ("license", "license.md"):
        return "define software license and distribution terms"

    # 3. Pour les nouveaux fichiers de code : extraire docstrings ou signatures de fonctions
    doc_lines = []
    in_block = False
    symbols = []

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            for _ in range(60):
                line = f.readline()
                if not line:
                    break
                s = line.strip()

                # Docstring Python """ ou bloc /* */
                if '"""' in s:
                    in_block = not in_block
                    clean = s.replace('"""', "").strip()
                    if clean:
                        doc_lines.append(clean)
                    continue
                elif "/*" in s:
                    in_block = True
                    clean = s.replace("/*", "").replace("*/", "").strip()
                    if clean:
                        doc_lines.append(clean)
                    continue
                elif "*/" in s:
                    in_block = False
                    continue

                if in_block:
                    clean = re.sub(r"^\*+\s*", "", s).strip()
                    if clean and len(clean) > 5:
                        doc_lines.append(clean)
                    continue

                if s.startswith(("#", "//")):
                    clean = re.sub(r"^[#/]+\s*", "", s).strip()
                    if clean and len(clean) > 8 and not clean.startswith(("!", "shellcheck", "eslint", "coding")):
                        doc_lines.append(clean)

                m = re.search(r"(?:class|def|function|async def|public function)\s+([a-zA-Z0-9_]+)", s)
                if m:
                    symbols.append(m.group(1))
    except Exception:
        pass

    if doc_lines:
        headline = doc_lines[0]
        if len(doc_lines) > 1 and len(headline) < 30:
            headline += " - " + doc_lines[1]
        return headline[:120]
    elif symbols:
        return f"implements {', '.join(symbols[:3])}"
    
    return "implement core functionality"

def categorize_file(rel_path: str):
    """Détermine le type Conventional Commit, le scope recommandé et la catégorie logique du fichier."""
    p = Path(rel_path)
    name = p.name.lower()
    ext = p.suffix.lower()
    rel_lower = rel_path.lower()

    if "docker" in rel_lower or name.startswith("dockerfile") or name.startswith(".dockerignore"):
        return {"type": "build", "scope": "docker", "category": "docker"}
    if ".github" in rel_lower or ".gitlab" in rel_lower or "jenkins" in rel_lower or "circleci" in rel_lower:
        return {"type": "ci", "scope": "ci", "category": "ci"}
    if name in ["package.json", "package-lock.json", "pom.xml", "build.gradle", "cargo.toml", "requirements.txt", "pyproject.toml", "setup.py", "makefile"]:
        return {"type": "build", "scope": "deps", "category": "deps"}
    if "test" in rel_lower or "spec" in rel_lower:
        return {"type": "test", "scope": "test", "category": "test"}
    if name in ["readme.md", "license", "contributing.md", "changelog.md"] or ext in [".md", ".txt"] or rel_lower.startswith("docs/"):
        return {"type": "docs", "scope": "docs", "category": "docs"}
    if name.startswith(".env") or ext in [".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".env"]:
        return {"type": "chore", "scope": "config", "category": "config"}
    if ext in [".sh", ".bash", ".zsh"]:
        return {"type": "chore", "scope": "cli" if "gtm" in rel_lower or "cli" in rel_lower else "scripts", "category": "scripts"}
    
    # Code applicatif : déduire le scope du répertoire ou du fichier
    if len(p.parts) > 1:
        scope = re.sub(r'^[0-9]+[_\-]*', '', p.parts[0]).lower()
        scope = re.sub(r'[^a-zA-Z0-9_\-]', '', scope) or "core"
    else:
        scope = p.stem.lower()
        scope = re.sub(r'^[0-9]+[_\-]*', '', scope)
        scope = re.sub(r'[^a-zA-Z0-9_\-]', '', scope) or "core"
    return {"type": "feat", "scope": scope, "category": scope}

def analyze_file(cwd: Path, rel_path: str):
    """Analyse légère: extrait les imports, définitions clés, rôle et intention sémantique."""
    full_path = cwd / rel_path
    cat = categorize_file(rel_path)

    symbols = []
    imports = []

    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [f.readline() for _ in range(80)]

        for line in lines:
            line_s = line.strip()
            # Imports génériques
            m_imp = re.search(r'(?:import|from|require|use|source|\.)\s+["\']?([a-zA-Z0-9_\-\./]+)', line_s)
            if m_imp:
                imp = m_imp.group(1).replace('"', '').replace("'", "")
                imports.append(imp)
            # Définitions génériques
            m_def = re.search(r'(?:class|def|function|interface|type|struct|enum)\s+([a-zA-Z0-9_]+)', line_s)
            if m_def:
                symbols.append(m_def.group(1))
    except Exception:
        pass

    intent = extract_file_intent(cwd, rel_path)

    return {
        "path": rel_path,
        "type": cat["type"],
        "scope": cat["scope"],
        "category": cat["category"],
        "role": cat["type"],
        "intent": intent,
        "symbols": symbols[:4],
        "imports": imports[:5]
    }

def resolve_links(file_analyses):
    """Identifie les liens réels entre les fichiers du projet."""
    all_paths = {fa["path"]: fa for fa in file_analyses}
    
    for fa in file_analyses:
        linked = set()
        for imp in fa["imports"]:
            for target_path in all_paths:
                if target_path == fa["path"]:
                    continue
                target_stem = Path(target_path).stem
                if target_stem in imp or imp in target_path:
                    linked.add(target_path)
        fa["links_to"] = list(linked)
        del fa["imports"]

def call_ollama(prompt_content: str, is_modular=False, model="qwen2.5-coder:1.5b", base_url="http://localhost:11434"):
    """Appelle Ollama avec sortie JSON contrainte et dimensionnement adapté."""
    url = f"{base_url}/api/chat"

    id_key = "module_ids" if is_modular else "file_ids"
    example_id = "[1, 2]" if is_modular else "[1, 2]"

    system_prompt = (
        "You are an expert Git commit architect adhering strictly to Conventional Commits v1.0.0 and @commitlint/config-conventional rules.\n"
        "Your task is to organize the numbered items into logical, atomic commits using their integer IDs in '" + id_key + "'.\n\n"
        "CRITICAL CONVENTIONAL COMMITS & COMMITLINT SPECIFICATIONS:\n"
        "1. Every ID from 1 to N MUST be included in exactly one commit in '" + id_key + "'.\n"
        "2. ALLOWED TYPES (type-enum):\n"
        "   - 'feat': user-facing new feature or capability\n"
        "   - 'fix': bug fix or corrective behavior\n"
        "   - 'build': changes affecting build system, packaging, external dependencies, or containerization (Docker, npm, maven)\n"
        "   - 'ci': changes to CI/CD workflows and scripts (GitHub Actions, pipelines)\n"
        "   - 'docs': documentation only (README, API docs, licenses)\n"
        "   - 'refactor': code change that neither fixes a bug nor adds a feature\n"
        "   - 'test': adding or updating test suites\n"
        "   - 'chore': maintenance, tooling, configuration files\n"
        "3. SCOPES (scope-case):\n"
        "   - MUST be in lower-case (e.g. docker, auth, api, cli, config, deps, docs)\n"
        "   - FORBIDDEN SCOPES: NEVER use 'code', 'file', 'files', 'all', or empty/generic scopes.\n"
        "4. ATOMIC COHERENCE:\n"
        "   - Group all related files that form a single logical unit of work into ONE commit (e.g. Dockerfile + .dockerignore + entrypoint MUST be in a single 'build(docker)' commit).\n"
        "5. SUBJECT LINE RULES (subject-case, subject-full-stop, imperative-mood):\n"
        "   - Format: '<type>(<scope>): <subject>'\n"
        "   - MUST start with a LOWER-CASE imperative verb: add, configure, setup, implement, update, remove, fix (NOT 'added', NOT 'Configure').\n"
        "   - MUST NOT end with a period ('.').\n"
        "   - STRICTLY FORBIDDEN: NEVER write 'add <filename>' or repeat file paths/extensions (e.g. FORBIDDEN: 'add Dockerfile', 'add .dockerignore', 'add main.py').\n"
        "   - Describe the actual technical ACTION and INTENT.\n"
        "     * CORRECT: 'build(docker): configure multi-stage container build and startup entrypoint'\n"
        "     * CORRECT: 'feat(auth): implement Google OAuth registration flow'\n"
        "     * CORRECT: 'docs(readme): add installation guide and usage examples'\n"
        "6. Output strictly a JSON object matching this schema:\n"
        "{\n"
        '  "commits": [\n'
        '    {"message": "<type>(<scope>): <action summary>", "' + id_key + '": ' + example_id + '}\n'
        "  ]\n"
        "}"
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": prompt_content
            }
        ],
        "format": "json",
        "stream": False,
        "keep_alive": 0,
        "options": {
            "temperature": 0.1,
            "num_ctx": 4096,
            "num_predict": 1000
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            content = body.get("message", {}).get("content", "{}")
            return json.loads(content)
    except urllib.error.URLError as e:
        print(f"\033[0;31m[ERROR]\033[0m Impossible de joindre Ollama ({base_url}) : {e}", file=sys.stderr)
        print("Vérifiez qu'Ollama est démarré avec 'ollama serve' ou lancez l'application Ollama.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\033[0;31m[ERROR]\033[0m Échec lors du parsing de la réponse LLM : {e}", file=sys.stderr)
        sys.exit(1)

def generate_synthetic_timestamps(commits, start_date=None, interval_min=45, interval_max=120):
    """Génère des timestamps synthétiques répartis sur des heures ouvrées."""
    now = datetime.now().astimezone()
    tz = now.tzinfo
    n_commits = len(commits)

    if start_date:
        try:
            current_dt = datetime.fromisoformat(start_date).replace(tzinfo=tz)
        except Exception:
            current_dt = now - timedelta(days=2)
    else:
        days_back = max(1, (n_commits * 90) // (8 * 60))
        current_dt = (now - timedelta(days=days_back)).replace(hour=9, minute=15, second=0)

    for c in commits:
        if current_dt.time() > time(18, 30):
            current_dt = (current_dt + timedelta(days=1)).replace(
                hour=9, minute=random.randint(10, 40), second=0
            )

        while current_dt.weekday() in (5, 6):
            current_dt = (current_dt + timedelta(days=1)).replace(
                hour=9, minute=random.randint(10, 40), second=0
            )

        c["date"] = current_dt.isoformat(timespec="seconds")
        delta_minutes = random.randint(interval_min, interval_max)
        current_dt += timedelta(minutes=delta_minutes)

    return commits

def assign_timestamps(commits, cwd: Path, start_date=None, strategy="last"):
    """
    Assigne des dates basées sur l'heure réelle de dernière modification (mtime) des fichiers.
    Strategy:
      - 'last': se base sur le dernier fichier modifié du lot (max)
      - 'first': se base sur le premier fichier modifié du lot (min)
    Garantit l'ordre chronologique strict requis par validator.sh.
    """
    now = datetime.now().astimezone()
    tz = now.tzinfo

    if start_date:
        return generate_synthetic_timestamps(commits, start_date=start_date)

    commit_entries = []
    for c in commits:
        mtimes = []
        for f in c.get("files", []):
            p = cwd / f
            if p.exists():
                try:
                    mtimes.append(os.path.getmtime(p))
                except Exception:
                    pass

        if mtimes:
            raw_time = min(mtimes) if strategy == "first" else max(mtimes)
            commit_mtime = int(round(raw_time))
        else:
            commit_mtime = None

        commit_entries.append({"commit": c, "mtime": commit_mtime})

    valid_mtimes = [e["mtime"] for e in commit_entries if e["mtime"] is not None]
    if not valid_mtimes or (max(valid_mtimes) - min(valid_mtimes) < 5):
        # Cas où tous les fichiers ont été clonés ou touchés dans la même seconde
        return generate_synthetic_timestamps(commits)

    # Trier les commits selon la chronologie réelle de modification
    commit_entries.sort(key=lambda e: e["mtime"] if e["mtime"] is not None else 0)

    prev_epoch = 0
    sorted_commits = []

    for entry in commit_entries:
        c = entry["commit"]
        target_epoch = entry["mtime"] if entry["mtime"] is not None else (prev_epoch + 60)

        # Si deux commits ont la même seconde ou sont dans le désordre, avancer d'au moins 60s
        if target_epoch <= prev_epoch:
            target_epoch = prev_epoch + random.randint(60, 180)

        prev_epoch = target_epoch
        dt = datetime.fromtimestamp(target_epoch).astimezone(tz)
        c["date"] = dt.isoformat(timespec="seconds")
        sorted_commits.append(c)

    return sorted_commits

ALLOWED_CONVENTIONAL_TYPES = {
    "feat", "fix", "build", "ci", "docs", "style", "refactor", "perf", "test", "chore", "revert"
}

def sanitize_commit_message(msg: str, commit_files: list = None) -> str:
    """
    Nettoie et normalise le message selon la spécification @commitlint/config-conventional:
    - type-enum : validation parmi les types officiels
    - scope-case : minuscules, suppression des extensions et des scopes interdits ('code', 'file', etc.)
    - subject-case : première lettre en minuscule
    - subject-full-stop : suppression de tout point final
    - élimination de l'anti-pattern 'add <fichier>'
    """
    msg = msg.strip()
    lines = msg.split("\n", 1)
    subject = lines[0].strip()
    body = ("\n" + lines[1]) if len(lines) > 1 else ""

    m = re.match(r'^([a-zA-Z]+)(?:\(([^)]+)\))?\s*:\s*(.*)', subject)
    if m:
        type_part = m.group(1).lower()
        scope_part = (m.group(2) or "").strip().lower()
        rest = m.group(3).strip()
    else:
        type_part = "feat"
        scope_part = ""
        rest = subject

    if type_part not in ALLOWED_CONVENTIONAL_TYPES:
        type_part = "feat"

    # Inférence automatique du type et du scope si tous les fichiers partagent un même domaine
    if commit_files:
        all_docker = all("docker" in f.lower() or Path(f).name.lower().startswith(("dockerfile", ".dockerignore")) for f in commit_files)
        all_docs = all(any(x in f.lower() for x in ["readme", "license", "contributing", "doc"]) for f in commit_files)
        all_tests = all("test" in f.lower() or "spec" in f.lower() for f in commit_files)
        all_ci = all(".github" in f.lower() or ".gitlab" in f.lower() or "ci" in f.lower() for f in commit_files)

        if all_docker:
            type_part = "build"
            scope_part = "docker"
        elif all_docs:
            type_part = "docs"
            scope_part = "docs" if not scope_part or scope_part in ("core", "code") else scope_part
        elif all_tests:
            type_part = "test"
            scope_part = "test" if not scope_part or scope_part in ("core", "code") else scope_part
        elif all_ci:
            type_part = "ci"
            scope_part = "ci"

    # Nettoyage du scope
    if scope_part:
        scope_name = Path(scope_part).stem
        if "/" in scope_name or "\\" in scope_name:
            scope_name = Path(scope_name).name
        scope_clean = re.sub(r'^[0-9]+[_\-]*', '', scope_name)
        scope_clean = re.sub(r'[^a-zA-Z0-9_\-]', '', scope_clean).lower()
        if scope_clean in ("code", "file", "files", "all", "project", "repo", "misc"):
            scope_clean = ""
        scope_part = scope_clean

    # Nettoyage du sujet
    rest = rest.rstrip(".")
    if " | " in rest:
        rest = rest.split(" | ")[0].strip()

    # Nettoyage des motifs répétitifs ou mal formulés
    rest = re.sub(r'^(?:add\s+)?implement core functionality', f'implement {scope_part or "module"} resources', rest, flags=re.IGNORECASE)
    rest = re.sub(r'^(?:add\s+)?provide project documentation.*', 'add project documentation and usage overview', rest, flags=re.IGNORECASE)
    rest = re.sub(r'^(?:add\s+)?(?:consultation|formalit[eé])\s*:\s*', '', rest, flags=re.IGNORECASE)

    if rest:
        rest = rest[0].lower() + rest[1:]

    # S'assurer d'avoir un verbe impératif
    if not re.match(r'^(?:add|configure|setup|implement|update|remove|fix|refactor|create|define|integrate|orchestrate|support)\b', rest, re.IGNORECASE):
        rest = f"add {rest}"

    # Correction de l'anti-pattern "add <filename>"
    if commit_files and re.match(r'^(?:add|added|create|created)\s+[a-zA-Z0-9_\.\-]+(?:\.[a-zA-Z0-9]+)?$', rest.strip(), re.IGNORECASE):
        if any("docker" in f.lower() for f in commit_files):
            rest = "configure containerization and startup entrypoint"
            type_part = "build"
            scope_part = "docker"
        elif any(f.endswith(".gitignore") for f in commit_files):
            rest = "configure repository ignore rules"
            type_part = "chore"
        elif any("readme" in f.lower() for f in commit_files):
            rest = "add documentation and usage overview"
            type_part = "docs"
        elif any("test" in f.lower() for f in commit_files):
            rest = "add automated test cases"
            type_part = "test"
        else:
            rest = f"implement {scope_part or 'core'} functionality"

    if scope_part:
        formatted = f"{type_part}({scope_part}): {rest}"
    else:
        formatted = f"{type_part}: {rest}"

    return formatted + body

def reconcile_and_clean_commits(commits, all_files, cwd: Path):
    """Élimine les doublons, filtre les fichiers hors cible et réconcilie les orphelins."""
    target_set = set(all_files)
    assigned_files = set()
    cleaned_commits = []

    for c in commits:
        filtered_files = []
        for f in c.get("files", []):
            if f in target_set and f not in assigned_files and (cwd / f).exists():
                filtered_files.append(f)
                assigned_files.add(f)
        if filtered_files:
            c["files"] = filtered_files
            c["message"] = sanitize_commit_message(c.get("message", "feat(core): update files"), filtered_files)
            cleaned_commits.append(c)

    # Réconciliation des orphelins (fichiers ciblés mais non cités par le modèle)
    unassigned = [f for f in all_files if f not in assigned_files and (cwd / f).exists()]
    if unassigned:
        docs_orphans = [f for f in unassigned if any(x in f.lower() for x in ["readme", "license", "doc"])]
        code_orphans = [f for f in unassigned if f not in docs_orphans]

        if docs_orphans:
            docs_commit = next((c for c in cleaned_commits if "docs" in c.get("message", "").lower()), None)
            if docs_commit:
                docs_commit["files"].extend(docs_orphans)
            else:
                cleaned_commits.append({
                    "message": "docs: add documentation and project references\n\nIncludes README, license and reference docs.",
                    "files": docs_orphans
                })

        if code_orphans:
            if cleaned_commits:
                cleaned_commits[-1]["files"].extend(code_orphans)
            else:
                cleaned_commits.append({
                    "message": "feat: project updates\n\nUpdates target files.",
                    "files": code_orphans
                })

    return cleaned_commits

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Générateur sobre de commit-plan.json via SLM local (Qwen2.5-Coder 1.5B).")
    parser.add_argument("plan_file", nargs="?", default="commit-plan.json", help="Fichier de sortie (défaut: commit-plan.json)")
    parser.add_argument("-o", "--output", default=None, help="Chemin alternatif du fichier de sortie")
    parser.add_argument("-a", "--all", action="store_true", help="Analyser tous les fichiers du dossier (pas uniquement git status)")
    parser.add_argument("-m", "--model", default="qwen2.5-coder:1.5b", help="Modèle Ollama (défaut: qwen2.5-coder:1.5b)")
    parser.add_argument("--start-date", default=None, help="Date de départ ISO (ex: 2026-10-10T09:00:00)")
    parser.add_argument("--date-strategy", choices=["last", "first"], default="last", help="Dater selon le 'last' (dernier fichier modifié, défaut) ou 'first' (premier)")
    parser.add_argument("--dry-run", action="store_true", help="Afficher le plan généré sans modifier de fichier")
    args = parser.parse_args()

    output_file = args.output or args.plan_file
    cwd = Path.cwd()

    print(f"\033[0;34m[INFO]\033[0m Exploration de {cwd}...")
    files = scan_directory(cwd, all_files=args.all)

    if not files:
        print("\033[0;33m[WARN]\033[0m Aucun fichier éligible trouvé pour générer un plan.")
        sys.exit(0)

    print(f"\033[0;34m[INFO]\033[0m {len(files)} fichier(s) détecté(s). Analyse des liaisons structurelles...")
    analyses = [analyze_file(cwd, f) for f in files]
    resolve_links(analyses)

    analyses_dict = {fa["path"]: fa for fa in analyses}

    # Stratégie hybride : si plus de 12 fichiers, regrouper par sous-dossier/module logique
    is_modular = len(files) > 12
    id_map = {}

    if is_modular:
        from collections import defaultdict
        groups = defaultdict(list)
        for f in files:
            p = Path(f)
            if len(p.parts) > 1:
                # Regrouper au niveau fonctionnel pertinent (max 3 niveaux) pour éviter la sur-fragmentation
                depth = min(3, len(p.parts) - 1)
                parent_dir = str(Path(*p.parts[:depth]))
                groups[parent_dir].append(f)
            else:
                cat = analyses_dict.get(f, {}).get("category", "core")
                groups[f"root/{cat}"].append(f)

        prompt_lines = ["Modules to organize into logical, atomic Conventional Commits:"]
        for idx, (dir_path, g_files) in enumerate(groups.items(), 1):
            id_map[idx] = g_files
            if dir_path.startswith("root/"):
                scope_clean = dir_path.split("/")[1]
            else:
                scope_name = Path(dir_path).name.lower().replace("-", "_")
                scope_clean = re.sub(r'^[0-9]+[_\-]*', '', scope_name)
                scope_clean = re.sub(r'[^a-zA-Z0-9_\-]', '', scope_clean) or "module"

            sample_types = [analyses_dict[gf]["type"] for gf in g_files if gf in analyses_dict]
            primary_type = sample_types[0] if sample_types else "feat"
            sample_intents = [analyses_dict[gf]["intent"] for gf in g_files[:2] if gf in analyses_dict]
            clean_intents = [re.sub(r'^(?:changes:\s*|implements\s*)', '', s).strip() for s in sample_intents if s]
            summary = ", ".join(clean_intents[:2])[:100]
            prompt_lines.append(f"- Module [{idx}] '{scope_clean}' [type: {primary_type}]: {len(g_files)} file(s) ({summary})")
    else:
        prompt_lines = ["Files to organize into logical, atomic Conventional Commits:"]
        for idx, fa in enumerate(analyses, 1):
            id_map[idx] = [fa["path"]]
            desc = f"[{idx}] {fa['path']} [type: {fa['type']}, scope: {fa['scope']}]: {fa['intent']}"
            if fa.get("links_to"):
                desc += f" (links: {', '.join(fa['links_to'])})"
            prompt_lines.append(desc)

    prompt = "\n".join(prompt_lines)
    print(f"\033[0;34m[INFO]\033[0m Inférence via SLM sobre '{args.model}' (mode: {'modulaire' if is_modular else 'fichiers'})...")
    res = call_ollama(prompt, is_modular=is_modular, model=args.model)

    raw_commits = res.get("commits", [])
    if not raw_commits:
        print("\033[0;31m[ERROR]\033[0m Le modèle n'a renvoyé aucun commit.", file=sys.stderr)
        sys.exit(1)

    # Reconstituer la liste réelle des fichiers à partir des identifiants (module_ids ou file_ids)
    expanded_commits = []
    id_key = "module_ids" if is_modular else "file_ids"

    for rc in raw_commits:
        c_files = []
        ids = rc.get(id_key, []) or rc.get("file_ids", []) or rc.get("module_ids", [])
        if not ids and "files" in rc:
            c_files = rc["files"]
        else:
            for item_id in ids:
                try:
                    int_id = int(item_id)
                    if int_id in id_map:
                        c_files.extend(id_map[int_id])
                except Exception:
                    pass

        expanded_commits.append({
            "message": rc.get("message", "feat: project update"),
            "files": c_files
        })

    # Nettoyage, déduplication et réconciliation
    commits = reconcile_and_clean_commits(expanded_commits, files, cwd)

    # Assignation des dates basées sur l'heure réelle de modification (mtime)
    commits = assign_timestamps(commits, cwd, start_date=args.start_date, strategy=args.date_strategy)

    final_plan = {"commits": commits}
    plan_json = json.dumps(final_plan, indent=2, ensure_ascii=False)

    if args.dry_run:
        print("\n\033[0;32m=== Plan de commits généré (Simulation) ===\033[0m")
        print(plan_json)
        return

    out_path = Path(output_file)
    if not out_path.is_absolute():
        out_path = cwd / out_path

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(plan_json + "\n")

    print(f"\033[0;32m[OK]\033[0m Plan de commits généré avec succès : {out_path} ({len(commits)} commits)")

if __name__ == "__main__":
    main()
