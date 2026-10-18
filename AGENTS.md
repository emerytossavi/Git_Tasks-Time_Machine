# AGENTS.md — Git Tasks-Time Machine (`gtm`)

> **Contract and Operational Directives for Autonomous AI Agents**  
> Target Systems: Cursor, Claude Code, GitHub Copilot, Devin, Antigravity, CI/CD automated workers.

---

## 1. System Identity & Mission

`gtm` (**Git Tasks-Time Machine**) is an offline-first, eco-responsible CLI tool designed to reconstruct clean, granular, conventional Git histories with precise past timestamps.

When operating as an AI agent in a repository using `gtm`:
- You MUST treat `gtm` as the **deterministic execution engine** for historical commits.
- You SHOULD generate or inspect `commit-plan.json` rather than directly issuing raw `GIT_AUTHOR_DATE` shell commands.
- You MUST uphold the **safety invariants** described below.

---

## 2. Invariants & Safety Contracts

| Invariant | Description |
| :--- | :--- |
| **No Remote Contamination** | `gtm` NEVER executes `git push`, `git fetch`, or network Git commands. All mutations are strictly local to `.git`. |
| **Deterministic Validation** | An agent MUST NEVER execute `gtm run` without first validating the plan via `gtm validate` and simulating via `gtm dry-run`. |
| **Zero Idle Footprint** | All SLM/LLM calls to Ollama MUST pass `"keep_alive": 0` (or `"keep_alive": "0s"`) to release model VRAM/RAM immediately upon completion. |
| **Monotonic Chronology** | Commit dates in `commit-plan.json` MUST be chronologically non-decreasing (`commit[i].date <= commit[i+1].date`). |
| **Conventional Commits v1.0.0** | Commit messages MUST strictly adhere to Conventional Commits with a valid type (`feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`). |
| **Substantive Descriptions** | If a commit touches multiple files or introduces functional logic, the message MUST include an explanatory body separated from the subject by a blank line (`\n\n`). |
| **Test Suite Gatekeeper (TDD)** | Any agent modifying GTM source code MUST run `gtm test` and achieve exit status 0 before finalizing changes. |

---

## 3. CLI Command Reference & Deterministic Exit Codes

All `gtm` commands conform to standard POSIX exit status:
- `0`: Success / Passed.
- `1`: Validation error / Configuration failure / Git conflict.
- `2`: Missing required dependency or environmental error.

### 3.1. `gtm doctor`
Diagnoses host dependencies (Bash 3.2+, Git, `jq`, `date`/`gdate`, Python 3, Ollama daemon, and local model).

```bash
gtm doctor
```
- **Exit 0**: All required tools and local worktree are ready.
- **Exit 1**: Missing dependency (e.g., `jq` or `git` missing).
- *Agent Action*: Run `gtm doctor` at step 0 of any setup workflow.

### 3.2. `gtm plan`
Leverages the local SLM (default `qwen2.5-coder:1.5b`) to inspect unstaged/staged files, extract semantic intent (AST functions, API endpoints, XML workflows, config schemas), and generate `.gtm/commit-plan.json` (with automatic `.gtm/.gitignore` containing `*` to guarantee zero Git tracking residue).

```bash
# Plan uncommitted changes (generates .gtm/commit-plan.json)
gtm plan

# Include all files (tracked + untracked)
gtm plan -a

# Non-interactive preview (outputs JSON without writing to file)
gtm plan --dry-run

# Specify target model or custom output
gtm plan -m qwen2.5-coder:1.5b -o custom-plan.json
```

### 3.3. `gtm validate [plan.json]`
Verifies the syntactic and semantic integrity of the commit plan:
- JSON schema conformance.
- File existence on the local filesystem (or tracked deleted files in Git history/index).
- ISO 8601 timestamp compliance (`YYYY-MM-DDTHH:MM:SS[+-]HH:MM`).
- Chronological ordering verification.
- Conventional commit message header format.

```bash
# Validates default plan (.gtm/commit-plan.json or fallback commit-plan.json)
gtm validate

# Or specify a custom plan file
gtm validate .gtm/commit-plan.json
```
- **Exit 0**: Plan is completely valid and ready for execution.
- **Exit 1**: Structural or semantic failure (error logged to stderr).

### 3.4. `gtm dry-run [plan.json]`
Performs a full dry-run simulation of the commit plan:
- Resolves all file paths and globs (annotating deleted files with `[supprimé]`).
- Displays target commit dates and formatted messages.
- Does NOT touch the Git index or object database.

```bash
gtm dry-run
# Or specify a custom plan
gtm dry-run .gtm/commit-plan.json
```

