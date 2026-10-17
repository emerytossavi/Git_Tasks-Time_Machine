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

DEFAULT_IGNORES = {
    ".git", ".svn", ".hg", "node_modules", "vendor", "__pycache__",
    ".venv", "env", ".cache", "dist", "build", ".DS_Store",
    "commit-plan.json", ".idea", ".vscode"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".bin", ".dylib", ".so", ".a",
    ".mp3", ".mp4", ".mov", ".avi", ".woff", ".woff2", ".ttf", ".eot"
}

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
    """Retourne la liste des fichiers modifiés ou non suivis selon git status."""
    try:
        cmd = ["git", "status", "--porcelain"]
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
                p = cwd / path_clean
                if p.is_file() and path_clean != "commit-plan.json" and not path_clean.startswith(".git"):
                    files.append(str(p.relative_to(cwd)))
        return files
    except Exception:
        return []

def scan_directory(cwd: Path, all_files=False):
    """Scanne le dossier courant et sélectionne les fichiers pertinents."""
    if not all_files:
        git_files = get_git_status_files(cwd)
        if git_files:
            return sorted(git_files)

    selected = []
    for root, dirs, files in os.walk(cwd):
        dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORES and not d.startswith(".")]
        rel_root = Path(root).relative_to(cwd)
        if any(part in DEFAULT_IGNORES for part in rel_root.parts):
            continue

        for f in files:
            if f in DEFAULT_IGNORES or f.startswith("."):
                continue
            p = Path(root) / f
            rel_p = p.relative_to(cwd)
            if str(rel_p) == "commit-plan.json":
                continue
            if is_text_file(p) and p.stat().st_size < 500 * 1024:
                selected.append(str(rel_p))

    return sorted(selected)

def analyze_file(cwd: Path, rel_path: str):
    """Analyse légère: extrait les imports, définitions clés et rôle."""
    full_path = cwd / rel_path
    ext = full_path.suffix.lower()
    name = full_path.name.lower()
    
    role = "code"
    if "test" in rel_path.lower() or "spec" in rel_path.lower():
        role = "test"
    elif name in ["readme.md", "license", "contributing.md", "changelog.md"] or ext in [".md", ".txt"]:
        role = "documentation"
    elif name.startswith(".env") or ext in [".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".env"]:
        role = "configuration"
    elif ext in [".sh", ".bash", ".zsh"]:
        role = "script/cli"

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

    return {
        "path": rel_path,
        "role": role,
        "symbols": symbols[:5],
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

def call_ollama(prompt_content: str, model="qwen2.5-coder:1.5b", base_url="http://localhost:11434"):
    """Appelle Ollama avec sortie JSON contrainte."""
    url = f"{base_url}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are an expert Git commit architect.\n"
                    "Group the given project files into a logical, coherent sequence of 3 to 7 Conventional Commits.\n"
                    "Rules:\n"
                    "1. Order commits chronologically by development lifecycle:\n"
                    "   - Setup & Configuration (chore/build)\n"
                    "   - Core libraries, data models or foundations (feat/refactor)\n"
                    "   - Features, services, CLI or entrypoints (feat)\n"
                    "   - Tests, documentation and samples (test/docs)\n"
                    "2. Group coupled or interdependent files together in the same commit.\n"
                    "3. Write a UNIQUE and meaningful Conventional Commit message for each commit based on its specific files:\n"
                    "   Format: <type>(<scope>): <summary>\\n\\n<body explaining rationale>\n"
                    "   Example scopes: (config), (core), (cli), (runner), (docs), (test).\n"
                    "4. Assign each given file into the most appropriate commit.\n"
                    "5. Output strictly a JSON object with this exact structure:\n"
                    "{\n"
                    '  "commits": [\n'
                    '    {"message": "<type>(<scope>): <summary>\\n\\n<rationale>", "files": ["<filename>"]}\n'
                    "  ]\n"
                    "}"
                )
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
            "temperature": 0.2,
            "num_ctx": 2048,
            "num_predict": 700
        }
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
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

    # Prompt compact (économise tokens et énergie)
    prompt_lines = ["Files to organize into coherent commits:"]
    for fa in analyses:
        desc = f"- {fa['path']} [{fa['role']}]"
        if fa.get("symbols"):
            desc += f" (defines: {', '.join(fa['symbols'])})"
        if fa.get("links_to"):
            desc += f" (links: {', '.join(fa['links_to'])})"
        prompt_lines.append(desc)

    prompt = "\n".join(prompt_lines)
    print(f"\033[0;34m[INFO]\033[0m Inférence via SLM sobre '{args.model}'...")
    res = call_ollama(prompt, model=args.model)

    raw_commits = res.get("commits", [])
    if not raw_commits:
        print("\033[0;31m[ERROR]\033[0m Le modèle n'a renvoyé aucun commit.", file=sys.stderr)
        sys.exit(1)

    # Nettoyage, déduplication et réconciliation
    commits = reconcile_and_clean_commits(raw_commits, files, cwd)

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
