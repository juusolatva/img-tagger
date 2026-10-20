# Task completion checklist
CI (GitHub Actions) enforces steps 1–2 on push/PR; run them locally first.
1. `python3 -m pytest` (offline, ~15s; install via `requirements-dev.txt`). Strict xfails pin known bugs — an XPASS means a fix landed; drop the marker.
2. `ruff check .` and `ruff format --check .` must pass (baseline is clean; CI fails otherwise). Use `ruff format .` to fix formatting. `basedpyright` warnings are user-global strict rules, not gated — just don't add new ones.
3. Behavior changes: manual run against sample images of each format (.jpg/.png/.webp/.gif, plus a corrupt-EXIF sample if touching auto-heal), then `img_tagger.py <dir> --clear` to reset. Requires a running Ollama/LM Studio for the tagger; say so if not verifiable.
4. Changed `requirements*.txt` → regenerate `requirements-dev.lock` (command in `AGENTS.md` CI section).
5. Update `AGENTS.md` (and README if user-visible) when behavior, invariants or CI change.
6. New code should stay within SonarQube rules (scanned in CI): cognitive complexity ≤ 15, no duplicated literals, `logger.exception()` in `except`, one condition per test `assert`.
