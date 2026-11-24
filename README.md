# img tagger

[![CI](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=coverage)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/github/license/juusolatva/img_tagger)](LICENSE)

A Python script that tags every **JPEG**, **WebP**, **PNG** and **GIF** in a folder (optionally with its subfolders). It sends each image to a vision-language model running in **Ollama** or **LM Studio**, on your own computer or another machine in your network, and writes the returned tags into the image's own metadata (EXIF and XMP, or the comment for GIFs), so they travel with the file.

img tagger uses no cloud service: images go only to the model server you choose. (Ollama's `-cloud` models run on ollama.com, so use a local model if your images must stay on your network.)

**Contents:** [Features](#features) · [Installation](#installation) · [Setting up a model backend](#setting-up-a-model-backend) · [Usage](#usage) · [What gets written to your images](#what-gets-written-to-your-images) · [Customising the prompt](#customising-the-prompt) · [Output](#output) · [Stopping early](#stopping-early) · [Clearing tags](#clearing-tags) · [Choosing a model and performance](#choosing-a-model-and-performance) · [Troubleshooting](#troubleshooting) · [Known limitations](#known-limitations) · [Development](#development)

## Features

- Tags JPEGs, WebPs, PNGs and GIFs, including animated ones (the animation is kept)
- Works with Ollama (default) or LM Studio, locally or on another machine
- Writes 6 to 12 lowercase tags per image into standard metadata fields
- Skips images it has already tagged, so you can safely run it again on the same folder
- Processes 1 to 4 images at a time
- Copes with chatty model replies (JSON, bullet lists, "Here are the tags:" intros, reasoning from thinking models)
- Writes through a temporary file in the same folder, so an interrupted run never leaves a half-written image
- Press `Q` to stop early and still get a report
- `--clear` strips the metadata back out
- The prompt lives in an editable [`prompt.txt`](prompt.txt)

## Installation

You need:

- [Python](https://www.python.org/downloads/) **3.13 or newer** (tested on 3.13 and 3.14; check with `python --version`). On macOS, Apple's bundled `python3` may be too old.
- [Ollama](https://ollama.com/download) or [LM Studio](https://lmstudio.ai/download) with a vision-capable model. A GPU makes a big difference to speed.

It runs on Linux and Windows (tested in CI and on Windows 11). It has not been tried on macOS.

```bash
git clone https://github.com/juusolatva/img_tagger.git
cd img_tagger
python3 -m venv .venv              # Windows: python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
```

- On Debian and Ubuntu, install `python3-venv` first if creating the virtual environment fails. Without a virtual environment, many Linux distributions refuse `pip install` with `externally-managed-environment`.
- If PowerShell says running scripts is disabled, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, or use Command Prompt and `.venv\Scripts\activate.bat`.
- Activate the virtual environment again in each new terminal. There's nothing else to install: you run `img_tagger.py` from the folder.

The packages are `ollama` and `openai` (the two backends), `pillow` (image formats, the copy sent to the model), `pyexiv2` (EXIF/XMP, with exiv2 built in, so no exiftool needed) and `tqdm` (progress bar). Install all of them even if you only use one backend or `--clear`.

> The examples use `python`. On Linux and macOS outside a virtual environment, use `python3`.

## Setting up a model backend

### Ollama

1. Install [Ollama](https://ollama.com/download) and make sure it's running.
2. Download the default model: `ollama pull qwen3-vl:8b`
3. Run `python img_tagger.py path/to/images`. The defaults (`--backend ollama`, `--host http://localhost:11434`, `--model qwen3-vl:8b`) already match.

For another vision model, pull it and pass its name with `--model`, e.g. `--model qwen3-vl:4b-instruct` for GPUs with little memory.

### LM Studio

1. Install [LM Studio](https://lmstudio.ai/download) and download a vision model, e.g. Qwen3 VL 8B. For a GGUF model, also download its **vision projector** (`mmproj-*.gguf`); without it every image fails with `does not support image inputs`.
2. Start LM Studio's local server (`http://localhost:1234`).
3. Run with `--backend lm-studio` and **LM Studio's model id**. The `--model` default `qwen3-vl:8b` is Ollama's name, so with LM Studio always pass it:

   ```bash
   python img_tagger.py path/to/images --backend lm-studio --model qwen/qwen3-vl-8b
   ```

The model ids are listed at <http://localhost:1234/v1/models>. LM Studio loads the model on the first request, so the first image is slower.

### Using a server on another machine

Pass `--host`. The server must accept network connections: for Ollama set `OLLAMA_HOST=0.0.0.0` on the server before starting it; in LM Studio turn on **Serve on Local Network**. A firewall may need to allow port 11434 (Ollama) or 1234 (LM Studio). img tagger never reads `OLLAMA_HOST` on your own computer; always pass `--host`.

- **Ollama** accepts `http://192.168.1.50:11434`, `192.168.1.50:11434` or `192.168.1.50`. Note that `http://192.168.1.50` without a port means port 80.
- **LM Studio** needs the full address with `http://` and the port, without `/v1`:

  ```bash
  python img_tagger.py path/to/images --backend lm-studio --host http://192.168.1.50:1234 --model qwen/qwen3-vl-8b
  ```

img tagger talks only to the address you gave: redirects aren't followed (the request fails instead), and credentials from your environment (`OLLAMA_API_KEY`, `OPENAI_ORG_ID`/`OPENAI_PROJECT_ID`) are not sent.

## Usage

```bash
python img_tagger.py path/to/images
```

> [!IMPORTANT]
> img tagger changes your images in place. It overwrites existing XMP keywords and description and the EXIF user comment, replaces every GIF comment, and re-encodes images with corrupted metadata (see [What gets written](#what-gets-written-to-your-images)). Try it on copies first, and back up anything you can't replace.

### Options

| Option | Default | Description |
|---|---|---|
| `directory` | (required) | The folder with your images. Quote paths with spaces on Windows. |
| `-r`, `--recursive` | off | Include all subfolders. |
| `--backend` | `ollama` | `ollama` or `lm-studio`. |
| `--host` | `http://localhost:11434` (Ollama), `http://localhost:1234` (LM Studio) | Address of the model server. |
| `--model` | `qwen3-vl:8b` | Model to use. With LM Studio, pass its id, e.g. `qwen/qwen3-vl-8b`. |
| `--workers` | `1` | Images processed at the same time, 1 to 4. |
| `--timeout` | `600` | Seconds to wait for one image's answer, including model loading. Raise it for slow hardware. |
| `--max-pixels` | `1` | Largest size in megapixels of the copy sent to the model; bigger images are scaled down. `0` sends the original file. |
| `--log` | off | Append a detailed log to this file (must end in `.log`). |
| `--clear` | off | Remove metadata instead of tagging. See [Clearing tags](#clearing-tags). |

### Examples

```bash
# A folder and all its subfolders, with Ollama
python img_tagger.py ~/Pictures/memes -r

# LM Studio, 4 workers, with a log
python img_tagger.py ~/Pictures/memes --backend lm-studio --model qwen/qwen3-vl-8b --workers 4 --log run.log

# Ollama on another machine, a smaller model, more time per image
python img_tagger.py ~/Pictures/memes --host http://192.168.1.50:11434 --model qwen3-vl:4b-instruct --timeout 1200
```

On Windows, write full paths (`"C:\Users\you\Pictures\memes"`): Command Prompt and PowerShell 5.1 don't expand `~`.

### Which files are processed

- Files ending in `.jpg`, `.jpeg`, `.png`, `.webp` or `.gif` (any letter case, hidden files included). Other files are ignored.
- img tagger goes by the image's real format, not its extension: a PNG named `.gif` is tagged as a PNG. Files that aren't valid images fail with `Unreadable image`, and images in other formats (BMP, MPO, ...) fail with `Unsupported file format`. Neither is sent to the model.
- Files over 256 MiB fail without being read.
- **Folder rules** (they stop other users from swapping files under img tagger):
  - Symlinked images and folders are refused; pass the real folder.
  - A `..` is allowed only at the start of the path (`../memes` works, `photos/../memes` doesn't).
  - On Linux and macOS, an image's folder must belong to you (or root) and must not be writable by its group or others. Folders created with `umask 0002` (common on Ubuntu) are mode `775` and refused; fix them with `chmod go-w <folder>`. With `-r`, images in a refused subfolder fail one by one and the rest continue.

### Exit codes

- `0`: the run finished, even if some images failed (also after `Q` or when no images were found).
- `1`: an `Error: ...` before any image, e.g. the folder is missing or refused, an option value is out of range, the log can't be opened, `prompt.txt` exists but is unreadable or empty, or the model server can't be reached or doesn't have the model.
- `2`: an invalid option (unknown `--backend`, a non-number for `--workers`, ...).

## What gets written to your images

### Where the tags go

**JPEG, WebP and PNG:**

| Field | Content |
|---|---|
| EXIF `Exif.Photo.UserComment` | `meme, cat, funny, reaction, text, digital_art [PROCESSED BY AI]` |
| XMP `Xmp.dc.subject` | The tags as a list: `meme`, `cat`, `funny`, ... |
| XMP `Xmp.dc.description` | `Tags: meme, cat, funny, reaction, text, digital_art \| [PROCESSED BY AI]` |

**GIF** has no EXIF or XMP, so the tags **replace the GIF's comment**: `meme, cat, funny, ... [PROCESSED BY AI]`.

To read them back, use e.g. [ExifTool](https://exiftool.org/): `exiftool -XMP:Subject -UserComment photo.jpg` or `exiftool -Comment party.gif`. Which photo apps display these fields hasn't been checked yet.

### How the tags are cleaned up

- Trimmed, lowercased and deduplicated, in the model's order; at most 12 are kept.
- Fewer than 6 usable tags → the image fails with `Invalid or insufficient tags returned from model` and nothing is written.
- Underscores and language are left alone, so `digital_art` and `digital art` can both appear, and Qwen models occasionally slip in a Chinese tag.

### Already tagged images are skipped

An image whose metadata contains `[PROCESSED BY AI]` anywhere (any EXIF or XMP value or PNG text chunk; for GIFs, the comment) is skipped without contacting the model, even if another tool added the marker. Failed images get no marker, so running the same command again retries only those.

There's no option to force re-tagging. Remove the marker from both `Exif.Photo.UserComment` and `Xmp.dc.description` (or the GIF comment), or run [`--clear`](#clearing-tags) on a folder of copies.

### What happens to existing metadata

Tagging replaces only the three fields above. Everything else (other EXIF such as orientation and camera data, other XMP, all IPTC, the JPEG comment, PNG text chunks such as Stable Diffusion's `parameters`, DPI) is kept. Existing **XMP keywords are lost**, and **IPTC keywords are not updated**, so apps that read IPTC may still show old keywords.

### How the files are changed

- JPEG, WebP and PNG: only the metadata is edited; the image data isn't re-encoded, and animated WebPs keep their frames and timing.
- GIF: only the comment blocks change; frames, colours, transparency and timing stay byte for byte the same. A `GIF87a` file becomes `GIF89a` when it gets a comment.
- The new version is written to a temporary `tmpXXXX.tmp` file in the same folder and then replaces the original. If the original is locked by another program, replacing is retried for 5 seconds.
- If the image changed while the model was working on it, nothing is written (`File changed during processing`).
- Permissions are kept: the file mode and group (or, if the group can't be kept, permissions are narrowed with a warning), Linux ACLs and `user.*` attributes, and on Windows the NTFS permissions and read-only flag. Timestamps are not kept, and on Windows the owner becomes your account. An EFS-encrypted image on Windows is only replaced if the new file is encrypted too (i.e. its folder is encrypted).

### Repairing corrupted metadata

If pyexiv2 reports broken metadata, img tagger prints `Warning: Corrupted metadata in <name> ...; re-saving it with Pillow`, re-saves the image with Pillow and tags the repaired copy. The repair has side effects:

| Format | Effect |
|---|---|
| JPEG | Re-encoded (quality 95). EXIF (incl. orientation and GPS), XMP, IPTC, ICC profile and DPI are dropped, so a photo may show up rotated. |
| WebP | Re-encoded as **lossy** (quality 95), even if it was lossless. EXIF, XMP, IPTC and ICC profile are dropped. |
| PNG | Stays lossless with its ICC profile, but loses text chunks, DPI, EXIF, XMP and IPTC. |
| Animated WebP / APNG | Keep frames, timing and loop count. Very large animations (over 250 million pixels in total) fail with `Animation too large to repair`. |

## Customising the prompt

Edit [`prompt.txt`](prompt.txt) to change what kind of tags you get. It's read (as UTF-8) from the folder of `img_tagger.py`, not the current folder. If it's missing, a built-in copy of the default prompt is used with a warning; if it exists but is unreadable or empty, the run stops.

The model must reply with **at least 6** tags. A comma-separated list is simplest; JSON lists, bullet or numbered lists and lists after an intro like `Here are the tags:` work too. Entries over 64 characters are dropped as sentences, a reply starting with an English refusal (`I'm sorry, I can't…`) fails, and anything before a thinking model's last `</think>` is ignored.

The default prompt asks for 6 to 12 English tags with the image type first (`meme`, `screenshot`, `photo`, ...), plus specific guidance for memes and screenshots.

## Output

Before the first image, img tagger checks that the server is reachable and lists your model (waiting at most 10 seconds). If not, it prints `Error: ...` with the available models and exits with 1, even if every image is already tagged.

Then a progress bar runs and each image prints a line as it finishes (with several workers, not in folder order):

```
  [✓] cat.jpg -> Generated Tags: ['meme', 'cat', 'funny', 'digital_art', 'reaction', 'text']
  [-] dog.png -> Skipped: Already Tagged
  [!] notimage.jpg -> Unreadable image (unsupported or corrupted file)
```

Metadata problems are shown as `  Warning: ...` lines. At the end comes a report:

```
==================================================
                PROCESSING REPORT
==================================================
 Processed images: 4
 Skipped images: 0
 Failed images: 1
 Total time elapsed: 0h 1m 11.24s
 Average processing time: 17.81 seconds

--- Failed files details ---
 * notimage.jpg -> Unreadable image (unsupported or corrupted file)
==================================================
```

"Processed" counts images tagged in this run; the average covers only those.

### Log file

`--log FILE` appends a detailed UTF-8 log, the first place to look when something goes wrong: run settings, the prompt, the server check, each image's request, **raw model reply** (cut at 4000 characters), tags, timing and full tracebacks, and HTTP requests. Missing folders are created. When the screen shows only `Connection error.`, the log usually has the real cause.

The log contains file paths and model replies, so check it before sharing. For safety the name must end in `.log`, an existing log must be a regular file you own (not a symlink), and a new log is readable only by you.

## Stopping early

Press `Q` (no Enter) while images are being tagged. Images in progress finish (or time out), queued images are cancelled without being counted, and the report is printed. The stop message appears when the next image finishes.

- Keys typed during a run go to the quit listener (on Linux and macOS they aren't echoed until the run ends).
- `Q` isn't available with `--clear`. On Linux and macOS it also isn't available when input is empty (`</dev/null`), and with piped input a `q` in the input stops the run.
- **Ctrl+C doesn't stop cleanly**: queued images keep going and you get a traceback with no report. Use `Q`. If you have to close the terminal, an image being written may leave a `tmpXXXX.tmp` file, which you can delete.

## Clearing tags

```bash
python img_tagger.py path/to/images --clear
```

> [!WARNING]
> `--clear` removes **all** EXIF, XMP and IPTC metadata from every JPEG, WebP and PNG in the folder (and subfolders with `-r`), not just the tags: camera settings, dates, GPS, author, copyright, orientation and other apps' keywords. It starts without confirmation and can't be undone. It's meant for resetting test images.

- Kept: the JPEG comment, PNG text chunks and DPI. A marker in a PNG text chunk still causes a skip afterwards; remove it with a metadata editor.
- GIFs: every comment is removed; nothing else changes.
- Invalid or unsupported files are left unchanged and reported as failed. Corrupted metadata is [repaired](#repairing-corrupted-metadata) by re-saving with Pillow.
- No model server or `prompt.txt` is needed. `-r`, `--workers` and `--log` work as usual; there's no progress bar, report or `Q`. The exit code is 0 even if some files failed.

## Choosing a model and performance

- Any model that accepts images should work; the default is Qwen3 VL 8B (`qwen3-vl:8b` in Ollama, `qwen/qwen3-vl-8b` in LM Studio). Thinking models work too but are slower.
- **Speed depends mostly on the GPU and the model.** The model should fit in GPU memory; anything that spills to the CPU is much slower. `ollama ps` shows the split. If it doesn't fit, use a smaller model (`qwen3-vl:4b-instruct` on 6 GB cards) or a shorter context (`OLLAMA_CONTEXT_LENGTH` on the server; tagging needs little context).
- `--timeout` applies per image. A timed-out image fails and is retried on the next run.
- `--workers` up to 4 matches both servers' default parallel requests. Extra requests wait on the server, and that wait counts towards `--timeout`.
- **Images are scaled down** to 1 megapixel by default (never up). With Qwen3 VL 4B a 12-megapixel photo took 29 s as is and 5 s at 1 MP with the same tags; small diagram text was still read at 1 MP but not at 0.5. Ollama enlarges smaller images anyway, so going lower saves nothing there. Raise it (`--max-pixels 2`) for screenshots with tiny text.
- The copy sent is the first frame, turned upright, as PNG or JPEG **without metadata**. With `--max-pixels 0`, or if the copy can't be made (e.g. a truncated image), the **original file is sent, including metadata such as GPS location**; only the log records that fallback.

## Troubleshooting

| Message | What to do |
|---|---|
| `ModuleNotFoundError: No module named 'pyexiv2'` (or another package) | Activate your virtual environment and run `python -m pip install -r requirements.txt`. |
| `Could not reach the Ollama server ...` | Start Ollama or check `--host` (`http://<ip>` without a port means port 80). For another machine see [above](#using-a-server-on-another-machine). |
| `Could not reach the LM Studio server ...: Connection error.` | Check the server is running. `--host` must start with `http://` and not end in `/v1`. Run with `--log` for the real cause. |
| `Error code: 307` (or another 3xx) | The server redirected the request, which isn't followed. Pass the address it redirects to. |
| `Could not reach ...: timed out` | No answer within 10 seconds: the machine is off, the address is wrong, or a firewall blocks it. |
| `The ... server at ... has no model '<name>'` | Use one of the listed models. Ollama: `ollama pull <name>`. LM Studio: use its id, not `qwen3-vl:8b`. |
| `... does not support image inputs` (LM Studio) | Download the model's vision projector (`mmproj-*.gguf`) or use another vision model. |
| HTML `Internal Server Error` on the first images (LM Studio) | Requests arrived while the model was loading (with `--workers` above 1). Run again, or load the model first. |
| `timed out` / `Request timed out.` after a long wait | Raise `--timeout`, use fewer `--workers` or a faster model. |
| Every image fails with a model error | The server check only confirms the model is listed. Run with `--log` to see the server's error. |
| `Invalid or insufficient tags returned from model` | Fewer than 6 usable tags. Check the raw reply with `--log`, try another model, or review your `prompt.txt`. |
| `Image folder must not be writable by its group or other users (chmod go-w)` | Run `chmod go-w <folder>` if nobody else should change files in it. |
| `File changed during processing` | The image was edited while being tagged. Nothing was written; run again. |
| `Unsupported file format: MPO` (or `BMP`, ...) | The file's real format isn't supported. Convert it. |
| `Access is denied: '...\tmpXXXX.tmp'` or `Failed to replace ...` (Windows) | Another program held the image locked. Close it and run again. On FAT32/exFAT or network drives, clear the read-only attribute first. |
| `The folder '<folder>' could not be located.` | Check the path; on Windows quote spaces and don't use `~`. |
| `No valid images found in '<folder>'.` | No supported files there. Add `-r` if they're in subfolders. |

## Known limitations

- **Animated images**: the model sees only the first frame, so an animation with a blank first frame gets tags like `blank, white`.
- **Original-file sends** (`--max-pixels 0` or a failed copy) include metadata and aren't rotated upright.
- **Repairs** of corrupted metadata re-encode JPEG/WebP and drop other metadata.
- **Keywords**: IPTC keywords aren't updated, and existing XMP keywords are replaced.
- **No forced re-tagging**: tagged images are always skipped.
- **MPO JPEGs** (several images in one file, from some cameras and phones) aren't supported.
- **Windows USB sticks (FAT32/exFAT) and network folders are untested**. If something goes wrong there, every image may fail with a permissions or replace error, so try a few copies first.
- **macOS** hasn't been tried.
- **Ctrl+C** doesn't stop a run cleanly; use `Q`.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m pytest            # offline: generated images, fake model servers
python -m pytest --cov      # with coverage, like CI
ruff check . && ruff format --check .
```

- [AGENTS.md](AGENTS.md): architecture, design rules, CI and maintenance notes (also imported by [CLAUDE.md](CLAUDE.md))
- [TESTING.md](TESTING.md): manual test checklist, including tagging-quality runs against real models
- [SECURITY.md](SECURITY.md): how to report vulnerabilities, and the threat model

## License

[MIT](LICENSE)
