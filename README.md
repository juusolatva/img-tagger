# img tagger

[![CI](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/juusolatva/img_tagger/actions/workflows/ci.yml)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=juusolatva_img_tagger&metric=coverage)](https://sonarcloud.io/summary/new_code?id=juusolatva_img_tagger)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Python](https://img.shields.io/badge/python-3.13%20%7C%203.14-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/github/license/juusolatva/img_tagger)](LICENSE)

A Python script that tags all the **JPEG**, **WebP**, **PNG** and **GIF** files in a folder (and optionally its subfolders). It sends each image to a vision-language model running in **Ollama** or **LM Studio**, either on your own computer or on another machine in your local network, and writes the tags the model sends back into the image's own metadata.

img tagger itself uses no cloud service: the images only go to the model server you point it at. (Ollama's cloud models, the ones whose names end in `-cloud`, run on ollama.com, so use a local model if your images must stay on your own network.)

The tags are standard EXIF and XMP fields (a comment for GIFs), so they stay with the file when you copy or move it. The accuracy of the tags depends on the model.

**Contents:** [Features](#features) · [Requirements](#requirements) · [Installation](#installation) · [Setting up a model backend](#setting-up-a-model-backend) · [Usage](#usage) · [What gets written to your images](#what-gets-written-to-your-images) · [Customising the prompt](#customising-the-prompt) · [Output](#output) · [Stopping early](#stopping-early) · [Clearing tags](#clearing-tags) · [Choosing a model and performance](#choosing-a-model-and-performance) · [Troubleshooting](#troubleshooting) · [Known issues and limitations](#known-issues-and-limitations) · [Running tests](#running-tests) · [Continuous integration](#continuous-integration) · [License](#license)

## Features

- Tags **JPEGs**, **WebPs**, **PNGs** and **GIFs**, including animated GIFs and WebPs (the animation is kept)
- Works with **Ollama** (default) or **LM Studio**, locally or on another machine with `--host`
- Writes 6 to 12 lowercase tags per image into standard metadata fields
- Skips files it has already tagged (they carry the marker ***[PROCESSED BY AI]***), so you can safely run it again on the same folder
- Processes **1 to 4** images at the same time
- Understands chatty model replies: plain comma-separated lists, JSON lists, bullet and numbered lists, "Here are the tags:" intros, and the reasoning of "thinking" models
- Writes through a temporary file in the same folder, so an interrupted write doesn't leave a half-written image behind
- Repairs images with corrupted metadata by re-saving them with Pillow (this re-encodes JPEGs and WebPs, see [Repairing corrupted metadata](#repairing-corrupted-metadata))
- Handles file and folder names with any characters, also on Windows
- Press `Q` to stop early and still get a report
- Progress bar, a result line for each image and a final report with timings
- Optional detailed log file for troubleshooting
- `--clear` strips the metadata back out
- The prompt lives in an editable [`prompt.txt`](prompt.txt)


---


## Requirements

- [Python](https://www.python.org/downloads/) **3.13 or newer** (tested on 3.13 and 3.14). Check with `python --version` (or `python3 --version`). On macOS, the `python3` that comes with Apple's command line tools may be too old; install a newer one from python.org or Homebrew. `pyexiv2` is built separately for each Python version, so a Python newer than 3.14 works only once `pyexiv2` has a release for it.
- [Ollama](https://ollama.com/download) or [LM Studio](https://lmstudio.ai/download) with a vision-capable model. A GPU makes a big difference to speed, see [Choosing a model and performance](#choosing-a-model-and-performance).
- The Python packages in [`requirements.txt`](requirements.txt):

| Package | Used for |
|---|---|
| `ollama` | Talking to Ollama |
| `openai` | Talking to LM Studio through its OpenAI-compatible API |
| `pillow` | Checking image formats, reading and writing GIFs, repairing broken metadata |
| `pyexiv2` | Reading and writing EXIF and XMP metadata, and clearing EXIF, XMP and IPTC with `--clear` |
| `tqdm` | The progress bar |

`pyexiv2` ships with the exiv2 library built in, so you **don't need exiftool or a separate exiv2 install**. Both backend libraries are installed, but only the one for the backend you use is needed at run time.

It has been run on Windows 11 and is tested on Linux and Windows in CI. It has not been tried on macOS.


---


## Installation

Clone the repository:

```bash
git clone https://github.com/juusolatva/img_tagger.git
cd img_tagger
```

Create a virtual environment so the packages don't mix with your system Python. On many Linux distributions, and with Homebrew's Python on macOS, it's needed anyway: there `pip` refuses to install into the system Python with `error: externally-managed-environment`.

Linux / macOS (on Debian and Ubuntu, install the `python3-venv` package first if this fails):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\activate
```

If PowerShell says that running scripts is disabled on this system, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` once, or use Command Prompt and `.venv\Scripts\activate.bat`.

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

`python -m pip` installs into the same Python you run img tagger with. There's nothing else to install: you run `img_tagger.py` directly from the folder. Activate the virtual environment again in every new terminal before you run it.

> The examples below use `python`. On Linux and macOS, use `python3` if `python` isn't available (inside an activated virtual environment both work).


---


## Setting up a model backend

img tagger doesn't run the model itself. It needs a running Ollama or LM Studio server with a vision-capable model.

### Ollama

1. Install [Ollama](https://ollama.com/download) and make sure it's running.
2. Download the default model:

   ```bash
   ollama pull qwen3-vl:8b
   ```

3. Run img tagger. The defaults (`--backend ollama`, `--host http://localhost:11434`, `--model qwen3-vl:8b`) already match:

   ```bash
   python img_tagger.py path/to/images
   ```

To use another vision model, pull it and pass its Ollama name with `--model`, e.g. `--model qwen3-vl:4b-instruct` for GPUs with little memory (see [Choosing a model and performance](#choosing-a-model-and-performance)).

### LM Studio

1. Install [LM Studio](https://lmstudio.ai/download).
2. Download a vision-capable model, for example Qwen3 VL 8B. For a GGUF model, make sure its **vision projector** (the `mmproj-*.gguf` file) is downloaded too. Without it LM Studio doesn't treat the model as vision-capable and rejects every image with `does not support image inputs`.
3. Start LM Studio's local server. img tagger expects it at `http://localhost:1234`.
4. Run img tagger with `--backend lm-studio` and **LM Studio's model id**. `--model` defaults to `qwen3-vl:8b` for both backends, but that's Ollama's name for the model, so with LM Studio you always have to set it:

   ```bash
   python img_tagger.py path/to/images --backend lm-studio --model qwen/qwen3-vl-8b
   ```

You can see the model ids LM Studio knows at <http://localhost:1234/v1/models>. LM Studio loads the model when the first request arrives, so the first image takes noticeably longer than the rest.

### Using a server on another machine

Point `--host` at the other machine. It has to be reachable from the computer running img tagger, and the server has to accept connections from the network:

- **Ollama** listens only on its own computer by default. On the server, set the environment variable `OLLAMA_HOST=0.0.0.0` before starting Ollama.
- **LM Studio** needs its **Serve on Local Network** server setting turned on.
- A firewall on the server may also have to allow the port (11434 for Ollama, 1234 for LM Studio).

img tagger itself doesn't read the `OLLAMA_HOST` variable on the computer it runs on; always pass `--host`. Ollama is fairly forgiving about the address:

| `--host` value | Connects to |
|---|---|
| `http://192.168.1.50:11434` | `http://192.168.1.50:11434` |
| `192.168.1.50:11434` | `http://192.168.1.50:11434` |
| `192.168.1.50` | `http://192.168.1.50:11434` |
| `http://192.168.1.50` | `http://192.168.1.50:80`: **add `:11434`** |

LM Studio needs the full address with `http://` and the port, and **without** `/v1` (img tagger adds it) or a trailing slash:

```bash
python img_tagger.py path/to/images --backend lm-studio --host http://192.168.1.50:1234 --model qwen/qwen3-vl-8b
```

Without `http://`, every image fails with just `Connection error.`


---


## Usage

Give it the folder with your images:

```bash
python img_tagger.py path/to/images
```

> [!IMPORTANT]
> img tagger changes your images in place. It overwrites any existing XMP keywords and description (caption) and the EXIF user comment, replaces the comment of every GIF and re-encodes it, and re-encodes images with corrupted metadata. See [What gets written to your images](#what-gets-written-to-your-images). Try it on a copy of a few images first, and back up anything you can't replace.

On Windows, quote paths that contain spaces:

```powershell
python img_tagger.py "C:\Users\you\Pictures\My memes"
```

### Options

| Option | Default | Description |
|---|---|---|
| `directory` | (required) | The folder with your images. |
| `-r`, `--recursive` | off | Go through all subfolders too. Without it only the top folder is processed. |
| `--backend` | `ollama` | `ollama` or `lm-studio`. |
| `--host` | `http://localhost:11434` for Ollama, `http://localhost:1234` for LM Studio | Address of the model server. See [Using a server on another machine](#using-a-server-on-another-machine). |
| `--model` | `qwen3-vl:8b` | The model to use. The default is Ollama's name for it, so with LM Studio pass LM Studio's id (e.g. `qwen/qwen3-vl-8b`). |
| `--workers` | `1` | How many images to process at the same time, from 1 to 4. |
| `--timeout` | `600` | Seconds to wait for the model's answer to one image, including loading the model, before that image is marked failed. Must be a positive number. Raise it for slow hardware. |
| `--log` | off | Append a detailed log to this file, e.g. `--log logs/run.log`. Missing folders are created; a relative path is relative to the current directory. The name must end in `.log` (any letter case), and an existing path must be a regular file of yours, not a symlink, folder or someone else's file. The file is opened once and kept open, so it can't be swapped for a link during the run. |
| `--clear` | off | Remove metadata from the images instead of tagging them. See [Clearing tags](#clearing-tags). |
| `-h`, `--help` | | Show the options and exit. |

### Which files are processed

- Files ending in `.jpg`, `.jpeg`, `.png`, `.webp` or `.gif`, in any letter case (`photo.JPG` counts). Hidden files such as `.hidden.jpg` are included.
- Everything else (`.jfif`, `.tif`, `.heic`, `.avif`, `.bmp`, ...) is silently ignored and not counted.
- Image symlinks and symlinked parent directories are refused; choose the real image directory. POSIX also refuses image directories writable by another user/group or owned by someone other than the current user or root. Shared ancestors such as `/tmp` are allowed because directory handles stay pinned. Paths containing `..` are refused.
- Each file is opened with Pillow first, and img tagger goes by the image's real format, not its extension (a PNG named `.gif` is tagged like a PNG).
  - A file with an image extension that isn't a valid image fails with `Skipping unsupported or corrupted file`.
  - A valid image in a format img tagger can't tag (e.g. a BMP named `.jpg`, or an MPO, see [Known issues](#known-issues-and-limitations)) fails with `Unsupported file format: <format>`.
  - Neither is sent to the model.
- If the folder has no matching files, it prints `No valid images found in '<folder>'.` If your images are in subfolders, add `-r`.

### Exit codes

| Code | When |
|---|---|
| `0` | The run finished, even if some images failed. Also after pressing `Q`, when no images were found, and when the backend's Python library is missing (an error is printed). |
| `1` | The folder doesn't exist, `--workers` is outside 1 to 4, `--timeout` is zero, negative or `nan`, `--log` doesn't name a regular `.log` file, or `prompt.txt` exists but can't be read. Also when the script stops with a Python traceback, e.g. a required package such as `pyexiv2` is missing or the `--log` file can't be created. |
| `2` | An invalid option, e.g. an unknown `--backend` or a non-number for `--workers` or `--timeout`. |

### Examples

The examples use Linux/macOS paths. On Windows, write the full path instead, e.g. `"C:\Users\you\Pictures\memes"`: Command Prompt and Windows PowerShell 5.1 don't expand `~`, so img tagger would report that the folder could not be located.

Tag a folder and all of its subfolders with Ollama:

```bash
python img_tagger.py ~/Pictures/memes -r
```

Use LM Studio with 4 workers and save a log:

```bash
python img_tagger.py ~/Pictures/memes --backend lm-studio --model qwen/qwen3-vl-8b --workers 4 --log run.log
```

Use Ollama on another machine with a smaller model, and give slow hardware more time per image:

```bash
python img_tagger.py ~/Pictures/memes --host http://192.168.1.50:11434 --model qwen3-vl:4b-instruct --timeout 1200
```

Clear all metadata from a folder and its subfolders (read [Clearing tags](#clearing-tags) first):

```bash
python img_tagger.py ~/Pictures/memes -r --clear
```


---


## What gets written to your images

### Where the tags go

**JPEG, WebP and PNG** get the tags in three places:

| Field | Content |
|---|---|
| EXIF `Exif.Photo.UserComment` | `meme, cat, funny, reaction, text, digital_art [PROCESSED BY AI]` |
| XMP `Xmp.dc.subject` | The tags as a list: `meme`, `cat`, `funny`, ... |
| XMP `Xmp.dc.description` | `Tags: meme, cat, funny, reaction, text, digital_art \| [PROCESSED BY AI]` |

**GIF** has no EXIF or XMP support, so the tags go into the GIF comment, **replacing any comment the GIF already had**: `meme, cat, funny, reaction, text, digital_art [PROCESSED BY AI]`.

Which apps display which of these fields hasn't been checked. The tags are also shown on screen while the script runs and written to the log file. To read them back from a file, use a metadata tool such as [ExifTool](https://exiftool.org/) (`exiftool -XMP:Subject -UserComment photo.jpg`, or `exiftool -Comment party.gif`).

### How the tags are cleaned up

- Each tag is trimmed and lowercased, and duplicates are removed. The model's order is kept.
- At most **12** tags are kept (the first 12).
- If fewer than **6** usable tags are left, the image fails with `Invalid or insufficient tags returned from model` and nothing is written.
- Underscores and spaces inside a tag are kept as they are (`digital_art`, `pixel art`). Some models use underscores, so `digital_art` and `digital art` can both appear across a folder.
- Tags aren't checked for language, so you can [change the prompt](#customising-the-prompt) to get tags in another language. The flip side: Qwen models occasionally reply with a Chinese tag even though the default prompt asks for English only, and such a tag is written as it is.
- With the default prompt the first tag is usually the type of image, such as `meme`, `screenshot`, `artwork` or `photo`.

### Already tagged images are skipped

The `[PROCESSED BY AI]` marker tells img tagger that an image is done. For JPEG, WebP and PNG it looks for the marker in every EXIF and XMP value and in any text metadata Pillow can read (such as PNG text chunks); for GIFs, in the comment. Images that have it are skipped without contacting the model.

Images that fail get no marker, so running the same command again retries only the failed ones and quickly skips the rest.

There is no option to force re-tagging. To tag images again, either move them into a folder of their own and run [`--clear`](#clearing-tags) on that folder (it works on whole folders only and removes **all** metadata, not just the tags), or use a metadata editor to remove the marker from both `Exif.Photo.UserComment` and `Xmp.dc.description` (for a GIF, from its comment).

### What happens to existing metadata

Tagging a JPEG, WebP or PNG replaces only the three fields above and leaves everything else alone, unless the image first has to be [repaired](#repairing-corrupted-metadata):

| Kept | Replaced |
|---|---|
| All other EXIF, e.g. orientation, camera settings, author | `Exif.Photo.UserComment` |
| All other XMP, e.g. the creator | `Xmp.dc.subject`: **existing XMP keywords are lost** and replaced by the new tags |
| All IPTC, including IPTC keywords | `Xmp.dc.description` |
| The JPEG comment | |
| PNG text chunks (e.g. Stable Diffusion's `parameters`) and DPI | |

IPTC keywords are not updated, so apps that read IPTC keywords may still show the old ones.

### How the files are changed

- **JPEG, WebP and PNG**: only the metadata is edited; the image data is not re-encoded. Animated WebPs keep their frames, frame durations and loop count.
- **GIF**: the whole file is re-encoded through Pillow. Each frame keeps its duration (100 ms if it had none) and the loop setting is kept (a GIF that plays once still plays once). Consecutive identical frames are merged into one frame with their combined duration, so playback looks the same. Pillow keeps all of a GIF's frames in memory while writing it, so a very large animated GIF can need a lot of RAM. See [Known issues](#known-issues-and-limitations) for the side effects.
- Each image is read through guarded file access. Output is written to an open temporary `tmpXXXX.tmp` file **in the same folder**, edited through that file handle and then moved over the original. If the original is locked (e.g. open in another program), the move is retried up to 10 times, half a second apart. The temporary file is removed afterwards.
- File mode permissions and, on Linux and macOS, the file's group are kept (if you aren't a member of that group, its group permissions are removed instead, with a warning). Linux extended attributes and POSIX ACLs are preserved through the opened file handles; inherited temporary-file ACL grants are removed. On Windows the image's NTFS permissions (its DACL, including whether it inherits from the folder) are given to the temporary file when it is created, before anything is written to it, and the read-only attribute is kept. Timestamps are not copied, and on Windows the file's owner becomes your account.
- On POSIX, parent directories are opened without following symlinks, and replacement uses pinned directory descriptors. This protects against other-user directory substitution subject to the directory ownership/write restrictions above; it does not isolate another process running as your own account or root.
- On Windows, every folder above an image is held open while the image is read or written, so it can't be renamed or swapped for a junction meanwhile (while that happens, renaming those folders fails with "in use"). Symlinks, junctions and other reparse points are refused. Nobody else can open the temporary file, and it replaces the original through its open handle. Tested on local NTFS drives only; see [Known issues](#known-issues-and-limitations) for USB sticks and network folders.

### Repairing corrupted metadata

If pyexiv2 reports broken metadata (an error mentioning "IFD" or "corrupt"), img tagger shows a warning like:

```
  Warning: Corrupted metadata in photo.jpg (<error>); re-saving it with Pillow before tagging (JPEG/WebP are re-encoded)
```

It then re-saves the image with Pillow (quality 95 for JPEG and WebP) and tags the repaired copy. This rescues the image, but the re-save has side effects:

| Format | Effect of the repair |
|---|---|
| JPEG | Re-encoded. EXIF (including orientation, camera and GPS data), ICC colour profile, XMP and DPI are dropped, so a photo that relied on its orientation may show up rotated. |
| WebP | Re-encoded as **lossy**, even if the original was lossless. ICC profile, EXIF and XMP are dropped. |
| PNG | Stays lossless and keeps its ICC profile, but other text chunks, DPI and EXIF are lost. |
| Animated WebP / PNG (APNG) | Keep their frames, frame durations and loop count. |


---


## Customising the prompt

The instructions sent to the model are in [`prompt.txt`](prompt.txt). Edit it to change what kind of tags you get.

- img tagger reads `prompt.txt` from the **same folder as `img_tagger.py`**, not from the folder you run it in. It's read as UTF-8.
- If the file is missing, it prints `Warning: Could not read prompt.txt from <path>. Falling back to default.` and uses a built-in copy of the same prompt.
- If the file exists but can't be read (no permission, invalid UTF-8), it prints an error and exits with code 1.
- Whatever you change, the model still has to reply with **at least 6** tags, or the image fails; only the first 12 are kept. A comma-separated list is the simplest. The reply can also be a JSON list (`["a", "b", ...]`), a bullet or numbered list with at least 6 items, or a list after an intro like `Here are the tags:`. Anything a thinking model writes before its last `</think>` is ignored.

The default prompt asks for 6 to 12 English tags with the image type first, and has extra instructions for memes (the template, subjects, mood and a few words from the text) and screenshots (the main topic or software shown).


---


## Output

### While it runs

```
Initialized backend: ollama | Target: http://localhost:11434
Found 5 images to process. Starting...

Starting concurrent processing (max_workers=1).
Press 'q' at any time to stop and see the current report.
```

The "Found" count includes images that are already tagged. A progress bar labelled `Processing images` follows, and a line is printed for each image as it finishes:

```
  [✓] cat.jpg -> Generated Tags: ['meme', 'cat', 'funny', 'digital_art', 'reaction', 'text']
  [-] dog.png -> Skipped: Already Tagged
  [!] notimage.jpg -> Skipping unsupported or corrupted file
  [!] blurry.webp -> Invalid or insufficient tags returned from model
  [!] party.gif -> <error message>
```

- `[✓]` tagged, `[-]` skipped, `[!]` failed.
- The result lines start with just the file name (an error from writing the file may include its path). With `-r`, files with the same name in different folders look alike.
- Lines appear in the order the images finish, which with several workers isn't the order they were found.
- When the output goes to a file or another program and can't show a character (e.g. on Windows, `✓` or a name like `日本.jpg`), a `?` is printed instead.

Some problems are always shown on screen as `  Warning: ...` lines, with or without `--log`:

- `Could not read the EXIF metadata of <name> (...)` (or `XMP`)
- `pyexiv2 could not read the metadata of <name> (...); checking it with Pillow instead`
- `Could not read the metadata of <name> (...); treating it as not yet tagged`
- `Could not read the GIF comment of <name> (...); treating it as not yet tagged`
- the [corrupted metadata](#repairing-corrupted-metadata) warning

### The final report

```
==================================================
                PROCESSING REPORT
==================================================
 Processed images: 4
 Skipped images: 0
 Failed images: 1
 Total time elapsed: <h>h <m>m <s>s
 Average processing time: <seconds> seconds

--- Failed files details ---
 * notimage.jpg -> Skipping unsupported or corrupted file
==================================================
```

- **Processed** means successfully tagged.
- **Average processing time** is shown only when at least one image was tagged. It covers the successful images only, from sending the request to the model until the tags are written.
- **Total time elapsed** starts once the prompt and the backend client are set up.
- **Failed files details** lists each failed image with the reason.

### Log file

`--log FILE` appends a detailed UTF-8 log, which is the first place to look when something goes wrong. Each line has a timestamp, level and thread name. It contains:

- the Python version and operating system
- the run settings: folder, recursion, backend, host, model, workers and timeout
- which prompt file was used, and the full prompt
- for each image: when it started, the request to the model, **the model's raw reply**, and the tags and time taken, or the error with a full traceback
- the HTTP requests made to the backend
- a summary at the end: how many were tagged, skipped and failed, and the total time

The log contains file paths (as you typed the folder, plus the full path of `prompt.txt`) and the model's replies, so check it before sharing it. When the screen shows only a short message such as `Connection error.`, the log usually has the real cause, e.g. `Request URL is missing an 'http://' or 'https://' protocol.`


---


## Stopping early

Press `Q` (or `q`, no Enter needed) while images are being tagged:

- Images that are already being processed finish normally (or fail once `--timeout` runs out).
- The images still in the queue are not sent to the model, and they are not shown in the output or counted in the report. Queued images are still checked quickly, though, so ones that are already tagged or aren't valid images may still show up as skipped or failed.
- The report is printed and the script exits normally.

The message `[!] Stop signal received (Q pressed). Finishing currently running tasks...` appears when the next image finishes, which on slow hardware can take a while.

Good to know:

- Keys you type during a run are used by the quit listener: on Windows they're consumed, and on Linux and macOS they're not echoed until the run ends.
- `Q` is not available with `--clear`.
- On Linux and macOS, when input isn't a terminal (e.g. it's piped in), a `q` in the input stops the run. If the input is empty (`</dev/null`), `Q` isn't available.
- On Windows, `Q` is only tested against a simulated console. If it doesn't react, closing the terminal window stops the run; an image being written at that moment may leave a `tmpXXXX.tmp` file in its folder, which you can delete.
- **Ctrl+C does not stop a run cleanly.** The images already queued keep being tagged, and you end up with a traceback and no report. Use `Q` instead.


---


## Clearing tags

```bash
python img_tagger.py path/to/images --clear
```

> [!WARNING]
> `--clear` removes **all** EXIF, XMP and IPTC metadata from every JPEG, WebP and PNG in the folder (and, with `-r`, in all subfolders), not just the tags img tagger wrote. That includes camera settings, dates, GPS location, author and copyright fields, orientation and keywords from other apps. It starts right away without asking for confirmation, it works only on whole folders (not single files), and there is no undo, so make a backup first if you care about that metadata. Photos that rely on the EXIF orientation may show up rotated afterwards.

- It was made for resetting images so they can be tagged again, e.g. when testing models or prompts.
- **Kept**: the JPEG comment, and PNG text chunks and DPI.
- **GIFs**: the comment is emptied, and every GIF is re-encoded the same way as when tagging, tagged or not (see [How the files are changed](#how-the-files-are-changed)).
- Like tagging, it goes by the image's real format, so a mislabeled file is cleared the way it was tagged.
- Files with corrupted metadata are re-saved with Pillow instead, with the same side effects as [when tagging](#repairing-corrupted-metadata).
- No model server is needed. `--backend`, `--host`, `--model` and `--timeout` are ignored (`--timeout` must still be valid), and `prompt.txt` isn't read.
- `-r`, `--workers` and `--log` work as usual.
- There's no progress bar, no report and no `Q` to stop.

The output looks like this:

```
Resetting tags for 3 images...
  Cleared metadata (pyexiv2) for: cat.jpg
  Cleared GIF comment: party.gif
  Failed to clear broken.png: <error message>
Done.
```

A file whose metadata had to be repaired shows `Sanitized and cleared (Pillow) for: <name>`. The exit code is 0 even if some files failed.


---


## Choosing a model and performance

- The default model is **Qwen3 VL 8B**. The default `--model qwen3-vl:8b` is Ollama's name for it; with LM Studio pass its id, e.g. `--model qwen/qwen3-vl-8b`. Any model that accepts image inputs should work, and tag quality depends on the model.
- "Thinking" models work too; their reasoning is dropped before the tags are read. Thinking and CPU-only generation can be slow, so you may need a longer `--timeout`.
- **Speed depends mostly on your GPU and the model.** A modern GPU with 16 GB of memory is far faster than older 6 GB cards, and on the same GPU one model can be many times faster than another. If tagging is very slow, try another model.
- **The model should fit in GPU memory.** A vision model's image part takes memory on top of the language model, and anything that doesn't fit runs on the CPU, which is much slower. With Ollama, `ollama ps` shows the split (e.g. `4%/96% CPU/GPU`). If part of the model runs on the CPU, use a smaller model (e.g. `qwen3-vl:4b-instruct` instead of `qwen3-vl:8b` on 6 GB cards) or a shorter context length (Ollama's `OLLAMA_CONTEXT_LENGTH` setting on the server): tagging one image needs far less context than chat.
- The **first image** is slower because the server loads the model then.
- `--timeout` (600 seconds by default) is how long to wait for **one** image's complete answer, including loading the model. An image that runs out of time is marked failed and retried on the next run. With LM Studio, a request that timed out is not resent.
- `--workers` sends up to 4 images at once, which matches the default number of parallel requests in both Ollama and LM Studio. If the server handles fewer requests at a time, the extra ones wait their turn on the server, and that wait may count towards `--timeout`.
- Each image is sent **whole and unchanged**: it isn't resized or converted. Very large files make large requests (about a third larger than the file, because of base64 encoding).


---


## Troubleshooting

**`ModuleNotFoundError: No module named 'pyexiv2'`** (or `'PIL'`, `'tqdm'`, `'ollama'` or `'openai'`)
- The dependencies aren't installed in the Python you ran. Activate your virtual environment if you made one, and run `python -m pip install -r requirements.txt`.

**`Failed to connect to Ollama. Please check that Ollama is downloaded, running and accessible.`** for every image
- Start Ollama, or check the address you passed with `--host` (and remember that `http://<ip>` without a port means port 80). For a server on another machine, see [Using a server on another machine](#using-a-server-on-another-machine).
- img tagger doesn't check the server before starting, so each image fails on its own. Press `Q` to stop.

**`Connection error.`** for every image (LM Studio)
- Make sure LM Studio's server is running and the port is right.
- `--host` must start with `http://`, e.g. `http://localhost:1234`, and must not end in `/v1`.
- Run with `--log` to see the real cause.

**Every image fails with an error about the model**
- Check `--model`. With Ollama the model must be pulled (`ollama pull <name>`). With LM Studio use LM Studio's model id from <http://localhost:1234/v1/models>, not the Ollama name.

**`... does not support image inputs`** (LM Studio)
- The model's vision projector (`mmproj-*.gguf`) isn't downloaded. Download it in LM Studio, or use another vision model.

**The first images fail with an HTML `Internal Server Error` page** (LM Studio)
- This can happen when several requests arrive while LM Studio is still loading the model (with `--workers` above 1). Run the same command again: the images that were tagged are skipped and the failed ones are retried. Loading the model in LM Studio before you start avoids it.

**`timed out`** (Ollama) or **`Request timed out.`** (LM Studio) after a long wait
- The image ran out of `--timeout`. Raise it (e.g. `--timeout 1200`), use fewer `--workers`, or try a faster model (see [Choosing a model and performance](#choosing-a-model-and-performance)).

**`Invalid or insufficient tags returned from model`**
- The reply didn't contain at least 6 usable tags. Run with `--log` to see the raw reply. Try another model, or check your changes to `prompt.txt`.

**`Skipping unsupported or corrupted file`**
- The file has an image extension but Pillow can't open it as an image.

**`Unsupported file format: MPO`** (or another format, e.g. `BMP` or `TIFF`)
- The file has a `.jpg`, `.jpeg`, `.png`, `.webp` or `.gif` extension, but its real format is something else. For MPO see [Known issues](#known-issues-and-limitations); otherwise convert the file to a supported format.

**`[WinError 5] Access is denied: '...\tmpXXXX.tmp'`** or **`Failed to replace ... after retries.`** on Windows
- Another program kept the image locked for the 5 seconds img tagger waited. Close the other program and run again. Read-only images are replaced (and stay read-only) on NTFS; on other drives (FAT32/exFAT, some network shares) a read-only image can fail this way, so clear its read-only attribute first.

**`Error: The folder '<folder>' could not be located.`**
- Check the path. On Windows, quote paths that contain spaces and don't use `~` (see [Examples](#examples)).

**`No valid images found in '<folder>'.`**
- No `.jpg`, `.jpeg`, `.png`, `.webp` or `.gif` files in that folder. If they're in subfolders, add `-r`.

**`Warning: Could not read prompt.txt from <path>. Falling back to default.`**
- `prompt.txt` isn't next to `img_tagger.py`. The built-in default prompt is used instead, so tagging still works.


---


## Known issues and limitations

- **Animated images**: the whole file is sent to the model, and the servers only look at the first frame. With animated GIFs this has been seen on both Ollama and LM Studio (a white first frame gave `blank, white`); animated WebPs and PNGs most likely behave the same. The animation itself is kept in the file.
- **Image orientation**: images are sent as they are, without applying the EXIF orientation, so depending on the server, rotated photos may look sideways to the model.
- **GIF re-encoding**: tagging or clearing a GIF re-encodes the whole file with Pillow. Frames, frame durations and the loop setting are kept, but custom application extensions (other than looping) and GIF XMP data are dropped, and the pixels or file size may change slightly.
- **Repaired images**: images with corrupted metadata are re-saved with Pillow, which can re-encode them and drop other metadata. See [Repairing corrupted metadata](#repairing-corrupted-metadata).
- **IPTC keywords** are left as they are, and existing XMP keywords are replaced. See [What happens to existing metadata](#what-happens-to-existing-metadata).
- **No forced re-tagging**: tagged images are always skipped. See [Already tagged images are skipped](#already-tagged-images-are-skipped).
- **MPO JPEGs are not supported**: JPEGs that hold several embedded images (some cameras and phones save these) are reported by Pillow as `MPO` and fail with `Unsupported file format: MPO`, without contacting the model.
- **Windows USB sticks and network folders are untested**: the Windows file handling (copying the image's permissions, replacing it through the open file handle) has only been tried on local NTFS drives. FAT32/exFAT drives and network shares handle permissions and renames differently; if they behave unexpectedly, every image there may fail with a permissions or replace error, so try a few copies first.
- **No upfront server check**: if the server is down or the model is wrong, every image fails separately.
- **Ctrl+C** doesn't stop a run cleanly. Use `Q`.


---


## Running tests

Install the development dependencies (pytest, pytest-cov and the pinned Ruff version) and run the tests:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

The default tests run offline: they generate their own images and use fake model backends, so no model server is needed. For a coverage report like CI's, run `python -m pytest --cov`.

Lint and format checks (line length 120):

```bash
ruff check .
ruff format --check .
```

On Windows, the tests for the Linux/macOS quit listener and file permissions are skipped; the Windows file-safety tests (folder pins, junctions, NTFS permissions, read-only files) run instead, and the Windows quit listener is tested with a simulated console.

### Integration tests

To check tagging quality against real images, put them in a `test_images/` folder (git-ignored, subfolders included) and run with Ollama or LM Studio running:

```bash
python -m pytest -m integration --run-integration -s
```

| Option | Default | Description |
|---|---|---|
| `--tagger-backend` | `ollama` | `ollama` or `lm-studio` |
| `--tagger-host` | the backend's localhost address | Address of the model server |
| `--tagger-model` | `qwen3-vl:8b` | Model to use; for LM Studio pass e.g. `qwen/qwen3-vl-8b` |
| `--images-dir` | `test_images/` in the repository | Folder with the test images (`~` works) |

For example, against LM Studio:

```bash
python -m pytest -m integration --run-integration -s --tagger-backend lm-studio --tagger-model qwen/qwen3-vl-8b
```

Each image is its own test. It is copied to a temporary folder first, so the originals are not modified, and cleared there if it was already tagged. Each test prints a line like `[SUCCESS] cat.jpg (12.3s) -> Generated Tags: [...]` so you can review the tags by eye, and fails if the image wasn't tagged. The tests use the same client settings as a real run: the default 600-second timeout, and with LM Studio a timed-out request is not resent.

Notes for coding agents and contributors are in [AGENTS.md](AGENTS.md).


---


## Continuous integration

Every push to `main` and every pull request runs [GitHub Actions](.github/workflows/ci.yml), and you can also start it by hand:

- **Ruff** lint and format checks, using the Ruff version pinned in `requirements-dev.txt`
- the offline **tests** with coverage on Python 3.13 and 3.14 (on Linux)
- a **SonarQube Cloud** scan, which uses the coverage report from the Python 3.14 job (needs `SONAR_TOKEN` as a repository secret and as a Dependabot secret; pull requests from forks get no secrets, so there the scan is skipped with a warning)
- an [**OSV-Scanner**](.github/workflows/osv-scanner.yml) dependency vulnerability scan (`requirements-dev.lock` and `requirements*.txt`), which also runs on a weekly schedule; on pull requests it checks only for newly introduced vulnerabilities and skips the SARIF upload on fork PRs

To run the same checks locally, use `ruff check .`, `ruff format --check .` and `python -m pytest --cov`.

CI installs the exact package versions in `requirements-dev.lock` (with `--require-hashes --only-binary :all:`). If you change `requirements.txt` or `requirements-dev.txt`, regenerate the lock with [uv](https://docs.astral.sh/uv/):

```bash
uv pip compile requirements-dev.txt --universal --python-version 3.13 --generate-hashes --no-header -o requirements-dev.lock
```

This keeps the versions already in the lock where they still fit. To update the locked versions, add `--upgrade` (or `-P <package>` for a single package).

[Dependabot](.github/dependabot.yml) opens pull requests to update the GitHub Actions used in CI; the schedule, grouping and cooldown are set in that file. It is told to ignore the Python packages, security updates included, because it can't regenerate this lock.

The minimum versions in `requirements.txt` have not been tested as minimums; CI only tests the locked versions.


---


## License

[MIT](LICENSE)
