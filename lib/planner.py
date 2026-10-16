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
    """Retourne la liste des fichiers modifiés ou non suivis selon git status (y compris dans les sous-dossiers)."""
    try:
        # -uall garantit que les fichiers dans les sous-dossiers non suivis sont tous listés individuellement
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
                p = cwd / path_clean
                if p.name in DEFAULT_IGNORES or p.name == ".DS_Store" or path_clean == "commit-plan.json" or path_clean.startswith(".git"):
                    continue
                if p.is_file():
                    files.append(str(p.relative_to(cwd)))
                elif p.is_dir():
                    # Sécurité : si une entrée est un dossier, parcourir récursivement
                    for root, _, filenames in os.walk(p):
                        for fn in filenames:
                            if fn in DEFAULT_IGNORES or fn == ".DS_Store":
                                continue
                            sub_p = Path(root) / fn
                            if is_text_file(sub_p):
                                files.append(str(sub_p.relative_to(cwd)))
        return files
    except Exception:
        return []

def scan_directory(cwd: Path, all_files=False):
    """Scanne le dossier courant et sélectionne les fichiers pertinents dans toute l'arborescence."""
    if not all_files:
        git_files = get_git_status_files(cwd)
        if git_files:
            return sorted(set(git_files))

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

    # 2. Pour les nouveaux fichiers ou sans diff : extraire docstrings ou commentaires de tête
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
    
    return "core implementation"

def analyze_file(cwd: Path, rel_path: str):
    """Analyse légère: extrait les imports, définitions clés, rôle et intention sémantique."""
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

    intent = extract_file_intent(cwd, rel_path)

    return {
        "path": rel_path,
        "role": role,
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
        "You are a senior tech lead and Git commit architect.\n"
        "Your task is to organize the numbered items into 3 to 8 logical, coherent Conventional Commits by their integer IDs in '" + id_key + "'.\n\n"
        "CRITICAL COMMIT MESSAGE RULES:\n"
        "1. Every ID from 1 to N MUST be included in exactly one commit in '" + id_key + "'.\n"
        "2. NEVER mention filenames, file extensions, or raw file paths in the commit message or scope.\n"
        "   - FORBIDDEN: 'feat(lib/planner.py): add planner.py'\n"
        "   - FORBIDDEN: 'feat(auth): add AuthService.php'\n"
        "3. The <scope> MUST be a conceptual domain (e.g. auth, api, cli, formalites, consultation, config, docs, core).\n"
        "4. The <summary> MUST describe the functional ACTION and INTENT in imperative mood:\n"
        "   - EXAMPLE: 'feat(auth): add Google OAuth method to registration flow'\n"
        "   - EXAMPLE: 'feat(api): add business formality write endpoints for companies'\n"
        "   - EXAMPLE: 'fix(scanner): support recursive subdirectory scanning in git status'\n"
        "5. Output strictly a JSON object matching this schema:\n"
        "{\n"
        '  "commits": [\n'
        '    {"message": "<type>(<scope>): <action summary>\\n\\n<short rationale>", "' + id_key + '": ' + example_id + '}\n'
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

def sanitize_commit_message(msg: str) -> str:
    """Nettoie le message pour retirer tout nom de fichier ou extension résiduel du scope."""
    def clean_scope(m):
        type_part = m.group(1).lower()
        raw_scope = m.group(2).strip()
        rest = m.group(3)
        scope_name = Path(raw_scope).stem
        if "/" in scope_name or "\\" in scope_name:
            scope_name = Path(scope_name).name
        # Retirer les préfixes numériques de tri (ex: 01_formalites -> formalites)
        scope_clean = re.sub(r'^[0-9]+[_\-]*', '', scope_name)
        scope_clean = re.sub(r'[^a-zA-Z0-9_\-]', '', scope_clean).lower()
        if not scope_clean:
            scope_clean = "core"
        return f"{type_part}({scope_clean}):{rest}"

    cleaned = re.sub(r'^([a-zA-Z]+)\(([^)]+)\):(.*)', clean_scope, msg.strip())
    return cleaned

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
            c["message"] = sanitize_commit_message(c.get("message", "feat(core): update files"))
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
                parent_dir = str(p.parent)
                groups[parent_dir].append(f)
            else:
                groups["root"].append(f)

        prompt_lines = ["Modules to organize into 3 to 8 logical commits:"]
        for idx, (dir_path, g_files) in enumerate(groups.items(), 1):
            id_map[idx] = g_files
            scope_name = Path(dir_path).name.lower().replace("-", "_") if dir_path != "root" else "core"
            scope_clean = re.sub(r'[^a-zA-Z0-9_\-]', '', scope_name) or "module"
            sample_intents = [analyses_dict[gf]["intent"] for gf in g_files[:2] if gf in analyses_dict]
            summary = " | ".join([s for s in sample_intents if s])[:120]
            prompt_lines.append(f"- Module [{idx}] '{scope_clean}': {len(g_files)} file(s) in {dir_path} ({summary})")
    else:
        prompt_lines = ["Files to organize into logical commits:"]
        for idx, fa in enumerate(analyses, 1):
            id_map[idx] = [fa["path"]]
            desc = f"[{idx}] {fa['path']} [{fa['role']}]: {fa['intent']}"
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
