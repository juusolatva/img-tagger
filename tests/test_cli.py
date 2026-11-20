"""CLI tests: main() in-process for argument handling, subprocesses for end-to-end runs (no model server needed)."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from conftest import SAMPLE_TAGS, FakeOllamaClient, FakeOpenAIClient, make_gif, make_image

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


class _FailingOllama(BaseHTTPRequestHandler):
    """Lists the default model (so the server check passes) and fails every chat request."""

    def _reply(self, status: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply(200, {"models": [{"name": img_tagger.DEFAULT_MODEL, "model": img_tagger.DEFAULT_MODEL}]})

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self._reply(500, {"error": "stub failure"})

    def log_message(self, *args):
        pass


@pytest.fixture
def failing_ollama():
    """URL of a local Ollama stand-in whose model replies all fail."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FailingOllama)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call_main(capsys, *args: str) -> tuple[int, str]:
    """Runs main() in-process; returns (exit code, stdout)."""
    code = img_tagger.main(list(args))
    return code, capsys.readouterr().out


class TestMain:
    """Argument handling through main(); none of these reach setup_logging()."""

    def test_missing_directory(self, capsys, tmp_path):
        code, out = call_main(capsys, str(tmp_path / "nope"))
        assert code == 1
        assert "could not be located" in out

    @pytest.mark.parametrize("workers", ["0", "5", "-1"])
    def test_rejects_out_of_range_workers(self, capsys, tmp_path, workers):
        code, out = call_main(capsys, str(tmp_path), "--workers", workers)
        assert code == 1
        assert "Workers must be between 1 and 4" in out

    @pytest.mark.parametrize("timeout", ["0", "-5", "nan", "inf"])
    def test_rejects_non_positive_timeout(self, capsys, tmp_path, timeout):
        code, out = call_main(capsys, str(tmp_path), "--timeout", timeout)
        assert code == 1
        assert "Timeout must be a positive number" in out

    @pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks and folder modes")
    @pytest.mark.parametrize("recursive", [False, True])
    def test_symlinked_folder_is_a_clean_error(self, capsys, tmp_path, recursive):
        real = tmp_path / "real"
        real.mkdir()
        make_image(real / "a.png")
        (tmp_path / "link").symlink_to(real)
        code, out = call_main(capsys, str(tmp_path / "link"), "--clear", *(["-r"] if recursive else []))
        assert code == 1
        assert f"Error: Image paths must not contain links: {tmp_path / 'link'} is a symlink" in out

    @pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="POSIX folder modes (root reads anyway)")
    @pytest.mark.parametrize("recursive", [False, True])
    def test_unlistable_folder_is_a_clean_error(self, capsys, tmp_path, recursive):
        folder = tmp_path / "locked"
        folder.mkdir()
        make_image(folder / "a.png")
        folder.chmod(0o311)  # can enter, can't list
        try:
            code, out = call_main(capsys, str(folder), "--clear", *(["-r"] if recursive else []))
        finally:
            folder.chmod(0o755)
        assert code == 1
        assert "Error: [Errno 13] Could not list the image folder: Permission denied" in out
        assert "No valid images found" not in out

    def test_rejects_unknown_backend(self, capsys, tmp_path):
        with pytest.raises(SystemExit) as exit_info:
            img_tagger.main([str(tmp_path), "--backend", "bogus"])
        assert exit_info.value.code == 2
        assert "invalid choice" in capsys.readouterr().err

    def test_empty_directory_exits_cleanly(self, capsys, tmp_path):
        code, out = call_main(capsys, str(tmp_path))
        assert code == 0
        assert "No valid images found" in out

    @pytest.mark.parametrize("name", ["notes.txt", ".bashrc", "authorized_keys", "run.log.py"])
    def test_rejects_log_without_log_suffix(self, capsys, tmp_path, name):
        log = tmp_path / "logs" / name
        code, out = call_main(capsys, str(tmp_path), "--log", str(log))
        assert code == 1
        assert "must end in .log" in out
        assert not log.parent.exists()

    @pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
    def test_rejects_symlinked_log(self, capsys, tmp_path):
        target = tmp_path / "profile"
        target.write_text("original\n", encoding="utf-8")
        log = tmp_path / "run.log"
        log.symlink_to(target)
        code, out = call_main(capsys, str(tmp_path), "--log", str(log))
        assert code == 1
        assert "must not be a symlink" in out
        assert target.read_text(encoding="utf-8") == "original\n"

    def test_rejects_non_regular_log(self, capsys, tmp_path):
        log = tmp_path / "dir.log"
        log.mkdir()
        code, out = call_main(capsys, str(tmp_path), "--log", str(log))
        assert code == 1
        assert "must be a regular file" in out

    def test_lm_studio_without_host_uses_its_own_default(self, tmp_path, monkeypatch, no_quit_listener):
        make_image(tmp_path / "a.png")
        hosts = []

        def fake_client(backend, host, timeout):
            hosts.append(host)
            return FakeOpenAIClient()

        monkeypatch.setattr(img_tagger, "_create_client", fake_client)
        assert img_tagger.main([str(tmp_path), "--backend", "lm-studio"]) == 0
        img_tagger.process_directory(str(tmp_path), backend="lm-studio")
        assert hosts == [img_tagger.DEFAULT_HOSTS["lm-studio"]] * 4  # server check + tagging, two runs


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
            "--max-pixels",
            "--log",
            "--clear",
        ]:
            assert flag in result.stdout

    def test_log_file_created(self, tmp_path):
        log = tmp_path / "logs" / "run.log"
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 0
        assert log.parent.is_dir()

    def test_appends_to_existing_uppercase_log(self, tmp_path):
        log = tmp_path / "RUN.LOG"
        log.write_text("earlier run\n", encoding="utf-8")
        result = run("img_tagger.py", str(tmp_path), "--log", str(log))
        assert result.returncode == 0
        assert log.read_text(encoding="utf-8").startswith("earlier run\n")

    # Port 9 (discard) refuses connections, so the server check fails fast without a model server.
    DEAD_HOST = "http://127.0.0.1:9"

    def test_unreachable_server_stops_before_any_image(self, tmp_path):
        image = make_image(tmp_path / "a.png")
        log = tmp_path / "run.log"
        result = run("img_tagger.py", str(tmp_path), "--host", self.DEAD_HOST, "--log", str(log))
        assert result.returncode == 1
        assert f"Error: Could not reach the Ollama server at {self.DEAD_HOST}" in result.stdout
        assert "Processing images" not in result.stdout + result.stderr
        assert "Traceback" not in result.stdout + result.stderr
        text = log.read_text(encoding="utf-8")
        assert "Server check failed" in text
        assert "Traceback" in text
        assert not img_tagger.is_already_processed(image)

    def test_failed_image_prints_no_traceback(self, tmp_path, failing_ollama):
        make_image(tmp_path / "a.png")
        result = run("img_tagger.py", str(tmp_path), "--host", failing_ollama)
        assert result.returncode == 0
        assert "Failed images: 1" in result.stdout
        assert "stub failure" in result.stdout
        assert "Traceback" not in result.stdout + result.stderr

    def test_log_file_records_run(self, tmp_path, failing_ollama):
        images = tmp_path / "images"
        images.mkdir()
        make_image(images / "a.png")
        log = tmp_path / "run.log"
        result = run("img_tagger.py", str(images), "--host", failing_ollama, "--timeout", "30", "--log", str(log))

        assert result.returncode == 0
        assert "Traceback" not in result.stderr
        text = log.read_text(encoding="utf-8")
        assert "Tagging 1 images" in text
        assert "workers=1, timeout=30s" in text
        assert "[DEBUG]" in text
        assert "Prompt: " in text
        assert "Server check passed" in text
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


