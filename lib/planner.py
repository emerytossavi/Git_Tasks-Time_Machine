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
    ".gtm",
    ".DS_Store",
    "commit-plan.json"
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf",
    ".zip", ".tar", ".gz", ".7z", ".exe", ".bin", ".dylib", ".so", ".a",
    ".mp3", ".mp4", ".mov", ".avi", ".woff", ".woff2", ".ttf", ".eot"
}

def is_system_excluded(rel_path: str, cwd: Path = None) -> bool:
    """Vérifie si un chemin fait partie des exclusions système indispensables (.git, .gtm, commit-plan.json, .DS_Store)."""
    p = Path(rel_path)
    if any(part in (".git", ".gtm") for part in p.parts):
        return True
    if p.name == ".DS_Store":
        return True
    if p.name == "commit-plan.json":
        # Si commit-plan.json était suivi dans Git et a été supprimé, sa suppression doit être prise en compte
        if cwd and is_git_deleted(cwd, rel_path):
            return False
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

def is_git_deleted(cwd: Path, rel_path: str) -> bool:
    """Vérifie si un fichier est supprimé mais suivi dans Git (working tree ou staging)."""
    try:
        cmd = ["git", "status", "--porcelain", "--", rel_path]
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.splitlines():
                if "D" in line[:2]:
                    return True
        cmd_ls = ["git", "ls-files", "--error-unmatch", "--", rel_path]
        res_ls = subprocess.run(cmd_ls, cwd=str(cwd), capture_output=True, text=True)
        return res_ls.returncode == 0
    except Exception:
        return False

def get_git_status_files(cwd: Path):
    """Retourne la liste des fichiers modifiés, supprimés ou non suivis selon git status (y compris dans les sous-dossiers)."""
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
                status_code = parts[0]
                path_str = parts[1]
                if " -> " in path_str:
                    path_str = path_str.split(" -> ")[1]
                path_clean = path_str.strip('"')
                if is_system_excluded(path_clean, cwd=cwd):
                    continue
                p = cwd / path_clean
                if p.is_file() and p.stat().st_size < 50 * 1024 * 1024:
                    files.append(str(p.relative_to(cwd)))
                elif not p.exists() and "D" in status_code:
                    files.append(path_clean)
                elif p.is_dir():
                    # Sécurité : si une entrée non suivie est un dossier brut
                    for root, _, filenames in os.walk(p):
                        for fn in filenames:
                            sub_p = Path(root) / fn
                            rel_sub = str(sub_p.relative_to(cwd))
                            if not is_system_excluded(rel_sub, cwd=cwd) and sub_p.is_file() and sub_p.stat().st_size < 50 * 1024 * 1024:
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
            if not line or is_system_excluded(line, cwd=cwd):
                continue
            p = cwd / line
            if p.is_file() and p.stat().st_size < 50 * 1024 * 1024:
                files.append(line)
            elif not p.exists() and is_git_deleted(cwd, line):
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
        dirs[:] = [d for d in dirs if not is_system_excluded(d, cwd=cwd) and not matches_gitignore(d, patterns)]
        for f in files:
            p = Path(root) / f
            rel_p = str(p.relative_to(cwd))
            if is_system_excluded(rel_p, cwd=cwd) or matches_gitignore(rel_p, patterns):
                continue
            if p.is_file() and p.stat().st_size < 50 * 1024 * 1024:
                selected.append(rel_p)

    return sorted(set(selected))

def clean_scope_name(raw_name: str) -> str:
    """Normalise un nom de scope pour Conventional Commits (minuscules, sans préfixes numériques ni caractères spéciaux)."""
    name = (raw_name or "").lower().strip()
    name = re.sub(r'^[0-9]+[_\-]*', '', name)
    name = name.replace("_", "-")
    name = re.sub(r'[^a-z0-9\-]', '', name)
    if not name:
        return "core"
    
    if "formalite" in name:
        return "formalites"
    if "registre" in name:
        return "registre"
    if "credit-mobilier" in name or "creditmobilier" in name:
        return "credit-mobilier"
    if "surete" in name:
        return "surete"
    if "template" in name or "archive" in name:
        return "templates"
    if "environ" in name:
        return "env"
    if "docker" in name:
        return "docker"
    if "doc" in name or "guide" in name:
        return "docs"
    if "ohada" in name or "rccm" in name:
        return "api"
    
    parts = [p for p in name.split("-") if p not in ("consultation", "sample", "packages", "service", "services", "api")]
    if parts:
        return "-".join(parts[:2])
    return name or "core"

