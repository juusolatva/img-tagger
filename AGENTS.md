# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
- `img_tagger.py` — single-file CLI: tags JPEG/WebP/PNG/GIF files via a local vision-language model (Ollama or LM Studio), writing tags into image metadata. `--clear` strips tags/metadata back out instead (used to reset images for testing; no model backend needed).
- `prompt.txt` — externalized LLM prompt; takes precedence over the `DEFAULT_PROMPT` fallback hardcoded in `img_tagger.py`.
- Flat repo layout: no package structure, not installable (`pyproject.toml` only holds Ruff and coverage config; no `setup.py`). Tests live in `tests/` (pytest, configured by `pytest.ini`). CI: GitHub Actions (see CI section).
- Requires **Python 3.10+** (uses modern type annotations like `str | None` and `list[str]`).

## Build/Lint/Test Commands
Ruff (lint + format) is configured in `pyproject.toml`; CI fails on any Ruff finding or unformatted file. SonarQube Cloud (project `juusolatva_img_tagger`) runs in CI; keep functions under its cognitive-complexity limit of 15 by extracting `_private` helpers.
- Dependencies: `pip install -r requirements.txt` (or `pip3 install -r requirements.txt`); dev deps (pytest, pytest-cov, Ruff): `pip install -r requirements-dev.txt`
- Lint/format: `ruff check .` and `ruff format .` (CI runs `ruff format --check`). Use the Ruff version pinned in `requirements-dev.txt`.
- Run tests: `python3 -m pytest` (offline: images generated on the fly, model backends faked; ~15s). With coverage like CI: `python3 -m pytest --cov`
- Integration tests (opt-in, need a live backend + images in git-ignored `test_images/`; copies images to a temp dir, prints tags for manual quality review): `python3 -m pytest -m integration --run-integration -s [--tagger-backend lm-studio] [--tagger-host URL] [--tagger-model M] [--images-dir DIR]`
- Run tagger (Ollama, default): `python3 img_tagger.py <directory>`
- Run tagger (LM Studio): `python3 img_tagger.py <directory> --backend lm-studio`
- Recursive, custom model/workers: `python3 img_tagger.py <directory> -r --model <model> --workers 4`
- Clear all tags: `python3 img_tagger.py <directory> --clear [-r] [--workers N]`
- Help: `python3 img_tagger.py -h`
- Request timeout (seconds, default 600): `python3 img_tagger.py <directory> --timeout 1200`
- Logging: `python3 img_tagger.py <dir> --log output.log` (see Logging under Core Rules)
- Note: On Linux environments, use `python3` if `python` is not aliased.

## CI
`.github/workflows/ci.yml` (GitHub Actions) runs on pushes to `main`, pull requests and manual dispatch:
- **Ruff**: `ruff check` and `ruff format --check --diff`. `ruff-action` reads the Ruff version from the `ruff==` pin in `requirements-dev.txt`.
- **Tests**: `pytest --cov --cov-report=xml` on Python 3.10, 3.11, 3.12, 3.13 and 3.14 (`fail-fast: false`). Integration tests are skipped (no backend). Installs from `requirements-dev.lock` with `--require-hashes --only-binary :all:`, so every locked package needs a wheel for every matrix version. The 3.14 job uploads `coverage.xml` as an artifact.
- **SonarQube Cloud**: runs after the tests and scans with the downloaded `coverage.xml`. Settings are in `sonar-project.properties` (sources `.`, `tests/**` excluded and treated as tests, `sonar.python.version` 3.10–3.14). Needs the `SONAR_TOKEN` repo secret. Coverage is configured in `[tool.coverage.run]` in `pyproject.toml` (branch coverage, `tests/` omitted, `relative_files = true` so Sonar can map the paths in `coverage.xml` to its sources).
- Third-party actions are pinned to commit SHAs with a `# vX.Y.Z` comment. GitHub's own `actions/*` use major-version tags.
- **`requirements-dev.lock`**: hash-locked, cross-platform lock of `requirements-dev.txt` (and thus `requirements.txt`) for Python ≥3.10. Only CI installs it; end users still get the `>=` bounds. After changing either requirements file (or to bump versions), regenerate it with `uv pip compile requirements-dev.txt --universal --python-version 3.10 --generate-hashes --no-header -o requirements-dev.lock`. Without `--python-version 3.10` the Python 3.10-only entries (`pillow` 12.x, `exceptiongroup`) are dropped and the 3.10 job breaks.
- Changing the supported Python range means updating the CI matrix, `sonar.python.version`, Ruff `target-version`, the lock's `--python-version` and the static Python badge in `README.md` together.

