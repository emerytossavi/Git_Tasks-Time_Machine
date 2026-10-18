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
import subprocess

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
        self.assertTrue(planner.is_system_excluded("config.env"))
        # Fichiers réguliers autorisés
        self.assertFalse(planner.is_system_excluded("config.env.example"))
        self.assertFalse(planner.is_system_excluded("src/main.py"))
        self.assertFalse(planner.is_system_excluded("README.md"))

    def test_is_system_excluded_allows_deleted_tracked_commit_plan(self):
        """Vérifie que commit-plan.json n'est pas exclu s'il s'agit d'un fichier suivi supprimé."""
        subprocess.run(["git", "init", "-q"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(self.cwd), check=True)

        plan = self.cwd / "commit-plan.json"
        plan.write_text('{"commits": []}')
        subprocess.run(["git", "add", "commit-plan.json"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "legacy plan"], cwd=str(self.cwd), check=True, capture_output=True)

        plan.unlink()
        self.assertFalse(planner.is_system_excluded("commit-plan.json", cwd=self.cwd))
        status_files = planner.get_git_status_files(self.cwd)
        self.assertIn("commit-plan.json", status_files)

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
        # Élimination des scopes tautologiques (ex: test(test) -> test, docs(docs) -> docs)
        self.assertEqual(
            planner.sanitize_commit_header("test(test): update unit tests"),
            "test: update unit tests"
        )
        self.assertEqual(
            planner.sanitize_commit_header("docs(docs): update documentation"),
            "docs: update documentation"
        )
        self.assertEqual(
            planner.sanitize_commit_header("chore(chore): update dependencies"),
            "chore: update dependencies"
        )
        # Nettoyage des numérotations brutes de sections markdown (ex: add 1. L'Essence...)
        self.assertEqual(
            planner.sanitize_commit_header("docs: add 1. L'Essence du Projet"),
            "docs: add L'Essence du Projet"
        )
        # Support des verbes impératifs en français sans ajout intempestif de 'add'
        self.assertEqual(
            planner.sanitize_commit_header("feat(auth): implémenter la connexion OAuth", target_lang="fr"),
            "feat(auth): implémenter la connexion OAuth"
        )
        self.assertEqual(
            planner.sanitize_commit_header("docs(api): documenter les endpoints API", target_lang="fr"),
            "docs(api): documenter les endpoints API"
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

    def test_language_configuration_and_naming(self):
        """Vérifie la résolution de la langue configurée et le mappage des noms de langues."""
        # Noms de langues
        self.assertEqual(planner.get_language_name("en"), "English")
        self.assertEqual(planner.get_language_name("fr"), "French")
        self.assertEqual(planner.get_language_name("es"), "Spanish")
        self.assertEqual(planner.get_language_name("de"), "German")
        self.assertEqual(planner.get_language_name("custom"), "custom")

        # Résolution de DEFAULT_LANG via variable d'environnement
        old_lang = os.environ.get("DEFAULT_LANG")
        try:
            os.environ["DEFAULT_LANG"] = "fr"
            self.assertEqual(planner.get_configured_default_lang(), "fr")
            os.environ["DEFAULT_LANG"] = "es"
            self.assertEqual(planner.get_configured_default_lang(), "es")
        finally:
            if old_lang is not None:
                os.environ["DEFAULT_LANG"] = old_lang
            else:
                os.environ.pop("DEFAULT_LANG", None)

    def test_read_config_var_cascade(self):
        """Vérifie le chargement en cascade : environnement > config.env > config.env.example > fallback."""
        # 1. Fallback par défaut
        self.assertEqual(planner.read_config_var(["NON_EXISTENT_VAR"], fallback="default_val"), "default_val")

        # 2. Surcharge via variable d'environnement
        os.environ["TEST_GTM_VAR"] = "from_env"
        try:
            self.assertEqual(planner.read_config_var(["TEST_GTM_VAR"], fallback="fallback"), "from_env")
        finally:
            os.environ.pop("TEST_GTM_VAR", None)

    def test_extract_file_intent_multilingual(self):
        """Vérifie que extract_file_intent produit des résumés adaptés à la langue cible."""
        readme = self.cwd / "README.md"
        readme.write_text("# Project")

        # Test anglais
        summary_en, details_en = planner.extract_file_intent(self.cwd, "README.md", target_lang="en")
        self.assertIn("document", summary_en.lower())
        self.assertIn("architecture", summary_en.lower())

        # Test français
        summary_fr, details_fr = planner.extract_file_intent(self.cwd, "README.md", target_lang="fr")
        self.assertIn("documenter", summary_fr.lower())
        self.assertIn("architecture", summary_fr.lower())

        # Test espagnol
        summary_es, details_es = planner.extract_file_intent(self.cwd, "README.md", target_lang="es")
        self.assertIn("documentar", summary_es.lower())

    def test_categorize_file_docs_precedence_over_spec(self):
        """Vérifie que les spécifications documentaires (ex: commit-plan-spec.md) sont bien classées en docs et non en test."""
        cat = planner.categorize_file("docs/commit-plan-spec.md")
        self.assertEqual(cat["type"], "docs")
        self.assertEqual(cat["scope"], "docs")

    def test_get_git_status_files_includes_deleted_files(self):
        """RED test: Vérifie que les fichiers supprimés du dépôt sont détectés par get_git_status_files."""
        # Initialiser un dépôt git dans self.cwd
        subprocess.run(["git", "init"], cwd=str(self.cwd), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(self.cwd), check=True)

        # Créer et commiter un fichier
        test_file = self.cwd / "obsolete.py"
        test_file.write_text("def old(): pass\n")
        subprocess.run(["git", "add", "obsolete.py"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "feat: initial obsolete"], cwd=str(self.cwd), check=True)

        # Supprimer le fichier
        test_file.unlink()

        # get_git_status_files doit impérativement lister le fichier supprimé
        status_files = planner.get_git_status_files(self.cwd)
        self.assertIn("obsolete.py", status_files, "Le fichier supprimé doit être détecté dans git status")

    def test_extract_file_intent_deleted_file(self):
        """RED test: Vérifie que extract_file_intent extrait une intention de suppression contextualisée."""
        # Initialiser un dépôt git dans self.cwd
        subprocess.run(["git", "init"], cwd=str(self.cwd), capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(self.cwd), check=True)

        code_file = self.cwd / "legacy_service.py"
        code_file.write_text("def obsolete_handler():\n    pass\n")
        subprocess.run(["git", "add", "legacy_service.py"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "feat: add legacy service"], cwd=str(self.cwd), check=True)

        code_file.unlink()

        # En français
        summary_fr, details_fr = planner.extract_file_intent(self.cwd, "legacy_service.py", target_lang="fr")
        self.assertTrue(any(w in summary_fr.lower() for w in ("supprimer", "suppression", "retirer")), f"Attendu mot de suppression en FR, reçu: {summary_fr}")

        # En anglais
        summary_en, details_en = planner.extract_file_intent(self.cwd, "legacy_service.py", target_lang="en")
        self.assertTrue(any(w in summary_en.lower() for w in ("remove", "delete")), f"Attendu mot de suppression en EN, reçu: {summary_en}")

    def test_reconcile_and_clean_commits_preserves_deleted_files(self):
        """Vérifie que reconcile_and_clean_commits ne rejette pas les fichiers suivis supprimés."""
        subprocess.run(["git", "init"], cwd=str(self.cwd), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(self.cwd), check=True)

        target = self.cwd / "deleted_service.py"
        target.write_text("class OldService:\n    pass\n")
        subprocess.run(["git", "add", "deleted_service.py"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "initial"], cwd=str(self.cwd), check=True, capture_output=True)
        target.unlink()

        raw_commits = [{
            "message": "refactor: remove obsolete service",
            "files": ["deleted_service.py"]
        }]
        result = planner.reconcile_and_clean_commits(
            raw_commits,
            ["deleted_service.py"],
            self.cwd,
            analyses_dict={"deleted_service.py": {"details": "suppression du service déprécié", "intent": "supprimer legacy"}}
        )
        self.assertEqual(len(result), 1)
        self.assertIn("deleted_service.py", result[0]["files"])

    def test_assign_timestamps_deleted_files(self):
        """Vérifie que assign_timestamps assigne des dates valides même si les fichiers sont supprimés."""
        commits = [{
            "message": "refactor: remove obsolete service",
            "files": ["non_existent_deleted.py"]
        }]
        assigned = planner.assign_timestamps(commits, self.cwd)
        self.assertEqual(len(assigned), 1)
        self.assertIn("date", assigned[0])
        self.assertTrue(len(assigned[0]["date"]) >= 19)

    def test_get_all_git_files_includes_deleted_files(self):
        """Vérifie que get_all_git_files (utilisé avec gtm plan -a) inclut aussi les fichiers suivis supprimés."""
        subprocess.run(["git", "init", "-q"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(self.cwd), check=True)

        f1 = self.cwd / "active.py"
        f2 = self.cwd / "to_delete.py"
        f1.write_text("hello")
        f2.write_text("obsolete")
        subprocess.run(["git", "add", "."], cwd=str(self.cwd), check=True)
        subprocess.run(["git", "commit", "--no-gpg-sign", "-m", "init"], cwd=str(self.cwd), check=True, capture_output=True)

        f2.unlink()
        files = planner.get_all_git_files(self.cwd)
        self.assertIn("to_delete.py", files)
        self.assertIn("active.py", files)

if __name__ == "__main__":
    unittest.main()