def extract_file_intent(cwd: Path, rel_path: str, target_lang: str = "en"):
    """
    Extrait l'intention métier et technique réelle du fichier.
    Retourne un tuple: (summary, details)
    - summary: phrase concise (1 ligne) pour le prompt du SLM
    - details: détails techniques concrets (endpoints, méthodes, schémas, fonctions) pour le corps du commit
    """
    full_path = cwd / rel_path
    name_lower = full_path.name.lower()
    ext_lower = full_path.suffix.lower()
    rel_lower = rel_path.lower()
    is_fr = (target_lang or "").lower().startswith("fr")
    is_es = (target_lang or "").lower().startswith("es")

    # 0. Fichier supprimé (absent du disque mais présent dans git)
    if not full_path.exists():
        stem_clean = Path(rel_path).stem.replace("_", " ").replace("-", " ")
        removed_symbols = []
        try:
            cmd = ["git", "diff", "HEAD", "-U0", "--no-color", "--", rel_path]
            res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
            if not res.stdout:
                cmd = ["git", "diff", "--cached", "-U0", "--no-color", "--", rel_path]
                res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
            if res.stdout:
                for l in res.stdout.splitlines():
                    if l.startswith("-") and not l.startswith("---"):
                        m = re.search(r'(?:def|class|function|async def)\s+([a-zA-Z0-9_]+)', l[1:])
                        if m and m.group(1) not in removed_symbols:
                            removed_symbols.append(m.group(1))
        except Exception:
            pass

        if removed_symbols:
            sym_str = ", ".join(removed_symbols[:3])
            sym_all = ", ".join(removed_symbols[:5])
            if is_fr:
                return f"supprimer {sym_str}", f"suppression de {sym_all} ({rel_path})"
            elif is_es:
                return f"eliminar {sym_str}", f"eliminación de {sym_all} ({rel_path})"
            else:
                return f"remove {sym_str}", f"remove {sym_all} ({rel_path})"

        if is_fr:
            return f"supprimer {stem_clean}", f"suppression de {rel_path}"
        elif is_es:
            return f"eliminar {stem_clean}", f"eliminación de {rel_path}"
        else:
            return f"remove {stem_clean}", f"remove {rel_path}"

    # 1. Fichiers binaires & archives d'exemple
    if ext_lower in BINARY_EXTENSIONS or ext_lower in (".zip", ".tar", ".gz", ".7z", ".pdf", ".png", ".jpg", ".jpeg", ".ico", ".svg"):
        stem_clean = full_path.stem.replace("_", " ").replace("-", " ")
        if ext_lower == ".pdf":
            if is_fr:
                return f"document justificatif ({stem_clean})", f"pièce jointe document PDF : {stem_clean}"
            elif is_es:
                return f"documento justificativo ({stem_clean})", f"adjunto documento PDF: {stem_clean}"
            return f"sample supporting document ({stem_clean})", f"PDF document attachment: {stem_clean}"
        elif ext_lower in (".zip", ".tar", ".gz", ".7z"):
            if is_fr:
                return "archive d'exemples et pièces jointes", "archive de fichiers compressés ZIP"
            elif is_es:
                return "archivo de ejemplos y adjuntos", "archivo de archivos comprimidos ZIP"
            return "sample archive package containing xmldb.xml and attachments", "compressed ZIP package archive"
        else:
            if is_fr:
                return f"ressource graphique ({stem_clean})", f"élément image : {stem_clean}"
            elif is_es:
                return f"recurso gráfico ({stem_clean})", f"elemento de imagen: {stem_clean}"
            return f"graphical asset ({stem_clean})", f"image asset: {stem_clean}"

    # 2. Si le fichier est suivi et modifié, extraire du git diff
    try:
        cmd = ["git", "diff", "-U0", "--no-color", "--", rel_path]
        res = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if res.stdout:
            added = []
            for l in res.stdout.splitlines():
                if l.startswith("+") and not l.startswith("+++"):
                    clean = l[1:].strip()
                    if len(clean) > 4 and clean not in ("{", "}", ");", "];", "end"):
                        added.append(clean)
            if added:
                symbols_added = []
                for l in added:
                    m = re.search(r'(?:def|class|function|async def)\s+([a-zA-Z0-9_]+)', l)
                    if m and m.group(1) not in symbols_added:
                        symbols_added.append(m.group(1))
                if symbols_added:
                    if is_fr:
                        summary = f"mettre à jour la logique de {', '.join(symbols_added[:3])}"
                        details = f"mise à jour de la logique pour {', '.join(symbols_added[:5])}"
                    elif is_es:
                        summary = f"actualizar la lógica de {', '.join(symbols_added[:3])}"
                        details = f"actualización de lógica para {', '.join(symbols_added[:5])}"
                    else:
                        summary = f"update {', '.join(symbols_added[:3])} logic"
                        details = f"update logic for {', '.join(symbols_added[:5])}"
                else:
                    meaningful = [l for l in added if any(l.startswith(x) for x in ("#", "//", "/*", "*", "def ", "class ", "function ", "export ", "public ", "const ", "router.", "app."))]
                    diff_summary = meaningful if meaningful else added
                    clean_diff = [re.sub(r'^[#/\*\s]+', '', x).strip() for x in diff_summary if x.strip()]
                    stem_name = Path(rel_path).stem
                    if is_fr:
                        summary = f"mettre à jour {stem_name}"
                        details = "modifications apportées : " + " ; ".join(clean_diff[:4])
                    elif is_es:
                        summary = f"actualizar {stem_name}"
                        details = "cambios realizados: " + " ; ".join(clean_diff[:4])
                    else:
                        summary = f"update {stem_name} implementation"
                        details = "diff changes: " + " ; ".join(clean_diff[:4])
                return summary[:120], details[:200]
    except Exception:
        pass

    # 3. Fichiers de configuration / containerisation / docs clés
    if name_lower == ".dockerignore":
        if is_fr:
            return "définir les exclusions de contexte pour l'image conteneur", "exclusions de build pour le packaging conteneur"
        elif is_es:
            return "definir exclusiones de contexto para la imagen de contenedor", "exclusiones de compilación para contenedor"
        return "define build context exclusions for container packaging", "container packaging build context exclusions"
    elif "entrypoint" in name_lower or (ext_lower in (".sh", ".bash") and "docker" in rel_lower):
        if is_fr:
            return "gérer le démarrage et l'initialisation du runtime conteneur", "initialisation et point d'entrée du conteneur"
        elif is_es:
            return "gestionar inicio e inicialización del entorno de contenedor", "inicialización y punto de entrada de contenedor"
        return "manage container runtime startup and initialization", "container runtime entrypoint initialization"
    elif name_lower.startswith("dockerfile"):
        if is_fr:
            return "configurer l'environnement de build et l'image conteneur", "environnement de compilation conteneur Docker"
        elif is_es:
            return "configurar entorno de compilación e imagen de contenedor", "entorno de compilación multi-etapa Docker"
        return "configure container build environment and runtime image", "multi-stage Docker build environment"
    elif name_lower.startswith("docker-compose"):
        if is_fr:
            return "orchestrer les services multi-conteneurs et l'environnement réseau", "configuration des services multi-conteneurs"
        elif is_es:
            return "orquestar servicios multi-contenedor y entorno de red", "configuración de servicios multi-contenedor"
        return "orchestrate multi-container services and network environment", "multi-container services configuration"
    elif name_lower == ".gitignore":
        if is_fr:
            return "configurer les règles d'exclusion de fichiers pour git", "règles d'exclusion et de masquage git"
        elif is_es:
            return "configurar reglas de exclusión de archivos para git", "reglas de exclusión e ignorado git"
        return "configure repository ignore rules for untracked files", "git exclusions and ignore rules"
    elif name_lower in ("readme.md", "readme"):
        if is_fr:
            return "documenter l'architecture du projet, l'API et les guides d'utilisation", "vue d'ensemble, architecture et documentation d'utilisation"
        elif is_es:
            return "documentar arquitectura del proyecto, API y guías de uso", "visión general, arquitectura y directrices de uso"
        return "document project architecture, API structure and usage guides", "project overview, architecture and usage guidelines"
    elif name_lower in ("license", "license.md"):
        if is_fr:
            return "définir les termes de licence et conditions de distribution", "termes de licence logicielle"
        elif is_es:
            return "definir términos de licencia y condiciones de distribución", "términos de licencia de software"
        return "define software license terms and distribution conditions", "software licensing terms"
    elif "guide" in name_lower:
        if is_fr:
            return "fournir le guide de référence technique et spécifications", "guide de référence technique et spécifications"
        elif is_es:
            return "proporcionar guía de referencia técnica y especificaciones", "guía de referencia técnica y especificaciones"
        return "provide technical webservices reference guide and specifications", "technical reference guide and specifications"

    # Lecture du contenu
    content = ""
    try:
        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(16384)
    except Exception:
        pass

    # 4. Fichiers Bruno API (.bru)
    if ext_lower == ".bru":
        if name_lower == "folder.bru":
            m_name = re.search(r'name:\s*([^\n\r}]+)', content)
            fname = m_name.group(1).strip() if m_name else full_path.parent.name
            return f"configure folder sequence and metadata for {fname}", f"folder order and metadata: {fname}"
        if name_lower == "collection.bru":
            return "configure Bruno API collection root settings and auth", "collection root configuration and authentication"
        if "environments" in rel_lower:
            vars_found = [v.strip() for v in re.findall(r'([a-zA-Z0-9_]+):', content)]
            vars_clean = [v for v in vars_found if v not in ("vars", "https", "http")]
            return f"configure environment variables ({', '.join(vars_clean[:4])})", f"environment variables: {', '.join(vars_clean[:6])}"

        m_method = re.search(r'^(get|post|put|delete|patch|head|options)\s*\{', content, re.M | re.I)
        m_url = re.search(r'url:\s*([^\n\r]+)', content)
        m_docs = re.search(r'docs\s*\{([^}]+)\}', content)
        
        method = m_method.group(1).upper() if m_method else "REQ"
        raw_url = m_url.group(1).strip() if m_url else ""
        clean_url = re.sub(r'\{\{[^}]+\}\}', '', raw_url).strip()
        if not clean_url:
            clean_url = raw_url
        clean_url = clean_url.split("?")[0]

        doc_summary = ""
        doc_details = []
        if m_docs:
            for l in m_docs.group(1).splitlines():
                cl = l.strip().lstrip('#-* `')
                if cl:
                    doc_details.append(cl)
            if doc_details:
                doc_summary = doc_details[0]

        summary = f"{method} {clean_url}"
        if doc_summary:
            clean_doc = re.sub(r'^(?:Formalité|Consultation)\s*:\s*', '', doc_summary, flags=re.I)
            summary += f" ({clean_doc})"
        
        detail_parts = [f"{method} {clean_url}"]
        if doc_details:
            detail_parts.extend(doc_details[:2])
        return summary, " - ".join(detail_parts)

    # 5. Fichiers XML (.xml)
    if ext_lower == ".xml":
        proc = re.search(r'<refProcess>([^<]+)</refProcess>', content)
        comp = re.search(r'<companyName>([^<]+)</companyName>', content)
        nature = re.search(r'<nature>([^<]+)</nature>', content)
        desc_prop = re.search(r'<descProperty>([^<]+)</descProperty>', content)
        act = re.search(r'<(?:otherTypeActivity|prsTypeActivity)>([^<]+)<', content)

        ref_proc = proc.group(1).strip() if proc else "data"
        desc_parts = []
        if comp: desc_parts.append(comp.group(1).strip())
        if nature: desc_parts.append(nature.group(1).strip())
        if desc_prop: desc_parts.append(desc_prop.group(1).strip())

        extra = " - " + ", ".join(desc_parts) if desc_parts else ""
        summary = f"XML dossier payload for {ref_proc}{extra}"
        
        detail_items = [f"process: {ref_proc}"]
        if comp: detail_items.append(f"company: {comp.group(1).strip()}")
        if act: detail_items.append(f"activity: {act.group(1).strip()}")
        if nature: detail_items.append(f"nature: {nature.group(1).strip()}")
        return summary, ", ".join(detail_items)

    # 6. Fichiers JSON (.json)
    if ext_lower == ".json":
        if name_lower == "bruno.json":
            try:
                bj = json.loads(content)
                return f"define Bruno collection ({bj.get('name', 'API')})", f"collection configuration: {bj.get('name', 'API')}"
            except Exception:
                return "define Bruno collection configuration", "collection configuration"
        elif name_lower == "package.json":
            try:
                pj = json.loads(content)
                return f"define npm package configuration ({pj.get('name', 'app')})", f"package metadata: {pj.get('name', 'app')}"
            except Exception:
                return "define npm package configuration", "package metadata"

    # 7. Code source (Python, JS/TS, Go, Java, Shell, etc.)
    routes = []
    symbols = []
    docstrings = []

    m_routes = re.findall(r'@(?:app|router|bp)\.(?:get|post|put|delete|patch)\([\'"]([^\'"]+)', content)
    if not m_routes:
        m_routes = re.findall(r'(?:app|router)\.(?:get|post|put|delete|patch)\([\'"]([^\'"]+)', content)
    if not m_routes:
        m_routes = re.findall(r'@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|RequestMapping)\([\'"]?([^\'"]+)', content)
    routes.extend(m_routes)

    m_sym = re.findall(r'(?:class|def|async def|function|func|public class|interface|struct)\s+([a-zA-Z0-9_]+)', content)
    symbols.extend(m_sym)

    m_doc = re.search(r'"""([^"]+)"""', content)
    if m_doc:
        doc_first = [l.strip() for l in m_doc.group(1).splitlines() if l.strip()]
        if doc_first:
            docstrings.append(doc_first[0])
    if not docstrings:
        comment_lines = []
        for line in content.splitlines()[:25]:
            l_s = line.strip()
            if l_s.startswith(("#", "//")) and not l_s.startswith(("#!", "# -*-", "// eslint")):
                clean_c = l_s.lstrip("#/ *").strip()
                if len(clean_c) > 10:
                    comment_lines.append(clean_c)
        if comment_lines:
            docstrings.append(comment_lines[0])

    if routes:
        if is_fr:
            summary = f"implémenter les points d'accès API ({', '.join(routes[:3])})"
            details = f"routes : {', '.join(routes[:4])}, gestionnaires : {', '.join(symbols[:3])}"
        elif is_es:
            summary = f"implementar endpoints de API ({', '.join(routes[:3])})"
            details = f"rutas: {', '.join(routes[:4])}, controladores: {', '.join(symbols[:3])}"
        else:
            summary = f"implement API endpoints ({', '.join(routes[:3])})"
            details = f"routes: {', '.join(routes[:4])}, handlers: {', '.join(symbols[:3])}"
        return summary, details
    elif docstrings and len(docstrings[0]) > 15:
        summary = docstrings[0][:100]
        label_imp = "implémente" if is_fr else ("implementa" if is_es else "implements")
        details = f"{docstrings[0]} ({label_imp} {', '.join(symbols[:4])})" if symbols else docstrings[0]
        return summary, details
    elif symbols:
        if is_fr:
            summary = f"implémenter {', '.join(symbols[:3])}"
            details = f"implémente {', '.join(symbols[:5])}"
        elif is_es:
            summary = f"implementar {', '.join(symbols[:3])}"
            details = f"implementa {', '.join(symbols[:5])}"
        else:
            summary = f"implement {', '.join(symbols[:3])}"
            details = f"implements {', '.join(symbols[:5])}"
        return summary, details

    stem_clean = full_path.stem.replace("_", " ").replace("-", " ")
    if is_fr:
        return f"implémenter les fonctionnalités de {stem_clean}", f"logique et configuration pour {stem_clean}"
    elif is_es:
        return f"implementar las funcionalidades de {stem_clean}", f"lógica y configuración para {stem_clean}"
    return f"implement {stem_clean} functionality", f"logic and configuration for {stem_clean}"

