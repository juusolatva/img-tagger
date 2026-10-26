"""End-to-end CLI tests that run the scripts as subprocesses (no model server needed)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import SAMPLE_TAGS, make_gif, make_image

import img_tagger

REPO = Path(__file__).resolve().parent.parent


def run(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / script), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=60,
        env={**os.environ, **env} if env else None,
    )


class TestImgTaggerCli:
    def test_help(self):
        result = run("img_tagger.py", "--help")
        assert result.returncode == 0
        for flag in [
            "--recursive",
            "--backend",
            "--host",
            "--model",
            "--workers",
            "--timeout",
            "--log",
            "--clear",
        ]:
            assert flag in result.stdout

    def test_missing_directory(self, tmp_path):
        result = run("img_tagger.py", str(tmp_path / "nope"))
        assert result.returncode == 1
        assert "could not be located" in result.stdout

    @pytest.mark.parametrize("workers", ["0", "5", "-1"])
    def test_rejects_out_of_range_workers(self, tmp_path, workers):
        result = run("img_tagger.py", str(tmp_path), "--workers", workers)
        assert result.returncode == 1
        assert "Workers must be between 1 and 4" in result.stdout

    @pytest.mark.parametrize("timeout", ["0", "-5", "nan"])
    def test_rejects_non_positive_timeout(self, tmp_path, timeout):
        result = run("img_tagger.py", str(tmp_path), "--timeout", timeout)
        assert result.returncode == 1
        assert "Timeout must be a positive number" in result.stdout

    def test_rejects_unknown_backend(self, tmp_path):
        result = run("img_tagger.py", str(tmp_path), "--backend", "bogus")
        assert result.returncode == 2
        assert "invalid choice" in result.stderr

    def test_empty_directory_exits_cleanly(self, tmp_path):
        result = run("img_tagger.py", str(tmp_path))
        assert result.returncode == 0
        assert "No valid images found" in result.stdout

    def test_log_file_created(self, tmp_path):
        log = tmp_path / "logs" / "run.log"
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 0
        assert log.parent.is_dir()

    @pytest.mark.parametrize("name", ["notes.txt", ".bashrc", "authorized_keys", "run.log.py"])
    def test_rejects_log_without_log_suffix(self, tmp_path, name):
        log = tmp_path / "logs" / name
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 1
        assert "must end in .log" in result.stdout
        assert not log.parent.exists()

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
    def test_rejects_symlinked_log(self, tmp_path):
        target = tmp_path / "profile"
        target.write_text("original\n", encoding="utf-8")
        log = tmp_path / "run.log"
        log.symlink_to(target)
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 1
        assert "must not be a symlink" in result.stdout
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_rejects_non_regular_log(self, tmp_path):
        log = tmp_path / "dir.log"
        log.mkdir()
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 1
        assert "must be a regular file" in result.stdout

    def test_appends_to_existing_uppercase_log(self, tmp_path):
        log = tmp_path / "RUN.LOG"
        log.write_text("earlier run\n", encoding="utf-8")
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 0
        assert log.read_text(encoding="utf-8").startswith("earlier run\n")

    # Port 9 (discard) refuses connections, so tagging fails fast without a model server.
    DEAD_HOST = "http://127.0.0.1:9"

    def test_failed_image_prints_no_traceback(self, tmp_path):
        make_image(tmp_path / "a.png")
        result = run("img_tagger.py", str(tmp_path), "--host", self.DEAD_HOST)
        assert result.returncode == 0
        assert "Failed images: 1" in result.stdout
        assert "Traceback" not in result.stdout + result.stderr

    def test_log_file_records_run(self, tmp_path):
        images = tmp_path / "images"
        images.mkdir()
        make_image(images / "a.png")
        log = tmp_path / "run.log"
        result = run("img_tagger.py", str(images), "--host", self.DEAD_HOST, "--timeout", "30", "--log", str(log))

        assert result.returncode == 0
        assert "Traceback" not in result.stderr
        text = log.read_text(encoding="utf-8")
        assert "Tagging 1 images" in text
        assert "workers=1, timeout=30s" in text
        assert "[DEBUG]" in text
        assert "Prompt: " in text
        assert "[ERROR]" in text
        assert "Error processing a.png after" in text
        assert "Traceback" in text
        assert "Finished in" in text
        assert "0 tagged, 0 skipped, 1 failed" in text
        assert "STREAM" not in text, "Pillow's DEBUG chatter should stay out of the log"

    @pytest.mark.parametrize("recursive", [False, True])
    def test_clears_directory(self, tmp_path, recursive):
        top_jpg = make_image(tmp_path / "a.jpg")
        top_gif = make_gif(tmp_path / "b.gif")
        sub = tmp_path / "sub"
        sub.mkdir()
        nested = make_image(sub / "c.png")
        for path in (top_jpg, top_gif, nested):
            img_tagger.tag_image(str(path), SAMPLE_TAGS)

        args = [str(tmp_path), "--clear"] + (["-r"] if recursive else [])
        result = run("img_tagger.py", *args)

        assert result.returncode == 0
        assert f"Resetting tags for {3 if recursive else 2} images" in result.stdout
        assert not img_tagger.is_already_processed(top_jpg)
        assert not img_tagger.is_already_processed(top_gif)
        assert img_tagger.is_already_processed(nested) is not recursive

    def test_output_encoding_without_the_characters_does_not_crash(self, tmp_path):
        # Like Windows output redirected to a file (cp1252), only stricter
        path = make_image(tmp_path / "日本.jpg")
        img_tagger.tag_image(str(path), SAMPLE_TAGS)

        result = run("img_tagger.py", str(tmp_path), "--clear", env={"PYTHONIOENCODING": "ascii"})

        assert result.returncode == 0
        assert "Cleared metadata (pyexiv2) for: ??.jpg" in result.stdout
        assert not img_tagger.is_already_processed(path)

    def test_clears_with_multiple_workers(self, tmp_path):
        paths = [make_image(tmp_path / f"img_{i}.jpg") for i in range(4)]
        for p in paths:
            img_tagger.tag_image(str(p), SAMPLE_TAGS)

        result = run("img_tagger.py", str(tmp_path), "--clear", "--workers", "2")
        assert result.returncode == 0
        assert "Resetting tags for 4 images" in result.stdout
        for p in paths:
            assert not img_tagger.is_already_processed(p)