### 3.5. `gtm run [plan.json]`
Executes atomic staging and commits for each item in the plan:
- Sets `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` per commit.
- Stages exact file lists using `git add -A -- <files>` (safely capturing additions, modifications, and deletions).
- Creates commits via `git commit -m "<message>"`.

```bash
gtm run
# Or specify a custom plan
gtm run .gtm/commit-plan.json
```

### 3.6. `gtm model [model_name|--list]`
Inspects or persistently configures the default SLM model in `config.env`:

```bash
# List available generation models in local Ollama and show the active one
gtm model --list

# Set the default model for future gtm plan executions (writes to config.env)
gtm model qwen2.5-coder:7b
```
- **Exit 0**: Model successfully listed or saved.
- **Exit 1**: Unrecognized arguments or empty input.

### 3.7. `gtm lang [lang_code]`
Inspects or persistently configures the target commit message language in `config.env`:
- Conventional Commit types (`feat`, `fix`, `docs`, etc.) always remain standardized in English.
- The message summary and body description are generated strictly in the chosen language without multilingual mixing.

```bash
# Show active commit language
gtm lang

# Set default commit language (writes DEFAULT_LANG to config.env)
gtm lang fr
gtm lang en
```
- **Exit 0**: Language successfully displayed or saved.
- **Exit 1**: Missing language code.

### 3.8. `gtm test`
Executes the comprehensive automated TDD test suite (Python `unittest` and isolated Shell sandboxes):
- Planner unit tests (sanitization, reconciliation, monotonicity, configuration, languages).
- Validator integration tests (valid plans, missing files, malformed JSON, dates).
- Model and config integration tests (persistence, fallbacks, list modes, lang).
- Runner and simulation tests (dry-run, atomic commit execution, exact timestamps, zero-residue).

```bash
gtm test
```
- **Exit 0**: All test suites passed (`[SUCCÈS TOTAL]`).
- **Exit 1**: At least one test suite failed.

---

## 4. Standard Agent Workflows

### Scenario A: Clean Workspace Commit Sequence (Autonomous Split)
Use this recipe when an agent has modified multiple files and wants to commit them cleanly into granular logical units with past timestamps:

```bash
# Step 1: Pre-flight check
gtm doctor || exit 1

# Step 2: Generate candidate plan (saved in .gtm/commit-plan.json)
gtm plan -a

# Step 3: Automated verification (automatically targets .gtm/commit-plan.json)
gtm validate || {
  echo "Validation failed; inspect .gtm/commit-plan.json"
  exit 1
}

# Step 4: Dry-run check
gtm dry-run

# Step 5: Execute commits
gtm run
```

### Scenario B: Custom Plan Generation by Agent (Bypassing SLM)
An AI agent can directly author `.gtm/commit-plan.json` without running Ollama:

1. Create `.gtm/commit-plan.json` following the schema in [`docs/commit-plan-spec.md`](file:///Users/emery.toss/Downloads/Workspace/apps/Git_Tasks-Time_Machine/docs/commit-plan-spec.md).
2. Validate and execute:
   ```bash
   gtm validate && gtm run
   ```

---

## 5. Commit Plan JSON Specification Quick Reference

For complete formal schema definitions, refer to [`docs/commit-plan-spec.md`](file:///Users/emery.toss/Downloads/Workspace/apps/Git_Tasks-Time_Machine/docs/commit-plan-spec.md).

```json
{
  "commits": [
    {
      "date": "2026-10-16T09:15:00+01:00",
      "message": "feat(scope): short imperative summary\n\nDetailed technical explanation of what was implemented and why.\n\n- file1.js: implement handler\n- file2.js: configure routes",
      "files": [
        "src/file1.js",
        "src/file2.js"
      ]
    }
  ]
}
```

### Message Structure Rules:
1. **Header**: `<type>(<scope>): <summary>` (lowercase type, no trailing period, maximum 72 characters recommended, hard limit 100).
2. **Body**: Separated by two newlines (`\n\n`), describes what was done and contextual rationale.
3. **Bullet details**: Optional list of affected files and key functional changes.

---

## 6. Guidelines for Agent Prompting & Self-Correction

If `gtm validate` fails during agent execution:
1. Parse the error output from stderr.
2. If the error mentions `Ordre chronologique invalide`:
   - Inspect the dates in `commit-plan.json`.
   - Sort the array of `commits` chronologically ascending by `date`.
3. If the error mentions `Fichier inexistant`:
   - Check if the file was deleted: ensure it was previously tracked in Git (in `HEAD` or staged).
   - Otherwise, check `git status` and adjust `files` array to match existing paths.
4. If the error mentions `Format de message invalide`:
   - Ensure the first line starts with `^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9_-]+\))?: [a-z0-9]`.