def categorize_file(rel_path: str, is_deleted: bool = False):
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
    if name in ["readme.md", "license", "contributing.md", "changelog.md"] or ext in [".md", ".txt"] or rel_lower.startswith("docs/"):
        return {"type": "docs", "scope": "docs", "category": "docs"}
    if "test" in rel_lower or "spec" in rel_lower:
        return {"type": "test", "scope": "test", "category": "test"}
    if "environment" in rel_lower or name.startswith(".env"):
        return {"type": "chore", "scope": "env", "category": "env"}
    if "template" in rel_lower or "sample" in rel_lower:
        return {"type": "chore", "scope": "templates", "category": "templates"}
    if ext in [".json", ".yaml", ".yml", ".toml", ".ini", ".conf"]:
        return {"type": "chore", "scope": "config", "category": "config"}
    if ext in [".sh", ".bash", ".zsh"]:
        return {"type": "chore", "scope": "cli" if "gtm" in rel_lower or "cli" in rel_lower else "scripts", "category": "scripts"}
    
    # Code applicatif : déduire le scope du répertoire ou du fichier
    if len(p.parts) > 1:
        dir_cand = p.parts[-2] if len(p.parts) > 2 else p.parts[0]
        scope = clean_scope_name(dir_cand)
    else:
        scope = clean_scope_name(p.stem)

    if is_deleted:
        return {"type": "refactor", "scope": scope, "category": scope}

    return {"type": "feat", "scope": scope, "category": scope}