class TestFolderPaths:
    def test_leading_parent_reference_works(self, capsys, tmp_path, monkeypatch):
        images = tmp_path / "images"
        images.mkdir()
        make_image(images / "a.png")
        (tmp_path / "work").mkdir()
        monkeypatch.chdir(tmp_path / "work")
        code, out = call_main(capsys, "../images", "--clear")
        assert code == 0
        assert "Resetting tags for 1 images" in out

    def test_inner_parent_reference_is_an_error_not_a_traceback(self, capsys, tmp_path):
        (tmp_path / "a").mkdir()
        (tmp_path / "images").mkdir()
        code, out = call_main(capsys, str(tmp_path / "a" / ".." / "images"), "--clear")
        assert code == 1
        assert "Error: Image paths must not contain '..'" in out

    @pytest.mark.skipif(os.name == "nt", reason="POSIX folder permissions")
    @pytest.mark.parametrize("clear", [False, True])
    def test_group_writable_folder_is_an_error_not_a_traceback(self, capsys, tmp_path, clear):
        folder = tmp_path / "shared"
        folder.mkdir()
        make_image(folder / "a.png")
        folder.chmod(0o775)
        code, out = call_main(capsys, str(folder), *(["--clear"] if clear else []))
        assert code == 1
        assert f"Error: Image folder must not be writable by its group or other users (chmod go-w): {folder}" in out


@pytest.fixture
def restore_logging():
    """Undo setup_logging() for in-process tests: remove our handler and the levels it set."""
    import logging

    root = logging.getLogger()
    level = root.level
    yield
    for handler in [h for h in root.handlers if isinstance(h, img_tagger._LogHandler)]:
        root.removeHandler(handler)
        handler.close()
    root.setLevel(level)
    img_tagger.logger.setLevel(logging.NOTSET)


