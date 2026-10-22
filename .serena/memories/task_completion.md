# Task completion checklist
CI (GitHub Actions) enforces steps 1–2 on push/PR; run them locally first.
1. `python3 -m pytest` (offline, ~15s; install via `requirements-dev.txt`). Strict xfails pin known bugs — an XPASS means a fix landed; drop the marker.
2. `ruff check .` and `ruff format --check .` must pass (baseline is clean; CI fails otherwise). Use `ruff format .` to fix formatting. `basedpyright` warnings are user-global strict rules, not gated — just don't add new ones.
3. Behavior changes: `python3 -m pytest -m integration --run-integration -s` against a live backend (copies `test_images/` to tmp, prints tags; flags in `AGENTS.md`; LM Studio needs `--tagger-model <LM Studio id>`), or a manual `img_tagger.py <dir>` run + `--clear` reset. Cover .jpg/.png/.webp/.gif, plus a corrupt-EXIF sample when touching auto-heal. Say so if no backend is available.
4. Changed `requirements*.txt` → regenerate `requirements-dev.lock` (command in `AGENTS.md` CI section; add `--upgrade`/`-P <pkg>` to actually bump pins).
5. Update `AGENTS.md` (and README if user-visible) when behavior, invariants or CI change.
6. New code should stay within SonarQube rules (scanned in CI): cognitive complexity ≤ 15, no duplicated literals, `logger.exception()` in `except`, one condition per test `assert`.
