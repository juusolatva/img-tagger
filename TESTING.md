# Manual testing

The automated tests (`python3 -m pytest`, run in CI on Linux and Windows) cover the code with generated images and fake model servers. This list is what they **can't** check: tagging quality with real models, real hardware and drives, and platforms CI doesn't run on.

**How to use it:** tick an item when it's done and note the date and setup after it, e.g.

```markdown
- [x] FAT32 USB stick: tag and `--clear` — 2026-12-01, Windows 11, OK
```

Untick an item when the code it depends on changes (each section says when). If a test fails, open an issue or pin the bug as a strict `xfail` test (see [AGENTS.md](AGENTS.md)).

## 1. Tagging quality

Re-test when `prompt.txt`, `DEFAULT_PROMPT`, `parse_model_output()`/`normalize_tags()`, the default model or the `--max-pixels` default changes, or when trying a new model.

Put sample images in `test_images/` (git-ignored, subfolders included), start the server and run:

```bash
python3 -m pytest -m integration --run-integration -s
python3 -m pytest -m integration --run-integration -s --tagger-backend lm-studio --tagger-model qwen/qwen3-vl-8b
```

| Option | Default | Description |
|---|---|---|
| `--tagger-backend` | `ollama` | `ollama` or `lm-studio` |
| `--tagger-host` | the backend's localhost address | Address of the model server |
| `--tagger-model` | `qwen3-vl:8b` | Model; with LM Studio pass its id, e.g. `qwen/qwen3-vl-8b` |
| `--images-dir` | `test_images/` | Folder with the test images (`~` works) |

Each image is copied to a temporary folder (the originals are never changed) and its tags are printed as `[SUCCESS] cat.jpg (12.3s) -> Generated Tags: [...]`. A test fails only if the image wasn't tagged, so read the tags yourself.

- [ ] Ollama, `qwen3-vl:8b`: tags fit photos, memes, screenshots and diagrams; the first tag is the image type
- [ ] LM Studio, `qwen/qwen3-vl-8b`: same check
- [ ] A smaller model for low-memory GPUs (`qwen3-vl:4b-instruct`)
- [ ] A "thinking" model: reasoning is dropped and the tags are parsed
- [ ] Small text in screenshots and diagrams is still read at the default 1 megapixel
- [ ] Animated GIF and WebP: tags describe the first frame, and the file still animates afterwards (the integration tests tag copies in a pytest temp folder, so check this by running `img_tagger.py` on copies in a folder of your own and opening them in a viewer)

## 2. Model servers

Re-test when `_create_client()`, `_check_server()` or the backend calls change.

- [ ] Ollama on another LAN machine (`OLLAMA_HOST=0.0.0.0` on the server, `--host http://<ip>:11434`)
- [ ] LM Studio on another LAN machine (Serve on Local Network, `--host http://<ip>:1234`)
- [ ] LM Studio with a GGUF model whose `mmproj-*.gguf` is missing: every image fails with `does not support image inputs`
- [ ] LM Studio with `--workers 4` and the model not loaded yet: any failed images are tagged on a second run

## 3. Windows

Re-test when the Windows file-safety code changes (`_pin_windows_directory()`, `_create_windows_temp()`, `_rename_windows_handle()`, `_discard_windows_temp()`, DACL handling) or the `msvcrt` quit listener changes. The drive tests matter most: if the code misbehaves there, **every** image on such a drive fails.

- [ ] Local NTFS: tag and `--clear`, read-only images stay read-only, pinned folders can't be renamed during a run (last passed 2026-10 on Windows 11, before the 2026-11-21 changes to `_pin_windows_directory()` and the EFS check)
- [ ] FAT32 USB stick: tag and `--clear`
- [ ] exFAT USB stick: tag and `--clear`
- [ ] Read-only image on FAT32 or exFAT
- [ ] Network share (SMB, e.g. a NAS or Samba server): tag and `--clear`
- [ ] EFS: an encrypted image in an encrypted folder is tagged; an encrypted image in a plain folder fails with `Encrypted (EFS) image would be replaced by an unencrypted file` (tests only fake the encryption flag)
- [ ] OneDrive folder with Files On-Demand: note what happens to cloud-only and downloaded files
- [ ] Real console: `Q` stops the run and prints the report (tests use a simulated console)
- [ ] Real console: arrow keys, Page Up/Down and function keys don't stop the run

## 4. macOS

Never run on macOS. Re-test after changes to the quit listener, file safety or logging.

- [ ] Install in a virtual environment and run `python3 -m pytest`
- [ ] Tag a folder with Ollama, then `--clear` it
- [ ] `Q` stops the run in Terminal, and the terminal echoes typed keys again afterwards
- [ ] `--log /tmp/run.log` works (`/tmp` is a symlink on macOS)
- [ ] Folders under `~/Pictures` pass the folder permission check

## 5. Linux

Re-test when the extended-attribute or quit-listener code changes.

- [ ] SELinux (Fedora): an image moved in from `/tmp` is tagged, and `ls -Z` shows a sensible label afterwards (tests only fake the labels)
- [ ] Real terminal: `Q` stops the run, and the terminal echoes typed keys again afterwards

## 6. Where the tags show up

Which apps display the tags hasn't been checked. When you know, add the result to README's [Where the tags go](README.md#where-the-tags-go).

- [ ] Windows Explorer (Properties → Details: Tags, Comments)
- [ ] digiKam
- [ ] Adobe Lightroom or Bridge
- [ ] macOS Finder or Photos
- [ ] The photo manager you actually use: ______

## 7. Dependency minimums

CI tests only the versions in `requirements-dev.lock`; the `>=` bounds in `requirements.txt` were never tested as minimums. Re-test when a bound changes.

- [ ] Fresh virtual environment on Python 3.13 with the exact minimums, then `python3 -m pytest`:

  ```bash
  sed 's/>=/==/' requirements.txt > /tmp/minimums.txt
  python3 -m pip install -r /tmp/minimums.txt pytest
  ```
