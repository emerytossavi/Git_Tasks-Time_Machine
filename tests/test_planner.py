#!/usr/bin/env python3
"""
tests/test_planner.py - Tests unitaires pour lib/planner.py
Framework: standard library unittest (zéro dépendance pip externe)
"""

import unittest
import sys
import os
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Ajouter la racine du projet au sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))

import planner

class TestPlannerUnit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cwd = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_is_system_excluded(self):
        """Vérifie que .gtm, .git, .DS_Store et commit-plan.json sont exclus des scans."""
        self.assertTrue(planner.is_system_excluded(".gtm"))
        self.assertTrue(planner.is_system_excluded(".gtm/commit-plan.json"))
        self.assertTrue(planner.is_system_excluded(".gtm/.gitignore"))
        self.assertTrue(planner.is_system_excluded(".git"))
        self.assertTrue(planner.is_system_excluded(".git/HEAD"))
        self.assertTrue(planner.is_system_excluded(".DS_Store"))
        self.assertTrue(planner.is_system_excluded("commit-plan.json"))
        # Fichiers réguliers autorisés
        self.assertFalse(planner.is_system_excluded("src/main.py"))
        self.assertFalse(planner.is_system_excluded("README.md"))

    def test_clean_scope_name(self):
        self.assertEqual(planner.clean_scope_name("src"), "src")
        self.assertEqual(planner.clean_scope_name("API_Service"), "api-service")
        self.assertEqual(planner.clean_scope_name("code"), "code")
        self.assertEqual(planner.clean_scope_name(""), "core")

    def test_sanitize_commit_header(self):
        # Header simple valide
        self.assertEqual(
            planner.sanitize_commit_header("feat(api): add endpoint"),
            "feat(api): add endpoint"
        )
        # Suppression du point final
        self.assertEqual(
            planner.sanitize_commit_header("fix(auth): fix token validation."),
            "fix(auth): fix token validation"
        )
        # Remplacement / suppression de scope interdit (code -> scope omis)
        self.assertEqual(
            planner.sanitize_commit_header("refactor(code): clean handler"),
            "refactor: clean handler"
        )
        # Elimination des verbes HTTP bruts
        self.assertNotIn(
            "POST /api",
            planner.sanitize_commit_header("feat(auth): POST /api/v1/login")
        )
        # Majuscule forcée en minuscule sur le sujet
        self.assertEqual(
            planner.sanitize_commit_header("docs(readme): Update installation instructions"),
            "docs(readme): update installation instructions"
        )

    def test_reconcile_and_clean_commits_returns_list_never_none(self):
        """Vérifie que reconcile_and_clean_commits renvoie TOUJOURS une liste (régression du return manquant)."""
        f1 = self.cwd / "main.py"
        f1.write_text("print('hello')")
        
        raw_commits = [{
            "message": "feat(core): initial implementation",
            "files": ["main.py"]
        }]
        
        result = planner.reconcile_and_clean_commits(raw_commits, ["main.py"], self.cwd)
        self.assertIsNotNone(result)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertIn("main.py", result[0]["files"])

    def test_reconcile_and_clean_commits_handles_orphans(self):
        """Vérifie que les fichiers orphelins non cités sont réconciliés et non perdus."""
        f1 = self.cwd / "main.py"
        f1.write_text("print('hello')")
        f2 = self.cwd / "README.md"
        f2.write_text("# Doc")

        raw_commits = [{
            "message": "feat(core): implement entrypoint",
            "files": ["main.py"]
        }]

        # README.md est dans all_files mais pas dans raw_commits
        result = planner.reconcile_and_clean_commits(raw_commits, ["main.py", "README.md"], self.cwd)
        self.assertIsNotNone(result)
        all_assigned = [f for c in result for f in c["files"]]
        self.assertIn("main.py", all_assigned)
        self.assertIn("README.md", all_assigned)

    def test_assign_timestamps_ordering_and_safety(self):
        """Vérifie la sécurité et l'ordre chronologique strict des timestamps."""
        # Sécurité : entrées vides ou None
        self.assertEqual(planner.assign_timestamps([], self.cwd), [])
        self.assertEqual(planner.assign_timestamps(None, self.cwd), [])

        f1 = self.cwd / "a.txt"
        f2 = self.cwd / "b.txt"
        f1.write_text("a")
        f2.write_text("b")

        commits = [
            {"message": "feat: first", "files": ["a.txt"]},
            {"message": "feat: second", "files": ["b.txt"]}
        ]

        assigned = planner.assign_timestamps(commits, self.cwd)
        self.assertEqual(len(assigned), 2)
        
        # Vérification des dates ISO et de la stricte monotonicité
        d1 = datetime.fromisoformat(assigned[0]["date"])
        d2 = datetime.fromisoformat(assigned[1]["date"])
        self.assertLessEqual(d1, d2)

    def test_get_configured_default_model(self):
        """Vérifie la résolution du modèle configuré."""
        old_env = os.environ.get("DEFAULT_MODEL")
        try:
            os.environ["DEFAULT_MODEL"] = "custom-test:model"
            self.assertEqual(planner.get_configured_default_model(), "custom-test:model")
        finally:
            if old_env is not None:
                os.environ["DEFAULT_MODEL"] = old_env
            else:
                os.environ.pop("DEFAULT_MODEL", None)

    def test_get_configured_ollama_host(self):
        """Vérifie la résolution et normalisation de l'hôte Ollama configuré."""
        old_host = os.environ.get("OLLAMA_HOST")
        old_base = os.environ.get("OLLAMA_BASE_URL")
        try:
            # 1. URL complète avec port personnalisé
            os.environ["OLLAMA_HOST"] = "http://192.168.1.100:11435"
            self.assertEqual(planner.get_configured_ollama_host(), "http://192.168.1.100:11435")

            # 2. URL sans schéma http:// et avec slash final (doit être normalisée)
            os.environ["OLLAMA_HOST"] = "remote-server.lan:11434/"
            self.assertEqual(planner.get_configured_ollama_host(), "http://remote-server.lan:11434")

            # 3. Via OLLAMA_BASE_URL
            os.environ.pop("OLLAMA_HOST", None)
            os.environ["OLLAMA_BASE_URL"] = "https://secure-ai.corp:8443"
            self.assertEqual(planner.get_configured_ollama_host(), "https://secure-ai.corp:8443")
        finally:
            if old_host is not None:
                os.environ["OLLAMA_HOST"] = old_host
            else:
                os.environ.pop("OLLAMA_HOST", None)
            if old_base is not None:
                os.environ["OLLAMA_BASE_URL"] = old_base
            else:
                os.environ.pop("OLLAMA_BASE_URL", None)

    def test_classify_model(self):
        """Vérifie la qualification honnête et dynamique du modèle selon sa taille réelle."""
        # 1. Modèles SLM sobres (<= 3.5B ou en Millions de paramètres)
        self.assertEqual(planner.classify_model("qwen2.5-coder:1.5b"), "SLM sobre")
        self.assertEqual(planner.classify_model("llama3.2:3b"), "SLM sobre")
        self.assertEqual(planner.classify_model("smollm:360m"), "SLM sobre")
        self.assertEqual(planner.classify_model("custom", param_size="1.5B"), "SLM sobre")
        self.assertEqual(planner.classify_model("custom", param_size="500M"), "SLM sobre")

        # 2. Modèles LLM intermédiaires (4B - 14B)
        self.assertEqual(planner.classify_model("qwen2.5-coder:7b"), "LLM local")
        self.assertEqual(planner.classify_model("llama3.1:8b"), "LLM local")
        self.assertEqual(planner.classify_model("deepseek-r1:14b"), "LLM local")
        self.assertEqual(planner.classify_model("custom", param_size="7.6B"), "LLM local")

        # 3. Modèles LLM haute capacité (> 14B)
        self.assertEqual(planner.classify_model("codestral:22b"), "LLM haute capacité")
        self.assertEqual(planner.classify_model("deepseek-r1:32b"), "LLM haute capacité")
        self.assertEqual(planner.classify_model("llama3.1:70b"), "LLM haute capacité")
        self.assertEqual(planner.classify_model("custom", param_size="70B"), "LLM haute capacité")

        # 4. Modèle inconnu sans indication de taille
        self.assertEqual(planner.classify_model("my-custom-model"), "modèle local")
        self.assertEqual(planner.classify_model(""), "modèle local")

    def test_gtm_gitignore_isolation(self):
        """Vérifie que le dossier .gtm est automatiquement isolé avec un .gitignore contenant '*'."""
        import subprocess
        # Initialiser un dépôt git dans le répertoire temporaire
        subprocess.run(["git", "init", "-q"], cwd=str(self.cwd), check=True)

        gtm_dir = self.cwd / ".gtm"
        gtm_dir.mkdir(parents=True, exist_ok=True)
        gitignore_file = gtm_dir / ".gitignore"
        gitignore_file.write_text("*\n", encoding="utf-8")
        plan_file = gtm_dir / "commit-plan.json"
        plan_file.write_text('{"commits": []}\n', encoding="utf-8")

        # Vérifier que git status ignore complètement .gtm et ses résidus
        res = subprocess.run(["git", "status", "--porcelain"], cwd=str(self.cwd), capture_output=True, text=True, check=True)
        self.assertEqual(res.stdout.strip(), "", "Le dossier .gtm ne doit laisser aucun résidu dans git status")

if __name__ == "__main__":
    unittest.main()