def analyze_file(cwd: Path, rel_path: str, target_lang: str = "en"):
    """Analyse légère: extrait les imports, définitions clés, rôle et intention sémantique profonde."""
    full_path = cwd / rel_path
    is_deleted = not full_path.exists() and is_git_deleted(cwd, rel_path)
    cat = categorize_file(rel_path, is_deleted=is_deleted)

    symbols = []
    imports = []

    if full_path.suffix.lower() not in BINARY_EXTENSIONS:
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = [f.readline() for _ in range(80)]

            for line in lines:
                line_s = line.strip()
                m_imp = re.search(r'(?:import|from|require|use|source|\.)\s+["\']?([a-zA-Z0-9_\-\./]+)', line_s)
                if m_imp:
                    imp = m_imp.group(1).replace('"', '').replace("'", "")
                    imports.append(imp)
                m_def = re.search(r'(?:class|def|function|interface|type|struct|enum)\s+([a-zA-Z0-9_]+)', line_s)
                if m_def:
                    symbols.append(m_def.group(1))
        except Exception:
            pass

    summary, details = extract_file_intent(cwd, rel_path, target_lang=target_lang)

    return {
        "path": rel_path,
        "type": cat["type"],
        "scope": cat["scope"],
        "category": cat["category"],
        "role": cat["type"],
        "intent": summary,
        "details": details,
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

SUPPORTED_LANGUAGES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic"
}

def get_language_name(lang_code: str) -> str:
    code = (lang_code or "en").strip().lower()
    return SUPPORTED_LANGUAGES.get(code, code)

def get_configured_default_lang() -> str:
    """Récupère la langue configurée dans l'environnement (DEFAULT_LANG) ou dans config.env (défaut: 'en')."""
    env_lang = os.environ.get("DEFAULT_LANG", "").strip().lower()
    if env_lang:
        return env_lang

    config_path = Path(__file__).resolve().parent.parent / "config.env"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEFAULT_LANG="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'").lower()
                        if val:
                            return val
        except Exception:
            pass

    return "en"