## Backends
- `--backend ollama` (default): `ollama` Python client, default host `http://localhost:11434`, default model `qwen3-vl:8b`.
- `--backend lm-studio`: `openai` client against LM Studio's OpenAI-compatible API, default host `http://localhost:1234`, images sent as base64 data URLs. `api_key="lm-studio"` is a required placeholder string, not a real credential.
- **Request timeout**: `--timeout` (default `DEFAULT_TIMEOUT` = 600s, must be > 0) is passed to both clients by `_create_client()`. It must cover the whole non-streamed reply, including model loading. A timeout raises in the worker and marks that image `FAILED`. The LM Studio client uses `max_retries=0`: the openai default (2) would resend a timed-out request to a server still busy with it.

## Core Rules & Architecture
- **Worker limit**: Max 4 concurrent workers (matches both backends' default concurrency limits). Default is 1. Enforced in CLI arg parsing (`1 <= workers <= 4`), not inside `process_directory()` itself.
- **Skip marker**: Files with `[PROCESSED BY AI]` in EXIF/XMP/GIF comment are skipped automatically (`is_already_processed()`).
- **Prompt source**: `prompt.txt` in the script directory takes precedence over the in-code `DEFAULT_PROMPT` fallback. If `prompt.txt` exists but cannot be read, execution aborts (`sys.exit(1)`).
- **Tag count & normalization**: Output is normalized via `normalize_tags()` (strip whitespace, lowercase, order-preserving deduplication, capped at 12 tags). Fewer than 6 valid tags after parsing marks that image as `FAILED`.
- **Tag parsing**: `parse_model_output()` first drops everything up to the last `</think>` (reasoning from thinking models), then tries several patterns in order:
  1. JSON array (`json.loads` on full string or bracketed `[...]` substring).
  2. Bullet points at line start (`[-•★●]`, minimum 6 items expected; splits each line on commas). Hyphens inside tags (`tag-1`) are not bullets.
  3. Numbered lists (`\d+\.`, minimum 6 items expected; splits each line on commas).
  4. Intro text: `tags`/`keywords` within the first ~40 chars, followed by a colon later on the same line (`Here are the tags for this image:`) or a dash right after (`Keywords -`). Parsed via `parse_text_tags()`, which drops common English stop words but keeps short tags like `3d`/`ui`.
  5. Comma- and/or newline-separated list fallback.
- **Concurrency & Locks**: Images are processed in parallel via `ThreadPoolExecutor`. `pyexiv2` is not thread-safe: all `pyexiv2` reads (`is_already_processed()`), writes (`write_metadata()`) and clears (`_clear_standard()`) are serialized through `metadata_lock = threading.Lock()`. Model API calls and Pillow operations (GIF read/write, format verification) are intentionally outside the lock to preserve concurrency.
- **Logging**: The `img_tagger` logger has a `NullHandler`, so without `--log` nothing is logged (no stray stderr warnings or tracebacks over the progress bar). The console shows results via `tqdm.write()`/`print()`. Problems the user must see either way go through `_warn()`, which both logs a warning and prints `  Warning: …` via `tqdm.write()`. These are pyexiv2/Pillow metadata read failures in `is_already_processed()` and the auto-heal re-save in `write_metadata()`. `--log` (`setup_logging()`) appends to the file with our logger at `DEBUG` and other libraries at `INFO`, which keeps httpx request lines and drops Pillow's per-chunk noise. The log records run settings, the prompt, each image's outcome and duration, raw model replies, tracebacks and a final summary.
- **Graceful quit**: Press `Q` during execution to trigger graceful shutdown. Monitored by a daemon thread (`listen_for_quit()`) using `msvcrt` on Windows or `termios`/`tty`/`select` on POSIX (with EOF detection for detached terminals). The POSIX loop reads the raw fd with `os.read()`, not `sys.stdin.read()`, so Python's buffer can't hide pending keys from `select()`. In-flight requests finish (or hit `--timeout`), but queued/unstarted tasks are marked `CANCELLED`.

## Metadata Schema
- **JPEG / WebP / PNG**:
  - EXIF: `Exif.Photo.UserComment` contains `"<tag1>, <tag2>, ... [PROCESSED BY AI]"`.
  - XMP: `Xmp.dc.subject` contains the raw tag list (`['tag1', 'tag2', ...]`); `Xmp.dc.description` contains `"Tags: <tag1>, <tag2>, ... | [PROCESSED BY AI]"`.
- **GIF**: Comment field only (no EXIF/XMP support). Stored as `"<tag1>, <tag2>, ... [PROCESSED BY AI]"`.
- **Metadata Clearing (`--clear`)**: `process_directory(clear=True)` delegates to `clear_directory()` → `clear_tags()` per file (`_clear_standard()` / `_clear_gif()`); no prompt/client/quit listener/report. Per-file failures are printed and logged, not raised. Strips EXIF, XMP, and IPTC (`img.clear_iptc()`) for standard images, and empties `comment=""` for GIFs. XMP needs `clear_xmp()` *and* `modify_raw_xmp("")`: on WebP, `clear_xmp()` alone leaves the XMP chunk in the saved file.

## File Replacement & Atomic Safety
- **Temp file placement**: Temporary files (`tempfile.mkstemp`) MUST always be created in the target image's directory (`dir=Path(image_path).parent`). This ensures replacements remain atomic on the same filesystem/mount point without cross-device link errors.
- **`robust_replace(src, dst)`**: Retries `src.replace(dst)` up to 10× with 0.5s delay upon `OSError` across **all platforms** (handles Windows file lock release and transient I/O locks).
- **Temp cleanup**: Always wrapped in `try...finally` using `temp_path.unlink(missing_ok=True)`.

## GIF Processing
- Frames are streamed via a generator during `Image.save()` (each frame copied and yielded one at a time) to avoid loading all frames into RAM, maintaining O(1) memory overhead even for large animated GIFs.
- Per-frame durations are extracted from `img.info` and preserved (defaulting to 100ms if missing).
- GIF tagging re-encodes the whole file through Pillow, so anything Pillow doesn't round-trip is lost: e.g. custom application extensions (`21 FF` blocks other than looping) are dropped.

## Animated WebP
README's known issue: the model might only see the first frame. Current state:
- Normal tagging/clearing goes through pyexiv2, which edits metadata in place: frames, per-frame durations and loop count survive.
- Auto-heal keeps the animation too: `_sanitize_with_pillow()` re-saves animated images (WebP, APNG) with `save_all=True` plus per-frame durations and loop.
- Untested what the model sees (probably only the first frame); `get_tags_lm_studio()` sends the whole file as `image/webp`.

## Non-standard PNG chunks
- pyexiv2 edits PNGs in place, so other text chunks (`tEXt`/`zTXt`/`iTXt`), `pHYs` (DPI) and private ancillary chunks survive tagging and clearing. Tagging adds an `iTXt` `XML:com.adobe.xmp` chunk; clearing removes it.
- The Pillow auto-heal re-save passes no `pnginfo`/`dpi`, so on that path other text chunks and DPI are lost.

## Metadata Auto-Healing & Sanitization
If `pyexiv2` raises a `RuntimeError` containing `"IFD"` or `"corrupt"`:
1. Re-save image with Pillow via `_sanitize_with_pillow()` (`quality=95` for lossy formats) to strip broken headers. Animated WebP/APNG keep all frames, durations and loop.
2. Retry metadata write/clear with pyexiv2 on the sanitized file.
*Caution*: Pillow re-saving can re-encode/compress lossy images (JPEG/WebP).

## Known Limitations & Maintenance Notes
- **Tests**: `python3 -m pytest` covers parsing, metadata round-trips for every format, GIF frame/duration preservation, auto-healing (simulated), temp-file cleanup, fake-backend pipeline, quit listener and CLI. CI runs them on Python 3.10–3.14 (Linux only). Tagging *quality* still needs a manual run with `--run-integration` against real images.
- **Known bugs**: none currently pinned. When adding one, pin it as a strict `xfail` (fixing it makes it XPASS → remove the marker).
- **Untested dependency minimums (future work)**: CI tests Python 3.10–3.14, but only against the versions in `requirements-dev.lock`. The `>=` lower bounds in `requirements.txt` were never tested as minimums. Known and accepted for now.
- **Linux-only CI**: nothing runs on Windows or macOS. The `msvcrt` quit listener is untested, and the POSIX quit-listener tests are skipped on Windows.
- **SonarQube false positives** (dismissed in Sonar; don't "fix" them in code): path traversal on `--log` in `setup_logging()` (operator-chosen path, tool is for interactive use); "always false" `OpenAI is None` in `_create_client()` (optional-import fallback, covered by `test_missing_openai_library`); regex-backtracking warnings on `parse_model_output()` patterns (measured linear on 200k-char adversarial inputs).
