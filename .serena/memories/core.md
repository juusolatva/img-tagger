# img_tagger core

Authoritative detailed spec lives in `AGENTS.md` (CLAUDE.md just `@`-includes it): parsing order, metadata schema, locking, auto-healing, GIF handling. Read it before touching tagging/metadata logic; keep it in sync when behavior changes.

## Source map (flat, no package)
- `img_tagger.py` — single-file CLI. Pipeline: `process_directory` (`_find_images` → `_load_prompt` → `_create_client` → quit listener + `_run_tasks` [ThreadPoolExecutor + tqdm, totals in `_RunStats`] → `_print_report`) → `process_single_image` (format check [`get_image_format`; not in `TAGGABLE_FORMATS` → FAILED] → `is_already_processed` [`_pyexiv2_has_marker` on bytes, `_pillow_has_marker` fallback; GIF comment] → stop check (CANCELLED) → `get_tags_ollama`/`get_tags_lm_studio` → `parse_model_output` (applies `normalize_tags`) → `tag_image`) → `write_metadata` (JPEG/WebP/PNG via `_modify_with_pyexiv2`) or `write_gif_tags` (Pillow comment).
  - `--clear` path: `process_directory(clear=True)` → `clear_directory` → `clear_tags` (`_clear_standard` pyexiv2 + Pillow auto-heal / `_clear_gif`). Reuses `robust_replace`/`_sanitize_with_pillow`; no prompt, client, quit listener or report. (Former standalone `clear_tags.py` was removed; no duplicated helpers remain.)
- `prompt.txt` — overrides `DEFAULT_PROMPT`; unreadable file → `sys.exit(1)`.
- `.github/workflows/ci.yml`, `.github/dependabot.yml`, `pyproject.toml` (Ruff + coverage only), `sonar-project.properties`, `requirements-dev.lock` — CI/tooling; see `AGENTS.md` CI section.
- `tests/` — offline pytest suite (fake backends, generated images); `test_integration.py` is opt-in and uses `test_images/`.
- `test_images/` — gitignored local manual-test corpus (may not exist).

## Invariants
- `process_single_image` returns `(status, filename, message, duration)`; status ∈ SUCCESS/FAILED/SKIPPED/CANCELLED. Designed not to raise (exceptions → FAILED); keep the `_run_tasks` guard around `future.result()` as a backstop.
- Format dispatch is by Pillow-detected format everywhere (`tag_image`, `is_already_processed`, `clear_tags`); the extension only decides for unreadable files (`_is_gif`).
- All pyexiv2 calls under module-level `metadata_lock`, and pyexiv2 only gets bytes (`ImageData`), never a path. Model calls and Pillow work stay outside the lock (exception: `write_metadata`'s auto-heal re-save + replace run inside it).
- Writes go to `tempfile.mkstemp(dir=<image dir>)` copy, then `robust_replace`, cleanup in `finally`.
- Skip marker string `[PROCESSED BY AI]` (constant `PROCESSED_MARKER`) is the idempotency contract between tagger, `--clear` and already-tagged user files — don't change its text.
- Worker bound (1–4) checked in `__main__` arg handling only.
- Optional imports (`msvcrt`, `termios`/`tty`, `ollama`, `openai`) fall back to `None`; code checks for `None` rather than importing lazily.

## Further memories
- Dependencies, Python version, dev machines, lockfile, Ruff/coverage config, CI jobs, backend gotchas (LM Studio ids, vision projector): `mem:tech_stack`
- Run/clear/log commands: `mem:suggested_commands`
- Code style (docstrings, typing, logging, pyexiv2 bytes-only): `mem:conventions`
- What to verify before declaring done (pytest, Ruff check/format, integration run, lock regen, SonarQube rules): `mem:task_completion`