def call_ollama(prompt_content: str, is_modular=False, model="qwen2.5-coder:1.5b", base_url=None, target_lang="en"):
    """Appelle Ollama avec sortie JSON contrainte, types standards et langue configurée."""
    base_url = (base_url or get_configured_ollama_host()).rstrip("/")
    url = f"{base_url}/api/chat"

    id_key = "module_ids" if is_modular else "file_ids"
    example_id = "[1, 2]" if is_modular else "[1, 2]"
    lang_name = get_language_name(target_lang)
    is_fr = (target_lang or "").lower().startswith("fr")
    is_es = (target_lang or "").lower().startswith("es")

    if is_fr:
        system_prompt = (
            "Tu es un architecte expert en commits Git respectant strictement Conventional Commits v1.0.0 et @commitlint/config-conventional.\n"
            f"Ta mission est d'organiser les éléments numérotés en commits atomiques et logiques en utilisant leurs identifiants entiers dans '{id_key}'.\n\n"
            "RÈGLES CRITIQUES CONVENTIONAL COMMITS & LANGUE :\n"
            f"1. Chaque identifiant de 1 à N doit obligatoirement figurer dans exactement un commit dans '{id_key}'.\n"
            "2. MOTS-CLÉS DE TYPE (type-enum) : restent OBLIGATOIREMENT en anglais standard minuscules selon la norme universelle :\n"
            "   'feat', 'fix', 'build', 'ci', 'docs', 'refactor', 'test', 'chore', 'perf', 'style', 'revert'.\n"
            "   NE JAMAIS traduire le mot-clé de type lui-même (ex: NE PAS écrire 'fonctionnalité' ou 'correction').\n"
            "3. LANGUE STRICTE DU MESSAGE : Le résumé (subject) et la description (body) doivent être rédigés STRICTEMENT EN FRANÇAIS.\n"
            "   AUCUN mélange linguistique (aucun mot ou phrase en anglais dans le sujet/corps sauf noms propres/fichiers). Rédige des phrases claires et naturelles en français.\n"
            "4. SCOPE (scope-case) : En minuscules (ex: docker, auth, api, cli, config, env, templates).\n"
            "   TAUTOLOGIE STRICTEMENT INTERDITE : Ne JAMAIS répéter le nom du type dans le scope (ex: INTERDIT 'test(test):', 'docs(docs):', 'chore(chore):'). Omettre le scope ou utiliser le nom du module.\n"
            "5. COHÉRENCE ATOMIQUE : Regroupe les fichiers complémentaires d'une même fonctionnalité dans un commit unique.\n"
            "6. RÈGLES DE L'EN-TÊTE : Format '<type>(<scope>): <sujet>'\n"
            "   - Doit impérativement commencer par un verbe impératif en minuscules en français (ex: ajouter, configurer, implémenter, mettre à jour, supprimer, corriger, documenter).\n"
            "   - Ne doit PAS se terminer par un point.\n"
            "   - STRICTEMENT INTERDIT : Ne JAMAIS écrire 'ajouter <nom_fichier>' ni répéter les extensions de fichier.\n"
            "   - STRICTEMENT INTERDIT : Ne JAMAIS inclure de numérotations brutes de sections markdown (ex: 'ajouter 1. L\'Essence...' -> écrire 'documenter la vision et les objectifs du projet').\n"
            "   - STRICTEMENT INTERDIT : Pas de méthodes HTTP brutes (GET, POST) ou d'URL brutes dans l'en-tête.\n"
            "7. CORPS (body) : OBLIGATOIRE. Expliquer concrètement et techniquement en français ce qui a été réalisé sans répéter bêtement la liste des fichiers.\n"
            "8. Sortie JSON stricte au format suivant :\n"
            "{\n"
            '  "commits": [\n'
            '    {\n'
            '      "subject": "<type>(<scope>): <résumé impératif en français>",\n'
            '      "body": "<description technique détaillée en français>",\n'
            f'      "{id_key}": {example_id}\n'
            '    }\n'
            '  ]\n'
            "}"
        )
    elif is_es:
        system_prompt = (
            "Eres un arquitecto experto en commits de Git que cumple estrictamente con las reglas de Conventional Commits v1.0.0.\n"
            f"Tu tarea es organizar los elementos numerados en commits atómicos y lógicos usando sus identificadores enteros en '{id_key}'.\n\n"
            "REGLAS CRÍTICAS:\n"
            f"1. Cada identificador de 1 a N debe incluirse exactamente en un commit en '{id_key}'.\n"
            "2. PALABRAS CLAVE DE TIPO : Deben permanecer OBLIGATORIAMENTE en inglés en minúsculas (feat, fix, docs, chore, test, refactor, build, ci).\n"
            "3. IDIOMA DEL MENSAJE : El resumen (subject) y la descripción (body) deben redactarse ESTRICTAMENTE EN ESPAÑOL imperativo.\n"
            "   SIN mezcla de idiomas (no spanglish). Redacta frases claras y naturales en español.\n"
            "4. SCOPE : En minúsculas. NUNCA repetir el tipo en el scope (prohibido 'test(test):', 'docs(docs):').\n"
            "5. COHERENCIA ATÓMICA : Agrupa los archivos complementarios de una misma función en un único commit.\n"
            "6. FORMATO DEL ENCABEZADO : '<type>(<scope>): <resumen en español>'\n"
            "   - Debe comenzar con un verbo imperativo en minúsculas en español (ej: agregar, configurar, implementar, actualizar, corregir, documentar).\n"
            "   - No debe terminar con un punto.\n"
            "   - NUNCA incluir números brutos de secciones de markdown ni nombres de archivos.\n"
            "7. CUERPO (body) : OBLIGATORIO. Explicar en español técnicamente qué se implementó.\n"
            "8. Salida JSON estricta:\n"
            "{\n"
            '  "commits": [\n'
            '    {\n'
            '      "subject": "<type>(<scope>): <resumen imperativo en español>",\n'
            '      "body": "<descripción técnica en español>",\n'
            f'      "{id_key}": {example_id}\n'
            '    }\n'
            '  ]\n'
            "}"
        )
    else:
        system_prompt = (
            "You are an expert Git commit architect adhering strictly to Conventional Commits v1.0.0 and @commitlint/config-conventional rules.\n"
            "Your task is to organize the numbered items into logical, atomic commits using their integer IDs in '" + id_key + "'.\n\n"
            "CRITICAL CONVENTIONAL COMMITS & LINGUISTIC SPECIFICATIONS:\n"
            "1. Every ID from 1 to N MUST be included in exactly one commit in '" + id_key + "'.\n"
            "2. CONVENTIONAL TYPES (type-enum):\n"
            "   - The type keyword MUST ALWAYS remain in lowercase English according to the Conventional Commits v1.0.0 standard:\n"
            "     'feat', 'fix', 'build', 'ci', 'docs', 'refactor', 'test', 'chore', 'perf', 'style', 'revert'.\n"
            "   - NEVER translate the type keyword itself (e.g. NEVER write 'fonctionnalité', 'correction', or 'documentation').\n"
            "3. STRICT MONOLINGUAL TARGET LANGUAGE:\n"
            f"   - The commit message content (the subject summary after '<type>(<scope>): ' and the 'body' description) MUST be strictly written in {lang_name} ({target_lang}).\n"
            f"   - NEVER mix languages. If any file title, heading, docstring, or comment in the input is in another language, you MUST translate and synthesize it into {lang_name}.\n"
            "4. SCOPES (scope-case):\n"
            "   - MUST be in lower-case (e.g. docker, auth, api, cli, config, env, templates).\n"
            "   - FORBIDDEN SCOPES: NEVER use 'code', 'file', 'files', 'all', or empty/generic scopes.\n"
            "   - FORBIDDEN TAUTOLOGY: NEVER repeat the type name as the scope (e.g. NEVER write 'test(test):', 'docs(docs):', or 'chore(chore):'). Use the specific module name or omit the scope entirely.\n"
            "5. ATOMIC COHERENCE:\n"
            "   - Group all related files that form a single logical unit of work into ONE commit.\n"
            "6. SUBJECT LINE RULES (subject-case, subject-full-stop, imperative-mood):\n"
            "   - Format: '<type>(<scope>): <subject>'\n"
            f"   - MUST start with a LOWER-CASE imperative verb in {lang_name} (e.g. in English: add, configure, setup, implement, update, remove, fix, integrate, support, document).\n"
            "   - MUST NOT end with a period ('.').\n"
            "   - STRICTLY FORBIDDEN: NEVER write 'add <filename>' or repeat file paths/extensions.\n"
            "   - STRICTLY FORBIDDEN: NEVER include raw markdown section numbers in the subject (e.g. NEVER write 'add 1. L\'Essence...' -> write 'document core project vision and goals').\n"
            "   - STRICTLY FORBIDDEN: DO NOT put raw HTTP methods (GET, POST) or raw URLs in the subject line.\n"
            "7. MANDATORY DESCRIPTION / BODY:\n"
            f"   - The 'body' field is MANDATORY. State clearly and concisely in {lang_name} WHAT was done technically without verbatim repetitions of the file list.\n"
            "8. Output strictly a JSON object matching this schema:\n"
            "{\n"
            '  "commits": [\n'
            '    {\n'
            '      "subject": "<type>(<scope>): <concise imperative summary in ' + lang_name + '>",\n'
            '      "body": "<concrete technical description in ' + lang_name + '>",\n'
            '      "' + id_key + '": ' + example_id + '\n'
            '    }\n'
            '  ]\n'
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
            "num_ctx": 8192,
            "num_predict": 2500
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
    if not commits:
        return []
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
    if not commits:
        return []
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
            elif p.parent.exists():
                try:
                    mtimes.append(os.path.getmtime(p.parent))
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

def format_file_label(rel_path: str, all_commit_files: list) -> str:
    """Formate un nom de fichier lisible en désambiguïsant les noms identiques par leur dossier parent."""
    p = Path(rel_path)
    basenames = [Path(f).name for f in all_commit_files]
    if basenames.count(p.name) > 1 and len(p.parts) > 1:
        return f"{p.parts[-2]}/{p.name}"
    return p.name

def sanitize_commit_header(subject: str, commit_files: list = None, target_lang: str = "en") -> str:
    """
    Nettoie et normalise la première ligne de commit selon @commitlint/config-conventional:
    - type-enum : validation parmi les types officiels (en anglais)
    - scope-case : minuscules, suppression des extensions, scopes interdits et scopes tautologiques (ex: test(test))
    - subject-case : première lettre en minuscule
    - subject-full-stop : suppression de tout point final
    - élimination des méthodes HTTP (POST, GET) ou URL brutes dans l'en-tête
    - élimination de l'anti-pattern 'add <fichier>' et des numérotations brutes de sections
    """
    subject = subject.strip()
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
        all_docs = all(any(x in f.lower() for x in ["readme", "license", "contributing", "guide", "doc", "bruno.json", "collection.bru"]) for f in commit_files)
        all_tests = all("test" in f.lower() or "spec" in f.lower() for f in commit_files)
        all_ci = all(".github" in f.lower() or ".gitlab" in f.lower() or "ci" in f.lower() for f in commit_files)
        all_env = all("environment" in f.lower() or Path(f).name.startswith(".env") for f in commit_files)
        all_templates = all("template" in f.lower() or "sample" in f.lower() for f in commit_files)
        all_formalites = all("formalite" in f.lower() for f in commit_files)
        all_registre = all("registre" in f.lower() for f in commit_files)
        all_credit = all("credit-mobilier" in f.lower() or "creditmobilier" in f.lower() for f in commit_files)

        if all_docker:
            type_part, scope_part = "build", "docker"
        elif all_docs:
            type_part, scope_part = "docs", (scope_part if scope_part and scope_part not in ("core", "code", "docs") else "api")
        elif all_env:
            type_part, scope_part = "chore", "env"
        elif all_templates:
            type_part, scope_part = "chore", "templates"
        elif all_formalites:
            type_part, scope_part = "feat", "formalites"
        elif all_registre:
            type_part, scope_part = "feat", "registre"
        elif all_credit:
            type_part, scope_part = "feat", "credit-mobilier"
        elif all_tests:
            type_part, scope_part = "test", (scope_part if scope_part and scope_part != "test" else "")
        elif all_ci:
            type_part, scope_part = "ci", (scope_part if scope_part and scope_part != "ci" else "")

    # Nettoyage du scope (élimination des scopes génériques ou tautologiques ex: test(test))
    if scope_part:
        scope_part = clean_scope_name(scope_part)
        if scope_part in ("code", "file", "files", "all", "project", "repo", "misc") or scope_part == type_part:
            scope_part = ""

    # Nettoyage signatures / update / colonnes
    rest = re.sub(r'^update:\s*(?:def|class|function)?\s*', 'update ', rest, flags=re.I)
    rest = re.sub(r'\([a-zA-Z0-9_,\s:\->\.]*\)[^:]*:', '', rest)
    rest = rest.rstrip(".:,;")
    if " | " in rest:
        rest = rest.split(" | ")[0].strip()

    # Nettoyage des numérotations brutes de sections markdown (ex: 'add 1. L\'Essence...' -> 'add L\'Essence...')
    rest = re.sub(r'^(?:add|ajouter|update|mettre à jour)\s+[0-9]+[\.\-\)]\s*', 'add ', rest, flags=re.I)
    rest = re.sub(r'^[0-9]+[\.\-\)]\s*', '', rest)

    # Nettoyage des méthodes HTTP ou URL dans l'en-tête (doivent aller dans la description/body)
    if re.search(r'\b(?:GET|POST|PUT|DELETE|PATCH)\b', rest, re.I):
        if "creation" in rest.lower() or "formalite" in rest.lower() or scope_part == "formalites":
            rest = "implement writing formalities and registration requests"
        elif "registre" in rest.lower() or scope_part == "registre":
            rest = "implement business registry consultation requests"
        elif "credit" in rest.lower() or "surete" in rest.lower() or scope_part == "credit-mobilier":
            rest = "implement movable credit and security consultation requests"
        else:
            rest = f"implement {scope_part or 'api'} endpoints"

    if scope_part == "templates" and ("configure folder" in rest.lower() or "sample supporting" in rest.lower() or "xml" in rest.lower()):
        rest = "add sample archive packages and XML dossiers"
    elif scope_part in ("docs", "readme", "api", "rccm-ohada") and ("document project architecture" in rest.lower() or "define bruno" in rest.lower()):
        rest = "document API architecture and collection configuration"

    # Si le sujet est trop verbeux ou concatène plusieurs morceaux séparés par des virgules
    if len(rest) > 75 and ", " in rest:
        first_part = rest.split(", ")[0].strip()
        if len(first_part) > 20:
            rest = first_part

    if rest.lower().startswith("xml"):
        rest = "add sample archive packages and XML dossiers"

    # Nettoyage des motifs répétitifs ou mal formulés
    rest = re.sub(r'^(?:add\s+)?implement core functionality', f'implement {scope_part or "module"} resources', rest, flags=re.IGNORECASE)
    rest = re.sub(r'^(?:add\s+)?provide project documentation.*', 'add project documentation and usage overview', rest, flags=re.IGNORECASE)
    rest = re.sub(r'^(?:add\s+)?(?:consultation|formalit[eé])\s*:\s*', '', rest, flags=re.IGNORECASE)

    rest = rest.rstrip(".:,;")
    if rest:
        rest = rest[0].lower() + rest[1:]

    # S'assurer d'avoir un verbe impératif
    valid_verbs_en = r'^(?:add|configure|setup|implement|update|remove|fix|refactor|create|define|integrate|orchestrate|support|document|provide|clean|cleanup)\b'
    valid_verbs_fr = r'^(?:ajouter|configurer|implémenter|mettre à jour|corriger|supprimer|refactoriser|créer|définir|intégrer|orchestrer|supporter|documenter|fournir|nettoyer|tester)\b'
    is_fr = (target_lang or "").lower().startswith("fr")

    if is_fr:
        if not re.match(valid_verbs_fr, rest, re.IGNORECASE) and not re.match(valid_verbs_en, rest, re.IGNORECASE):
            rest = f"ajouter {rest}"
    else:
        if not re.match(valid_verbs_en, rest, re.IGNORECASE):
            rest = f"add {rest}"

    # Correction de l'anti-pattern "add <filename>"
    if commit_files and re.match(r'^(?:add|added|create|created|ajouter|créer)\s+[a-zA-Z0-9_\.\-]+(?:\.[a-zA-Z0-9]+)?$', rest.strip(), re.IGNORECASE):
        if any("docker" in f.lower() for f in commit_files):
            rest = "configure containerization and startup entrypoint" if not is_fr else "configurer la conteneurisation et l'entrypoint"
            type_part, scope_part = "build", "docker"
        elif any(f.endswith(".gitignore") for f in commit_files):
            rest = "configure repository ignore rules" if not is_fr else "configurer les règles d'exclusion gitignore"
            type_part, scope_part = "chore", "git"
        elif any("readme" in f.lower() for f in commit_files):
            rest = "add documentation and usage overview" if not is_fr else "ajouter la documentation générale du projet"
            type_part, scope_part = "docs", "readme"
        elif any("test" in f.lower() for f in commit_files):
            rest = "add automated test cases" if not is_fr else "ajouter des cas de test automatisés"
            type_part, scope_part = "test", ""
        else:
            rest = f"implement {scope_part or 'core'} functionality" if not is_fr else f"implémenter les fonctionnalités {scope_part or 'principales'}"

    if scope_part:
        return f"{type_part}({scope_part}): {rest}"
    else:
        return f"{type_part}: {rest}"

def sanitize_commit_message(msg: str, commit_files: list = None, target_lang: str = "en") -> str:
    """Nettoie l'en-tête et préserve ou assemble le corps du message."""
    msg = msg.strip()
    if "\n\n" in msg:
        parts = msg.split("\n\n", 1)
        subject = parts[0].strip()
        body = parts[1].strip()
    elif "\n" in msg:
        parts = msg.split("\n", 1)
        subject = parts[0].strip()
        body = parts[1].strip()
    else:
        subject = msg
        body = ""

    header = sanitize_commit_header(subject, commit_files, target_lang=target_lang)
    if body:
        return f"{header}\n\n{body}"
    return header

def reconcile_and_clean_commits(commits, all_files, cwd: Path, analyses_dict: dict = None, target_lang: str = "en"):
    """
    Élimine les doublons, filtre les fichiers hors cible, réconcilie les orphelins
    et enrichit automatiquement le corps de commit avec les détails techniques réels.
    """
    target_set = set(all_files)
    assigned_files = set()
    cleaned_commits = []
    is_fr = (target_lang or "").lower().startswith("fr")

    for c in commits:
        filtered_files = []
        for f in c.get("files", []):
            if f in target_set and f not in assigned_files and ((cwd / f).exists() or is_git_deleted(cwd, f)):
                filtered_files.append(f)
                assigned_files.add(f)
        if filtered_files:
            c["files"] = filtered_files
            c_msg = c.get("message", "feat: project update")
            
            # Extraction du subject et body existant
            if "\n\n" in c_msg:
                parts = c_msg.split("\n\n", 1)
                subj, raw_body = parts[0].strip(), parts[1].strip()
            elif "\n" in c_msg:
                parts = c_msg.split("\n", 1)
                subj, raw_body = parts[0].strip(), parts[1].strip()
            else:
                subj, raw_body = c_msg.strip(), ""

            header = sanitize_commit_header(subj, filtered_files, target_lang=target_lang)

            # Assemblage de la description technique concrète des fichiers
            bullets = []
            if analyses_dict:
                for f in filtered_files:
                    fa = analyses_dict.get(f, {})
                    label = format_file_label(f, filtered_files)
                    det = fa.get("details") or fa.get("intent") or "update configuration and logic"
                    bullets.append(f"- {label}: {det}")

            # Validation de la consistance du body
            is_body_valid = (
                len(raw_body) >= 25
                and not any(raw_body.lower().startswith(x) for x in ("feat", "fix", "chore", "docs", "build", "update files", "project update"))
                and raw_body.lower() != subj.lower()
            )

            if len(filtered_files) > 1:
                if is_body_valid and bullets:
                    full_body = f"{raw_body}\n\n" + "\n".join(bullets)
                elif bullets:
                    full_body = "\n".join(bullets)
                else:
                    full_body = raw_body or ("Mise à jour des fichiers et configurations du projet." if is_fr else "Updates target project files and configurations.")
            else:
                single_det = bullets[0].split(": ", 1)[-1] if bullets else ""
                fallback_single = "Mise à jour des ressources et configurations." if is_fr else "Updates configuration and resources."
                full_body = raw_body if is_body_valid else (single_det or fallback_single)

            c["message"] = f"{header}\n\n{full_body}"
            cleaned_commits.append(c)

    # Réconciliation des orphelins (fichiers ciblés mais non cités par le modèle)
    unassigned = [f for f in all_files if f not in assigned_files and ((cwd / f).exists() or is_git_deleted(cwd, f))]
    if unassigned:
        docs_orphans = [f for f in unassigned if any(x in f.lower() for x in ["readme", "license", "doc", "guide"])]
        code_orphans = [f for f in unassigned if f not in docs_orphans]

        if docs_orphans:
            docs_commit = next((c for c in cleaned_commits if "docs" in c.get("message", "").lower()), None)
            if docs_commit:
                docs_commit["files"].extend(docs_orphans)
                if analyses_dict:
                    new_bullets = [f"- {format_file_label(f, docs_commit['files'])}: {analyses_dict.get(f, {}).get('details', 'documentation')}" for f in docs_orphans]
                    docs_commit["message"] += "\n" + "\n".join(new_bullets)
            else:
                orphan_bullets = [f"- {f}: {analyses_dict.get(f, {}).get('details', 'documentation')}" for f in docs_orphans] if analyses_dict else []
                msg_docs = "docs(api): documenter le projet et les spécifications\n\n" if is_fr else "docs(api): add documentation and project references\n\n"
                cleaned_commits.append({
                    "message": msg_docs + "\n".join(orphan_bullets),
                    "files": docs_orphans
                })

        if code_orphans:
            if cleaned_commits:
                cleaned_commits[-1]["files"].extend(code_orphans)
                if analyses_dict:
                    new_bullets = [f"- {format_file_label(f, cleaned_commits[-1]['files'])}: {analyses_dict.get(f, {}).get('details', 'implementation')}" for f in code_orphans]
                    cleaned_commits[-1]["message"] += "\n" + "\n".join(new_bullets)
            else:
                orphan_bullets = [f"- {f}: {analyses_dict.get(f, {}).get('details', 'implementation')}" for f in code_orphans] if analyses_dict else []
                msg_code = "feat(core): implémenter les fonctionnalités principales du projet\n\n" if is_fr else "feat(core): implement core project functionality\n\n"
                cleaned_commits.append({
                    "message": msg_code + "\n".join(orphan_bullets),
                    "files": code_orphans
                })

    return cleaned_commits

def get_configured_default_model() -> str:
    """Récupère le modèle configuré dans l'environnement ou dans config.env."""
    env_model = os.environ.get("DEFAULT_MODEL", "").strip()
    if env_model:
        return env_model

    config_path = Path(__file__).resolve().parent.parent / "config.env"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEFAULT_MODEL="):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if val:
                            return val
        except Exception:
            pass

    return "qwen2.5-coder:1.5b"

def get_configured_ollama_host() -> str:
    """Récupère l'hôte Ollama configuré dans l'environnement (OLLAMA_HOST, OLLAMA_BASE_URL) ou dans config.env."""
    env_host = os.environ.get("OLLAMA_HOST", "").strip() or os.environ.get("OLLAMA_BASE_URL", "").strip()
    if env_host:
        host = env_host
    else:
        host = "http://localhost:11434"
        config_path = Path(__file__).resolve().parent.parent / "config.env"
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("OLLAMA_HOST=") or line.startswith("OLLAMA_BASE_URL="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                host = val
                                break
            except Exception:
                pass

    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    return host.rstrip("/")

def classify_model(model_name: str, param_size: str = "") -> str:
    """
    Qualifie honnêtement le modèle selon la taille réelle de ses paramètres :
    - <= 3.5B : "SLM sobre"
    - 4B à 14B : "LLM local"
    - > 14B : "LLM haute capacité"
    - Inconnu : "modèle local"
    """
    if not model_name and not param_size:
        return "modèle local"

    size_billions = None

    # 1. Vérification via la chaîne de taille passée (ex: '1.5B', '7.6B', '500M')
    if param_size:
        m_size = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*([bBmM])', param_size)
        if m_size:
            val = float(m_size.group(1))
            unit = m_size.group(2).upper()
            size_billions = val if unit == 'B' else (val / 1000.0)

    # 2. Si non trouvée, extraction depuis le tag du modèle (ex: 'qwen2.5-coder:1.5b', 'llama3.1:8b', 'smollm:360m')
    if size_billions is None and model_name:
        m_tag = re.search(r'[:_\-]([0-9]+(?:\.[0-9]+)?)([bBmM])\b', model_name)
        if m_tag:
            val = float(m_tag.group(1))
            unit = m_tag.group(2).upper()
            size_billions = val if unit == 'B' else (val / 1000.0)

    # 3. Qualification selon les seuils objectifs
    if size_billions is None:
        return "modèle local"

    if size_billions <= 3.5:
        return "SLM sobre"
    elif size_billions <= 14.5:
        return "LLM local"
    else:
        return "LLM haute capacité"

def get_model_qualification(model_name: str, base_url=None) -> str:
    """Interroge Ollama pour récupérer la taille exacte, ou analyse le nom du modèle."""
    base_url = (base_url or get_configured_ollama_host()).rstrip("/")
    param_size = ""
    try:
        req = urllib.request.Request(f"{base_url}/api/tags", headers={"User-Agent": "gtm"})
        with urllib.request.urlopen(req, timeout=0.8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for m in data.get("models", []):
                name = m.get("name", "")
                if name == model_name or name.startswith(model_name + ":") or model_name.startswith(name):
                    param_size = m.get("details", {}).get("parameter_size", "")
                    if param_size:
                        break
    except Exception:
        pass

    return classify_model(model_name, param_size=param_size)

def main():
    import argparse
    default_model = get_configured_default_model()
    default_host = get_configured_ollama_host()
    default_lang = get_configured_default_lang()
    parser = argparse.ArgumentParser(description=f"Générateur sobre de commit-plan.json via SLM local (défaut: {default_model}).")
    parser.add_argument("plan_file", nargs="?", default=".gtm/commit-plan.json", help="Fichier de sortie (défaut: .gtm/commit-plan.json)")
    parser.add_argument("-o", "--output", default=None, help="Chemin alternatif du fichier de sortie")
    parser.add_argument("-a", "--all", action="store_true", help="Analyser tous les fichiers du dossier (pas uniquement git status)")
    parser.add_argument("-m", "--model", default=default_model, help=f"Modèle Ollama (défaut configuré: {default_model})")
    parser.add_argument("-l", "--lang", default=default_lang, help=f"Langue des messages de commit (défaut configuré: {default_lang})")
    parser.add_argument("--ollama-host", default=default_host, help=f"Hôte du serveur Ollama (défaut: {default_host})")
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
    is_fr = (args.lang or "").lower().startswith("fr")
    is_es = (args.lang or "").lower().startswith("es")
    analyses = [analyze_file(cwd, f, target_lang=args.lang) for f in files]
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
                depth = min(3, len(p.parts) - 1)
                parent_dir = str(Path(*p.parts[:depth]))
                groups[parent_dir].append(f)
            else:
                cat = analyses_dict.get(f, {}).get("category", "core")
                groups[f"root/{cat}"].append(f)

        if is_fr:
            prompt_lines = ["Modules à regrouper en commits Conventional Commits atomiques et logiques :"]
        elif is_es:
            prompt_lines = ["Módulos para organizar en commits Conventional Commits atómicos y lógicos:"]
        else:
            prompt_lines = ["Modules to organize into logical, atomic Conventional Commits:"]

        for idx, (dir_path, g_files) in enumerate(groups.items(), 1):
            id_map[idx] = g_files
            if dir_path.startswith("root/"):
                scope_clean = clean_scope_name(dir_path.split("/")[1])
            else:
                scope_name = Path(dir_path).name.lower()
                scope_clean = clean_scope_name(scope_name)

            sample_types = [analyses_dict[gf]["type"] for gf in g_files if gf in analyses_dict]
            primary_type = sample_types[0] if sample_types else "feat"
            sample_intents = [analyses_dict[gf]["intent"] for gf in g_files if gf in analyses_dict]
            clean_intents = [re.sub(r'^(?:update:\s*|changes:\s*|implements\s*|mise à jour:\s*|modifications:\s*)', '', s, flags=re.I).strip() for s in sample_intents if s]
            
            # Résumé informatif multi-fichiers
            unique_intents = list(dict.fromkeys(clean_intents))[:3]
            summary = ", ".join(unique_intents)
            if is_fr:
                prompt_lines.append(f"- Module [{idx}] '{scope_clean}' [type: {primary_type}]: {len(g_files)} fichier(s)\n  * Rôle : {summary}")
            elif is_es:
                prompt_lines.append(f"- Módulo [{idx}] '{scope_clean}' [type: {primary_type}]: {len(g_files)} archivo(s)\n  * Rol: {summary}")
            else:
                prompt_lines.append(f"- Module [{idx}] '{scope_clean}' [type: {primary_type}]: {len(g_files)} file(s)\n  * Intent: {summary}")
    else:
        if is_fr:
            prompt_lines = ["Fichiers à regrouper en commits Conventional Commits atomiques et logiques :"]
        elif is_es:
            prompt_lines = ["Archivos para organizar en commits Conventional Commits atómicos y lógicos:"]
        else:
            prompt_lines = ["Files to organize into logical, atomic Conventional Commits:"]

        for idx, fa in enumerate(analyses, 1):
            id_map[idx] = [fa["path"]]
            if is_fr:
                desc = f"- [{idx}] {fa['path']} [type: {fa['type']}, scope: {fa['scope']}] : {fa['intent']}"
                if fa.get("links_to"):
                    desc += f" (liaisons : {', '.join(fa['links_to'])})"
            elif is_es:
                desc = f"- [{idx}] {fa['path']} [type: {fa['type']}, scope: {fa['scope']}] : {fa['intent']}"
                if fa.get("links_to"):
                    desc += f" (enlaces: {', '.join(fa['links_to'])})"
            else:
                desc = f"- [{idx}] {fa['path']} [type: {fa['type']}, scope: {fa['scope']}]: {fa['intent']}"
                if fa.get("links_to"):
                    desc += f" (links: {', '.join(fa['links_to'])})"
            prompt_lines.append(desc)

    prompt = "\n".join(prompt_lines)
    model_kind = get_model_qualification(args.model, base_url=args.ollama_host)
    lang_name = get_language_name(args.lang)
    print(f"\033[0;34m[INFO]\033[0m Inférence via {model_kind} '{args.model}' (mode: {'modulaire' if is_modular else 'fichiers'}, langue: {lang_name})...")
    res = call_ollama(prompt, is_modular=is_modular, model=args.model, base_url=args.ollama_host, target_lang=args.lang)

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

        # Récupération du message avec subject et body
        subj = rc.get("subject", "").strip()
        body = rc.get("body", "").strip()
        msg = rc.get("message", "").strip()

        if subj:
            commit_text = f"{subj}\n\n{body}" if body else subj
        elif msg:
            commit_text = msg
        else:
            commit_text = "feat: project update"

        expanded_commits.append({
            "message": commit_text,
            "files": c_files
        })

    # Nettoyage, déduplication, enrichissement de la description et réconciliation
    commits = reconcile_and_clean_commits(expanded_commits, files, cwd, analyses_dict=analyses_dict, target_lang=args.lang)

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

    # Assurer que le répertoire parent existe (ex: .gtm/)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Si le fichier est écrit dans un dossier .gtm, créer le .gitignore protecteur avec '*'
    if out_path.parent.name == ".gtm" or any(part == ".gtm" for part in out_path.parts):
        gtm_gitignore = out_path.parent / ".gitignore"
        if not gtm_gitignore.exists():
            try:
                with open(gtm_gitignore, "w", encoding="utf-8") as gf:
                    gf.write("*\n")
            except Exception:
                pass

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(plan_json + "\n")

    print(f"\033[0;32m[OK]\033[0m Plan de commits généré avec succès : {out_path} ({len(commits)} commits)")

if __name__ == "__main__":
    main()