class TestSetupLogging:
    def test_invalid_arguments_create_no_log(self, capsys, tmp_path):
        log = tmp_path / "logs" / "run.log"
        code, out = call_main(capsys, str(tmp_path), "--workers", "9", "--log", str(log))
        assert code == 1
        assert "Workers must be between 1 and 4" in out
        assert not log.parent.exists()

    def test_logs_beside_existing_root_handlers_and_replaces_an_earlier_log(self, tmp_path, restore_logging):
        import logging

        assert logging.getLogger().handlers  # pytest's capture handlers: basicConfig() would do nothing
        first, second = tmp_path / "first.log", tmp_path / "second.log"
        img_tagger.setup_logging(str(first))
        handler = next(h for h in logging.getLogger().handlers if isinstance(h, img_tagger._LogHandler))
        img_tagger.logger.info("one")
        img_tagger.setup_logging(str(second))
        img_tagger.logger.info("two")

        assert handler.stream.closed  # the replaced log is closed, not leaked
        handler.close()  # closing again (e.g. logging.shutdown()) is harmless
        assert sum(isinstance(h, img_tagger._LogHandler) for h in logging.getLogger().handlers) == 1
        assert "one" in first.read_text(encoding="utf-8")
        assert "two" not in first.read_text(encoding="utf-8")
        assert "two" in second.read_text(encoding="utf-8")


class TestOpenLog:
    """setup_logging() opens the log once, so a swap after _log_path_error() can't redirect appends."""

    def test_symlink_swapped_in_after_validation_is_refused(self, tmp_path):
        target = tmp_path / "profile"
        target.write_text("original\n", encoding="utf-8")
        log = tmp_path / "run.log"
        assert img_tagger._log_path_error(str(log)) is None  # validated while it doesn't exist yet
        try:
            log.symlink_to(target)
        except OSError as error:
            pytest.skip(f"Symlink creation unavailable: {error}")
        with pytest.raises(OSError):
            img_tagger.setup_logging(str(log))
        assert target.read_text(encoding="utf-8") == "original\n"

    @pytest.mark.skipif(os.name == "nt", reason="POSIX FIFOs")
    def test_fifo_is_refused_without_blocking(self, tmp_path):
        log = tmp_path / "pipe.log"
        os.mkfifo(log)
        with pytest.raises(OSError):
            img_tagger.setup_logging(str(log))

    @pytest.mark.skipif(os.name == "nt", reason="POSIX file ownership")
    def test_log_owned_by_another_user_is_refused(self, tmp_path, monkeypatch):
        log = tmp_path / "run.log"
        log.write_text("someone else's\n", encoding="utf-8")
        monkeypatch.setattr(img_tagger.os, "geteuid", lambda: log.stat().st_uid + 1)
        with pytest.raises(OSError, match="belong"):
            img_tagger.setup_logging(str(log))
        assert log.read_text(encoding="utf-8") == "someone else's\n"

    def test_main_reports_unopenable_log(self, capsys, tmp_path, monkeypatch):
        def refuse(path):
            raise OSError(1, "The log file must belong to the current user", str(path))

        monkeypatch.setattr(img_tagger, "_open_log", refuse)
        code, out = call_main(capsys, str(tmp_path), "--log", str(tmp_path / "run.log"))
        assert code == 1
        assert "Could not open the log file" in out


class TestMaxPixels:
    @pytest.mark.parametrize("value", ["-1", "nan", "inf"])
    def test_rejects_negative_or_nan(self, capsys, tmp_path, value):
        code, out = call_main(capsys, str(tmp_path), "--max-pixels", value)
        assert code == 1
        assert "Max pixels must be zero or a positive number" in out

    @pytest.mark.parametrize(
        ("value", "expected"), [(None, img_tagger.DEFAULT_MAX_MEGAPIXELS), ("0", 0.0), ("2.5", 2.5)]
    )
    def test_reaches_the_backend_call(self, tmp_path, monkeypatch, no_quit_listener, value, expected):
        make_image(tmp_path / "a.png")
        budgets = []

        def fake_get_tags(client, model, img_path, prompt, max_megapixels, data=None):
            budgets.append(max_megapixels)
            return ", ".join(SAMPLE_TAGS)

        monkeypatch.setattr(img_tagger, "_create_client", lambda *args: FakeOllamaClient())
        monkeypatch.setattr(img_tagger, "get_tags_ollama", fake_get_tags)
        args = [str(tmp_path)] + (["--max-pixels", value] if value else [])
        assert img_tagger.main(args) == 0
        assert budgets == [expected]


def test_log_stream_tolerates_undecodable_file_names(tmp_path):
    log = tmp_path / "run.log"
    stream = img_tagger._open_log(log)
    try:
        stream.write("Processing caf\udce9.jpg\n")  # how a Latin-1 name arrives on POSIX (surrogateescape)
    finally:
        stream.close()
    assert log.read_text(encoding="utf-8") == r"Processing caf\udce9.jpg" + "\n"  # escaped, not dropped


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_new_log_is_private(tmp_path):
    log = tmp_path / "run.log"
    img_tagger._open_log(log).close()
    assert log.stat().st_mode & 0o077 == 0


def test_log_keeps_a_more_verbose_root_level_and_filters_other_debug(tmp_path, restore_logging):
    import logging

    logging.getLogger().setLevel(logging.DEBUG)  # an embedding application's own setting
    log = tmp_path / "run.log"
    img_tagger.setup_logging(str(log))
    logging.getLogger("other.library").debug("noise")
    logging.getLogger("other.library").info("request line")
    img_tagger.logger.debug("our detail")

    assert logging.getLogger().level == logging.DEBUG
    text = log.read_text(encoding="utf-8")
    assert "noise" not in text
    assert "request line" in text
    assert "our detail" in text
