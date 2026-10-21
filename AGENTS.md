# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Overview
- `img_tagger.py` — single-file CLI: tags JPEG/WebP/PNG/GIF files via a vision-language model on a local or LAN server (Ollama or LM Studio), writing tags into image metadata. `--clear` strips tags/metadata back out instead (used to reset images for testing; no model backend needed).
- `prompt.txt` — externalized LLM prompt; takes precedence over the `DEFAULT_PROMPT` fallback hardcoded in `img_tagger.py`.
- Flat repo layout: no package structure, not installable (`pyproject.toml` only holds Ruff and coverage config; no `setup.py`). Tests live in `tests/` (pytest, configured by `pytest.ini`). CI: GitHub Actions (see CI section).
- `.serena/` (tracked): Serena project config and memories (`core`, `conventions`, `suggested_commands`, `task_completion`, `tech_stack`, `memory_maintenance`) that condense this file. When a fact here changes, update the matching memory in the same change.
- Requires **Python 3.10+** (uses modern type annotations like `str | None` and `list[str]`).

## Build/Lint/Test Commands
Ruff (lint + format) is configured in `pyproject.toml`; CI fails on any Ruff finding or unformatted file. SonarQube Cloud (project `juusolatva_img_tagger`) runs in CI; keep functions under its cognitive-complexity limit of 15 by extracting `_private` helpers.
- Dependencies: `pip install -r requirements.txt` (or `pip3 install -r requirements.txt`); dev deps (pytest, pytest-cov, Ruff): `pip install -r requirements-dev.txt`
- Lint/format: `ruff check .` and `ruff format .` (CI runs `ruff format --check`). Use the Ruff version pinned in `requirements-dev.txt`.
- Run tests: `python3 -m pytest` (offline: images generated on the fly, model backends faked; ~15s). With coverage like CI: `python3 -m pytest --cov`
- Integration tests (opt-in, need a live backend + images in git-ignored `test_images/`; copies images to a temp dir, prints tags for manual quality review): `python3 -m pytest -m integration --run-integration -s [--tagger-backend lm-studio] [--tagger-host URL] [--tagger-model M] [--images-dir DIR]`. `--tagger-model` defaults to Ollama's `qwen3-vl:8b`, so with LM Studio also pass its model id. The `client` fixture uses `_create_client()`, so runs get `DEFAULT_TIMEOUT` and LM Studio's `max_retries=0`.
- Run tagger (Ollama, default): `python3 img_tagger.py <directory>`
- Run tagger (LM Studio): `python3 img_tagger.py <directory> --backend lm-studio --model qwen/qwen3-vl-8b` (LM Studio's own model id; see Backends)
- Recursive, custom model/workers: `python3 img_tagger.py <directory> -r --model <model> --workers 4`
- Clear all tags: `python3 img_tagger.py <directory> --clear [-r] [--workers N]`
- Help: `python3 img_tagger.py -h`
- Request timeout (seconds, default 600): `python3 img_tagger.py <directory> --timeout 1200`
- Logging: `python3 img_tagger.py <dir> --log output.log` (see Logging under Core Rules)
- Note: commands use `python3` (Linux/macOS); on Windows use `python` (`python3` there is often the Microsoft Store alias).

## CI
`.github/workflows/ci.yml` (GitHub Actions) runs on pushes to `main`, pull requests and manual dispatch:
- **Ruff**: `ruff check` and `ruff format --check --diff`. `ruff-action` reads the Ruff version from the `ruff==` pin in `requirements-dev.txt`.
- **Tests**: `pytest --cov --cov-report=xml` on Python 3.10, 3.11, 3.12, 3.13 and 3.14 (`fail-fast: false`). Integration tests are skipped (no backend). Installs from `requirements-dev.lock` with `--require-hashes --only-binary :all:`, so every locked package needs a wheel for every matrix version. The 3.14 job uploads `coverage.xml` as an artifact.
- **SonarQube Cloud**: runs after the tests and scans with the downloaded `coverage.xml`. Settings are in `sonar-project.properties` (sources `.`, `tests/**` excluded and treated as tests, `sonar.python.version` 3.10–3.14). Needs the `SONAR_TOKEN` repo secret. Coverage is configured in `[tool.coverage.run]` in `pyproject.toml` (branch coverage, `tests/` omitted, `relative_files = true` so Sonar can map the paths in `coverage.xml` to its sources).
- Third-party actions are pinned to commit SHAs with a `# vX.Y.Z` comment. GitHub's own `actions/*` use major-version tags.
- **`requirements-dev.lock`**: hash-locked, cross-platform lock of `requirements-dev.txt` (and thus `requirements.txt`) for Python ≥3.10. Only CI installs it; end users still get the `>=` bounds. After changing either requirements file (or to bump versions), regenerate it with `uv pip compile requirements-dev.txt --universal --python-version 3.10 --generate-hashes --no-header -o requirements-dev.lock`. Without `--python-version 3.10` the old-Python-only entries (`pillow` 12.x, `exceptiongroup`, `tomli`) are dropped and the 3.10 job breaks.
- Changing the supported Python range means updating the CI matrix, `sonar.python.version`, Ruff `target-version`, the lock's `--python-version` and the static Python badge in `README.md` together.

## Backends
- `--backend ollama` (default): `ollama` Python client, default host `http://localhost:11434`. `get_tags_ollama()` passes the image *path* in `images`; the client reads and base64-encodes the file itself, so a remote Ollama needs no shared filesystem.
- `--backend lm-studio`: `openai` client against LM Studio's OpenAI-compatible API, default host `http://localhost:1234`. `get_tags_lm_studio()` sends the file as a base64 data URL whose MIME type comes from the Pillow-detected format (fallback `image/jpeg`), not the extension. `api_key="lm-studio"` is a required placeholder string, not a real credential.
- **What the model gets**: the original file, whole and unmodified (no resizing, no frame extraction), so for animated GIF/WebP/APNG the server decodes only the first frame (see Animated GIF & WebP).
- **`--model`**: one default for both backends, `qwen3-vl:8b`, which is Ollama naming. LM Studio ids differ (e.g. `qwen/qwen3-vl-8b`; list them at `<host>/v1/models`), so with LM Studio `--model` must always be passed.
- **LM Studio vision setup** (found by testing, not visible in code): a GGUF model only counts as vision-capable (`type: "vlm"` in `<host>/api/v0/models`) once its vision projector `mmproj-*.gguf` is downloaded; otherwise every image fails with HTTP 400 `... does not support image inputs`. LM Studio loads the model on the first request, so the first image is slower.
- **`--host`**: no argparse default; `__main__` fills in the backend's localhost URL, so the ollama client never falls back to `OLLAMA_HOST`. The ollama client normalizes hosts (`192.168.1.10` → `http://192.168.1.10:11434`); LM Studio uses `f"{host}/v1"` verbatim, so pass `http://host:port` without `/v1`. Servers on another LAN machine work.
- **Request timeout**: `--timeout` (default `DEFAULT_TIMEOUT` = 600s, must be > 0; `nan` is rejected explicitly with `math.isnan()` because `nan <= 0` is false) is passed to both clients by `_create_client()`. It must cover the whole non-streamed reply, including model loading. A timeout raises in the worker and marks that image `FAILED`. The LM Studio client uses `max_retries=0`: the openai default (2) would resend a timed-out request to a server still busy with it.

## Core Rules & Architecture
- **Pipeline**: `process_directory()` → `_find_images()` (extension filter `IMAGE_EXTENSIONS`, `iterdir()`/`rglob("*")`) → `_load_prompt()` → `_create_client()` → quit listener → `_run_tasks()` (`ThreadPoolExecutor` + `as_completed` + tqdm; each `process_single_image()` result `(status, name, message, duration)` goes to `_RunStats.record()`) → `_print_report()`. Per image: `get_image_format()` (Pillow verify; invalid → `FAILED`; a format outside `TAGGABLE_FORMATS`, e.g. BMP or MPO, → `FAILED` before any model call) → `is_already_processed()` (`SKIPPED`) → stop check (`CANCELLED`) → backend call → `parse_model_output()` → `tag_image()`.
- **Format dispatch**: `tag_image()`, `is_already_processed()` and `clear_tags()` all route on the Pillow-detected format, not the extension (a PNG named `.gif` is tagged, detected and cleared via pyexiv2). The extension decides only when Pillow can't read the file (`_is_gif()`).
- **Worker limit**: Max 4 concurrent workers (matches both backends' default concurrency limits). Default is 1. Enforced in CLI arg parsing (`1 <= workers <= 4`), not inside `process_directory()` itself.
- **Skip marker**: Files with `[PROCESSED BY AI]` are skipped automatically (`is_already_processed()`). JPEG/WebP/PNG: any EXIF or XMP value (`_pyexiv2_has_marker()`); if pyexiv2 finds none or fails, any string in Pillow's `img.info` (`_pillow_has_marker()`, e.g. PNG text chunks). GIF: the comment only. Unreadable metadata → `_warn()` and treated as not tagged.
- **Prompt source**: `prompt.txt` in the script directory takes precedence over the in-code `DEFAULT_PROMPT` fallback. If `prompt.txt` exists but cannot be read, execution aborts (`sys.exit(1)`).
- **Tag count & normalization**: Output is normalized via `normalize_tags()` (strip whitespace, lowercase, order-preserving deduplication, capped at 12 tags). Nothing else is rewritten or filtered: underscores stay (Qwen sometimes replies `digital_art`), and so do non-English tags (Qwen models occasionally emit a Chinese tag despite the English-only prompt). Deliberately unfiltered: `prompt.txt` may ask for tags in any language. Fewer than 6 valid tags after parsing marks that image as `FAILED`.
- **Tag parsing**: `parse_model_output()` first drops everything up to the last `</think>` (reasoning from thinking models), then tries several patterns in order:
  1. JSON array (`json.loads` on full string or bracketed `[...]` substring).
  2. Bullet points at line start (`[-•★●]`, minimum 6 items expected; splits each line on commas). Hyphens inside tags (`tag-1`) are not bullets.
  3. Numbered lists (`\d+\.`, minimum 6 items expected; splits each line on commas).
  4. Intro text: `tags`/`keywords` within the first ~40 chars, followed by a colon later on the same line (`Here are the tags for this image:`) or a dash right after (`Keywords -`). Parsed via `parse_text_tags()`, which drops common English stop words but keeps short tags like `3d`/`ui`.
  5. Comma- and/or newline-separated list fallback.

  Only the JSON pattern falls through when it yields fewer than 6 tags; a matched bullet/numbered/intro pattern returns its result (or `None` → `FAILED`) without trying later patterns.
- **Concurrency & Locks**: Images are processed in parallel via `ThreadPoolExecutor`. `pyexiv2` is not thread-safe: all `pyexiv2` reads (`_pyexiv2_has_marker()`), writes (`write_metadata()`) and clears (`_clear_standard()`) are serialized through `metadata_lock = threading.Lock()`. In `write_metadata()` the lock also covers the auto-heal re-save and `robust_replace()`; `_clear_standard()` holds it only around pyexiv2. Model API calls and other Pillow operations (GIF read/write, format verification, the skip-check fallback) are intentionally outside the lock to preserve concurrency.
- **Logging**: The `img_tagger` logger has a `NullHandler`, so without `--log` nothing is logged (no stray stderr warnings or tracebacks over the progress bar). The console shows results via `tqdm.write()`/`print()`. Problems the user must see either way go through `_warn()`, which both logs a warning and prints `  Warning: …` via `tqdm.write()`. These are pyexiv2/Pillow metadata read failures in `is_already_processed()` and the auto-heal re-save in `write_metadata()`. `--log` (`setup_logging()`) appends to the file with our logger at `DEBUG` and other libraries at `INFO`, which keeps httpx request lines and drops Pillow's per-chunk noise. The log records run settings, the prompt, each image's outcome and duration, raw model replies, tracebacks and a final summary.
- **Console encoding**: `__main__` reconfigures `sys.stdout` with `errors="replace"`. Redirected output on Windows uses the ANSI code page (e.g. cp1252), which can't encode the `[✓]` success prefix or many file names; without this every success was counted as a failure and a non-ASCII name aborted the run. Tests that call functions directly don't get it (`test_cli.py` covers it via a subprocess with `PYTHONIOENCODING=ascii`).
- **Graceful quit**: Press `Q` during execution to trigger graceful shutdown. Monitored by a daemon thread (`listen_for_quit()`): `_wait_for_quit_windows()` (`msvcrt`) on Windows; on POSIX `_cbreak_stdin()` + `_wait_for_quit_posix()` (`termios`/`tty`/`select`, EOF detection; plain reads with `idle_sleep=0.1` when stdin isn't a tty). The POSIX loop reads the raw fd with `os.read()`, not `sys.stdin.read()`, so Python's buffer can't hide pending keys from `select()`. In-flight requests finish (or hit `--timeout`). Queued tasks still run the format and skip checks, then return `CANCELLED`, which is neither printed nor counted. `process_directory()` sets `stop_event` in its `finally` after every run, so the listener exits (restoring the POSIX terminal) instead of being waited out by `join(timeout=2)`.

## Metadata Schema
- **JPEG / WebP / PNG**:
  - EXIF: `Exif.Photo.UserComment` contains `"<tag1>, <tag2>, ... [PROCESSED BY AI]"`.
  - XMP: `Xmp.dc.subject` contains the raw tag list (`['tag1', 'tag2', ...]`); `Xmp.dc.description` contains `"Tags: <tag1>, <tag2>, ... | [PROCESSED BY AI]"`.
  - Only these three fields are replaced; other EXIF/XMP/IPTC survives tagging (unless auto-heal runs).
- **GIF**: Comment field only (no EXIF/XMP support). Stored as `"<tag1>, <tag2>, ... [PROCESSED BY AI]"`, replacing any existing comment.
- **Metadata Clearing (`--clear`)**: `process_directory(clear=True)` delegates to `clear_directory()` → `clear_tags()` per file (`_clear_standard()` / `_clear_gif()`); no prompt/client/quit listener/report. Per-file failures are printed and logged, not raised. Strips EXIF, XMP, and IPTC (`_clear_all()`) for standard images, and empties `comment=""` for GIFs (every GIF is re-encoded, tagged or not). XMP needs `clear_xmp()` *and* `modify_raw_xmp("")`: on WebP, `clear_xmp()` alone leaves the XMP chunk in the saved file. `clear_comment()` is never called, so JPEG `COM` and PNG `Description` comments survive.

## File Replacement & Atomic Safety
- **Temp file placement**: Temporary files (`tempfile.mkstemp`) MUST always be created in the target image's directory (`dir=Path(image_path).parent`). This ensures replacements remain atomic on the same filesystem/mount point without cross-device link errors.
- **pyexiv2 never gets a path**: `_modify_with_pyexiv2()` reads the temp file's bytes into `pyexiv2.ImageData`, applies the edit and writes `get_bytes()` back with Python; `_pyexiv2_has_marker()` reads via `ImageData` too. On Windows pyexiv2 can't open paths with non-ASCII characters in the file name *or any folder* (`encoding="utf-8"` fails; `"mbcs"` covers only the ANSI code page), and the temp file sits in the image's folder. Never pass a path to `pyexiv2.Image`. (`ImageData` holds the whole file in memory and refuses files ≥2 GB.)
- **Permissions**: standard formats copy the original with `shutil.copy2` (mode and times kept); GIFs are written to the fresh `mkstemp` file (0600 on POSIX), so `write_gif_tags()`/`_clear_gif()` call `shutil.copymode()` before replacing.
- **`robust_replace(src, dst)`**: Retries `src.replace(dst)` up to 10× with 0.5s delay upon `OSError` across **all platforms** (handles Windows file lock release and transient I/O locks).
- **Temp cleanup**: Always wrapped in `try...finally` using `temp_path.unlink(missing_ok=True)`.

## GIF Processing
- Frames reach `Image.save()` through a generator (`append_images=frame_generator()`), but this does not bound memory: Pillow's GIF writer collects every frame before writing, so peak memory grows with frame count × frame size.
- Per-frame durations are extracted from `img.info` and preserved (defaulting to 100ms if missing). Pillow merges identical consecutive frames on save (durations summed), so the frame count can drop; tests use all-different frames for this reason (`make_gif()`).
- The loop count is kept only if the source has one (`_gif_loop_kwargs()`): a GIF without it plays once, and saving with `loop=0` would make it loop forever.
- GIF tagging and clearing re-encode the whole file through Pillow, so anything Pillow doesn't round-trip is lost: e.g. custom application extensions (`21 FF` blocks other than looping) are dropped.

## Animated GIF & WebP
README's known issue: the model only sees the first frame. Neither backend extracts frames (see Backends); manual runs in 2026-10 confirmed it for animated GIFs on both backends (a white first frame was tagged `blank`, `white`). Animated WebP takes the same path, untested.
- Normal WebP tagging/clearing goes through pyexiv2, which edits metadata in place: frames, per-frame durations and loop count survive.
- Auto-heal keeps the animation too: `_sanitize_with_pillow()` re-saves animated images (WebP, APNG) with `save_all=True` plus per-frame durations and loop.

## Non-standard PNG chunks
- pyexiv2 edits PNGs in place, so other text chunks (`tEXt`/`zTXt`/`iTXt`), `pHYs` (DPI) and private ancillary chunks survive tagging and clearing. Tagging adds an `eXIf` chunk and an `iTXt` `XML:com.adobe.xmp` chunk; clearing removes both. Exiv2 rewrites a `tEXt` `Description` (its PNG comment) as `iTXt`, keeping the text.
- The Pillow auto-heal re-save passes no `pnginfo`/`dpi`, so on that path other text chunks and DPI are lost.

## Metadata Auto-Healing & Sanitization
If `pyexiv2` raises a `RuntimeError` whose message contains `IFD` or `corrupt` (case-insensitive):
1. Re-save the original into the temp file with Pillow via `_sanitize_with_pillow()` (`quality=95`) to strip broken headers. Animated WebP/APNG keep all frames, durations and loop. The format is the detected one.
2. Tagging (`write_metadata()`): retry the pyexiv2 write once on the sanitized file; a second failure propagates (`FAILED`). Clearing (`_clear_standard()`): no retry, the Pillow re-save *is* the clear (Pillow writes no EXIF/XMP/IPTC by default).

*Caution*: the re-save re-encodes JPEG/WebP (no `lossless=True`, so lossless WebP becomes lossy) and keeps only pixels and animation: EXIF (incl. Orientation, so photos may show rotated), XMP, IPTC, DPI and, for JPEG/WebP, the ICC profile are dropped.

## Known Limitations & Maintenance Notes
- **Tests**: `python3 -m pytest` covers parsing, metadata round-trips for every format, non-ASCII file and folder names, mislabeled extensions, GIF frame/duration/loop preservation, auto-healing (simulated), temp-file cleanup, fake-backend pipeline, quit listener and CLI. CI runs them on Python 3.10–3.14 (Linux only). Tagging *quality* still needs a manual run with `--run-integration` against real images.
- **Known bugs**: none currently pinned. When adding one, pin it as a strict `xfail` (fixing it makes it XPASS → remove the marker).
- **Read-only files on Windows**: `shutil.copy2` copies the read-only attribute to the temp file, so tagging/clearing fails after the model call and the read-only temp file can't be unlinked (left behind as `tmpXXXX.tmp`). Read-only GIFs fail in `robust_replace()` instead and leave nothing.
- **Untested dependency minimums (future work)**: CI tests Python 3.10–3.14, but only against the versions in `requirements-dev.lock`. The `>=` lower bounds in `requirements.txt` were never tested as minimums. Known and accepted for now.
- **Linux-only CI**: nothing runs on Windows or macOS in CI. The offline suite was run by hand on Windows 11 + Python 3.14 (2026-10: all pass; the POSIX-only quit-listener and permission tests skip). The `msvcrt` quit listener (Windows `Q`) is still untested.
- **SonarQube false positives** (dismissed in Sonar; don't "fix" them in code): path traversal on `--log` in `setup_logging()` (operator-chosen path, tool is for interactive use); "always false" `OpenAI is None` in `_create_client()` (optional-import fallback, covered by `test_missing_openai_library`); regex-backtracking warnings on `parse_model_output()` patterns (measured linear on 200k-char adversarial inputs).
