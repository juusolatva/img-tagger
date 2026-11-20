"""Regression tests for image disclosure and redirected temporary-file writes."""

import errno
import os
import stat
import struct
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from conftest import SAMPLE_TAGS, FakeOllamaClient, FakeOpenAIClient, make_gif, make_image

import img_tagger

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows handles, junctions and DACLs")


def link_or_skip(link: Path, target: Path) -> None:
    """Create a test link where the platform permits it (a junction for Windows folders)."""
    try:
        if os.name == "nt" and target.is_dir():
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
        else:
            link.symlink_to(target, target_is_directory=target.is_dir())
    except OSError as error:
        pytest.skip(f"Symlink creation unavailable: {error}")


@pytest.mark.parametrize("extension", ["jpg", "png", "webp", "gif"])
@pytest.mark.parametrize("parent_link", [False, True])
def test_link_sources_never_reach_backend_or_writers(tmp_path, extension, parent_link, capsys):
    private = tmp_path / "private"
    private.mkdir()
    target = private / f"secret.{extension}"
    (make_gif if extension == "gif" else make_image)(target)
    original = target.read_bytes()
    if parent_link:
        link_or_skip(tmp_path / "linked", private)
        candidate = tmp_path / "linked" / target.name
    else:
        candidate = tmp_path / f"linked.{extension}"
        link_or_skip(candidate, target)

    for backend, client in [("ollama", FakeOllamaClient()), ("lm-studio", FakeOpenAIClient())]:
        result = img_tagger.process_single_image(candidate, client, backend, "m", "p", threading.Event())
        assert result[0] == "FAILED"
        assert client.calls == []
        helper = img_tagger.get_tags_ollama if backend == "ollama" else img_tagger.get_tags_lm_studio
        with pytest.raises(OSError):
            helper(client, "m", candidate, "p")
        assert client.calls == []

    for writer in [img_tagger.tag_image, img_tagger.write_metadata, img_tagger.write_gif_tags]:
        with pytest.raises((OSError, RuntimeError)):
            writer(str(candidate), SAMPLE_TAGS)
    img_tagger.clear_tags(candidate)
    assert "Failed to clear" in capsys.readouterr().out
    assert target.read_bytes() == original
    assert list(tmp_path.rglob("*.tmp")) == []


def test_discovery_ignores_leaf_links_and_rejects_linked_root(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    image = make_image(real / "a.png")
    link_or_skip(real / "linked.png", image)
    assert img_tagger._find_images(str(real), False) == [image]
    link_or_skip(tmp_path / "linked-root", real)
    with pytest.raises(OSError):
        img_tagger._find_images(str(tmp_path / "linked-root"), True)


@pytest.mark.skipif(os.name == "nt", reason="POSIX allows unlinking an open file")
@pytest.mark.parametrize("extension", ["jpg", "png", "webp", "gif"])
@pytest.mark.parametrize("clear", [False, True])
def test_substituted_temporary_never_writes_sentinel(tmp_path, monkeypatch, extension, clear, capsys):
    image = tmp_path / f"a.{extension}"
    (make_gif if extension == "gif" else make_image)(image)
    original = image.read_bytes()
    sentinel = tmp_path / "unrelated.txt"
    sentinel.write_bytes(b"must remain untouched")
    sentinel.chmod(0o640)
    real_create = img_tagger._create_image_temp

    def substituted(*args, **kwargs):
        fd, name = real_create(*args, **kwargs)
        Path(name).unlink()
        Path(name).symlink_to(sentinel)
        return fd, name

    monkeypatch.setattr(img_tagger, "_create_image_temp", substituted)
    if clear:
        img_tagger.clear_tags(image)
        assert "Failed to clear" in capsys.readouterr().out
    else:
        with pytest.raises(RuntimeError, match="File changed"):
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert sentinel.read_bytes() == b"must remain untouched"
    assert stat.S_IMODE(sentinel.stat().st_mode) == 0o640
    assert image.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX directory permissions and FIFOs")
def test_rejects_shared_directory_and_nonregular_input(tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir()
    image = make_image(shared / "a.png")
    shared.chmod(0o777)
    try:
        with pytest.raises(img_tagger._UnsafeImagePath, match="writable"):
            img_tagger._read_image_bytes(image)
    finally:
        shared.chmod(0o700)
    fifo = tmp_path / "pipe.png"
    os.mkfifo(fifo)
    with pytest.raises(img_tagger._UnsafeImagePath, match="regular"):
        img_tagger._read_image_bytes(fifo)


def test_ollama_receives_snapshot_even_if_path_changes_during_request(tmp_path):
    image = make_image(tmp_path / "a.png")
    expected = image.read_bytes()
    private = make_image(tmp_path / "private.png", color=(1, 2, 3))

    class ReplacingClient(FakeOllamaClient):
        def chat(self, model, messages):
            image.unlink()
            link_or_skip(image, private)
            return super().chat(model, messages)

    client = ReplacingClient()
    img_tagger.get_tags_ollama(client, "m", image, "p", max_megapixels=0)
    assert client.calls[0]["messages"][0]["images"] == [expected]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux POSIX ACL extended attributes")
@pytest.mark.parametrize("clear", [False, True])
@pytest.mark.parametrize("extension", ["png", "gif"])
def test_preserves_acl_instead_of_granting_acl_mask_to_owning_group(tmp_path, clear, extension):
    image = tmp_path / f"acl.{extension}"
    (make_gif if extension == "gif" else make_image)(image)
    entries = [(1, 6, 0xFFFFFFFF), (2, 6, os.geteuid()), (4, 0, 0xFFFFFFFF), (16, 6, 0xFFFFFFFF), (32, 4, 0xFFFFFFFF)]
    acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)
    try:
        os.setxattr(image, "system.posix_acl_access", acl)
    except OSError as error:
        pytest.skip(f"ACLs unavailable on test filesystem: {error}")
    before = os.getxattr(image, "system.posix_acl_access")
    if clear:
        img_tagger.clear_tags(image)
    else:
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert os.getxattr(image, "system.posix_acl_access") == before
    assert stat.S_IMODE(image.stat().st_mode) == 0o664


@pytest.mark.skipif(os.name == "nt", reason="POSIX descriptor-relative operations")
def test_parent_rename_does_not_redirect_temporary_creation_or_commit(tmp_path, monkeypatch):
    folder = tmp_path / "images"
    folder.mkdir()
    image = make_image(folder / "a.png")
    moved = tmp_path / "moved"
    real_create = img_tagger._create_image_temp

    def rename_parent(directory, *args):
        folder.rename(moved)
        folder.mkdir()
        (folder / image.name).write_bytes(b"unrelated replacement directory")
        return real_create(directory, *args)

    monkeypatch.setattr(img_tagger, "_create_image_temp", rename_parent)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert image.read_bytes() == b"unrelated replacement directory"
    assert img_tagger.is_already_processed(moved / image.name)
    assert list(tmp_path.rglob("*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX no-follow leaf open")
def test_leaf_substitution_between_parent_open_and_read_is_rejected(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")
    private = make_image(tmp_path / "private.png")
    real_open = os.open

    def substitute(path, flags, *args, **kwargs):
        if path == image.name:
            image.unlink()
            image.symlink_to(private)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", substitute)
    client = FakeOllamaClient()
    with pytest.raises(OSError):
        img_tagger.get_tags_ollama(client, "m", image, "p")
    assert client.calls == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX UID ownership checks")
def test_unmapped_owner_is_not_trusted_as_namespace_root_owner():
    unknown_uid = max(os.geteuid(), 65534) + 1
    info = SimpleNamespace(st_uid=unknown_uid, st_mode=stat.S_IFDIR | 0o755)
    with pytest.raises(img_tagger._UnsafeImagePath, match="belong"):
        img_tagger._check_directory(info)


@windows_only
def test_windows_leaf_reparse_point_is_rejected(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")
    real_fstat = os.fstat

    class Reparse:
        def __init__(self, info):
            self.info = info

        st_file_attributes = 0x400

        def __getattr__(self, name):
            return getattr(self.info, name)

    def reparse(fd):
        info = real_fstat(fd)
        return Reparse(info) if stat.S_ISREG(info.st_mode) else info  # folders are checked separately

    monkeypatch.setattr(img_tagger.os, "fstat", reparse)
    with pytest.raises(img_tagger._UnsafeImagePath, match="regular"):
        img_tagger._read_image_bytes(image)


@windows_only
def test_windows_ancestors_and_temporary_are_locked_during_edit(tmp_path, monkeypatch):
    outer = tmp_path / "outer"
    folder = outer / "images"
    folder.mkdir(parents=True)
    image = make_image(folder / "a.png")
    real_create = img_tagger._create_image_temp
    attempts = []

    def swap_attempts(directory, *args):
        fd, temporary = real_create(directory, *args)
        for ancestor in (folder, outer):
            with pytest.raises(PermissionError):
                ancestor.rename(tmp_path / "moved")
            attempts.append(ancestor)
        with pytest.raises(PermissionError):
            temporary.read_bytes()
        return fd, temporary

    monkeypatch.setattr(img_tagger, "_create_image_temp", swap_attempts)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert attempts == [folder, outer]
    assert img_tagger.is_already_processed(image)
    outer.rename(tmp_path / "moved")  # the pins are released afterwards


def windows_dacl(path: Path):
    fd = os.open(path, os.O_RDONLY)
    try:
        return img_tagger._windows_dacl(img_tagger._windows_security(fd))
    finally:
        os.close(fd)


def icacls(path: Path, *args: str) -> None:
    subprocess.run(["icacls", str(path), *args], check=True, capture_output=True)


@windows_only
@pytest.mark.parametrize("clear", [False, True])
@pytest.mark.parametrize("extension", ["png", "gif"])
@pytest.mark.parametrize("protected", [False, True])
def test_windows_preserves_restrictive_dacl(tmp_path, clear, extension, protected):
    image = tmp_path / f"acl.{extension}"
    (make_gif if extension == "gif" else make_image)(image)
    if protected:
        icacls(image, "/inheritance:r", "/grant:r", f"{os.environ['USERNAME']}:F", "*S-1-5-18:F")
    else:
        icacls(image, "/deny", "*S-1-5-32-546:R")  # explicit Guests deny on top of the inherited entries
    before = windows_dacl(image)
    if clear:
        img_tagger.clear_tags(image)
    else:
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert windows_dacl(image) == before
    assert list(tmp_path.glob("*.tmp")) == []


@windows_only
def test_windows_dacl_mismatch_fails_closed(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")
    original = image.read_bytes()
    real_dacl = img_tagger._windows_dacl
    calls = []

    def differing(security):
        calls.append(1)
        entries, protected = real_dacl(security)
        return (entries, not protected) if len(calls) == 1 else (entries, protected)

    monkeypatch.setattr(img_tagger, "_windows_dacl", differing)
    with pytest.raises(RuntimeError, match="permissions"):
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert image.read_bytes() == original
    assert list(tmp_path.glob("*.tmp")) == []


@windows_only
@pytest.mark.parametrize("clear", [False, True])
def test_windows_read_only_image_is_replaced_and_stays_read_only(tmp_path, clear):
    image = make_image(tmp_path / "a.jpg")
    image.chmod(stat.S_IREAD)
    try:
        if clear:
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
            img_tagger.clear_tags(image)
            assert not img_tagger.is_already_processed(image)
        else:
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
            assert img_tagger.is_already_processed(image)
        assert not os.access(image, os.W_OK)
        assert list(tmp_path.glob("*.tmp")) == []
    finally:
        image.chmod(stat.S_IREAD | stat.S_IWRITE)


@windows_only
def test_windows_failed_commit_discards_read_only_temporary(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.jpg")
    image.chmod(stat.S_IREAD)
    original = image.read_bytes()

    def changed(path, parent_fd, expected):
        raise img_tagger._UnsafeImagePath("File changed during processing")

    monkeypatch.setattr(img_tagger, "_check_replacement", changed)
    try:
        with pytest.raises(RuntimeError, match="File changed"):
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
        assert image.read_bytes() == original
        assert list(tmp_path.glob("*.tmp")) == []
    finally:
        image.chmod(stat.S_IREAD | stat.S_IWRITE)


@windows_only
def test_windows_rename_falls_back_without_rename_info_ex(tmp_path, monkeypatch):
    import ctypes

    image = make_image(tmp_path / "a.png")
    real = img_tagger._kernel32
    classes = []

    class NoRenameEx:
        def __getattr__(self, name):
            return getattr(real, name)

        def SetFileInformationByHandle(self, handle, info_class, info, size):
            classes.append(info_class)
            if info_class == img_tagger._Win.FILE_RENAME_INFO_EX:
                ctypes.set_last_error(87)  # ERROR_INVALID_PARAMETER, as on filesystems without it
                return 0
            return real.SetFileInformationByHandle(handle, info_class, info, size)

    monkeypatch.setattr(img_tagger, "_kernel32", NoRenameEx())
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert classes == [img_tagger._Win.FILE_RENAME_INFO_EX, img_tagger._Win.FILE_RENAME_INFO]
    assert img_tagger.is_already_processed(image)


@pytest.mark.skipif(not hasattr(os, "O_PATH"), reason="Linux execute-only directory handles")
def test_direct_reads_allow_execute_only_ancestors(tmp_path):
    ancestor = tmp_path / "execute-only"
    ancestor.mkdir()
    folder = ancestor / "images"
    folder.mkdir()
    image = make_image(folder / "a.png")
    ancestor.chmod(0o111)
    try:
        assert img_tagger.get_image_format(image) == "PNG"
    finally:
        ancestor.chmod(0o700)


@windows_only
def test_windows_interrupt_after_rename_keeps_committed_image(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")
    real_rename = img_tagger._rename_windows_handle

    def rename_then_interrupt(fd, target):
        real_rename(fd, target)
        raise KeyboardInterrupt  # Ctrl+C landing right after the rename completed

    monkeypatch.setattr(img_tagger, "_rename_windows_handle", rename_then_interrupt)
    with pytest.raises(KeyboardInterrupt):
        img_tagger.write_metadata(str(image), SAMPLE_TAGS)
    assert img_tagger.is_already_processed(image)
    assert list(tmp_path.glob("*.tmp")) == []


@windows_only
def test_windows_non_bmp_path_is_renamed_exactly(tmp_path):
    folder = tmp_path / "Trip \U0001f600\U0001f30d"
    folder.mkdir()
    image = make_image(folder / "a\U0001f600.jpg")
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert img_tagger.is_already_processed(image)
    assert sorted(p.name for p in folder.iterdir()) == [image.name]


@windows_only
@pytest.mark.parametrize("denied", [{0x20}, {0x20, 0x01}])
def test_windows_folder_without_traverse_right_still_works(tmp_path, monkeypatch, denied):
    folder = tmp_path / "list-only"
    folder.mkdir()
    image = make_image(folder / "a.png")
    real_open = img_tagger._win_open
    granted = []

    def restricted(path, access, *args, **kwargs):
        if path == folder and any(access & right for right in denied):
            raise PermissionError(13, "Access is denied", str(path))
        if path == folder:
            granted.append(access)
        return real_open(path, access, *args, **kwargs)

    monkeypatch.setattr(img_tagger, "_win_open", restricted)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert img_tagger.is_already_processed(image)
    expected = img_tagger._Win.FILE_READ_ATTRIBUTES | (0 if 0x01 in denied else img_tagger._Win.FILE_LIST_DIRECTORY)
    assert set(granted) == {expected}


@windows_only
def test_windows_volume_without_acls_skips_dacl_handling(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")

    def no_security(fd):
        raise AssertionError("DACL must not be read on a volume without ACLs")

    monkeypatch.setattr(img_tagger, "_windows_persistent_acls", lambda fd: False)
    monkeypatch.setattr(img_tagger, "_windows_security", no_security)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert img_tagger.is_already_processed(image)


class FakeXattrs:
    """
    In-memory extended attributes keyed by inode, standing in for an SELinux system where this user
    may not write security.* attributes: the source image's attributes, the temporary's defaults.
    """

    def __init__(self, monkeypatch, image: Path, source: dict[str, bytes], temporary: dict[str, bytes]):
        self.source_inode = image.stat().st_ino
        self.source, self.temporary = dict(source), dict(temporary)
        self.unreadable: dict[str, int] = {}
        self.written: list[str] = []
        for name in ("listxattr", "getxattr", "setxattr", "removexattr"):
            monkeypatch.setattr(img_tagger.os, name, getattr(self, name), raising=False)

    def _of(self, fd) -> dict[str, bytes]:
        return self.source if os.fstat(fd).st_ino == self.source_inode else self.temporary

    def listxattr(self, fd):
        return list(self._of(fd))

    def getxattr(self, fd, name):
        if name in self.unreadable:
            raise OSError(self.unreadable[name], os.strerror(self.unreadable[name]))
        return self._of(fd)[name]

    def setxattr(self, fd, name, value):
        if not name.startswith(("user.", "system.posix_acl")):
            raise PermissionError(errno.EACCES, "Permission denied")
        self.written.append(name)
        self._of(fd)[name] = value

    def removexattr(self, fd, name):
        if not name.startswith(("user.", "system.posix_acl")):
            raise PermissionError(errno.EACCES, "Permission denied")
        self.written.append(f"-{name}")
        del self._of(fd)[name]


@pytest.mark.skipif(os.name == "nt", reason="POSIX extended attributes")
class TestExtendedAttributes:
    """Only the access ACL, user.* and (best effort) the SELinux label are carried over (review finding 3)."""

    @pytest.mark.parametrize("clear", [False, True])
    def test_differing_selinux_label_does_not_fail_the_edit(self, tmp_path, monkeypatch, clear):
        image = make_image(tmp_path / "a.png")
        source = {"security.selinux": b"user_tmp_t\0", "user.origin": b"camera", "security.capability": b"cap"}
        fake = FakeXattrs(monkeypatch, image, source, {"security.selinux": b"user_home_t\0"})
        if clear:
            img_tagger.clear_tags(image)
        else:
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
        assert img_tagger.is_already_processed(image) is not clear
        assert fake.written == ["user.origin"]  # never security.capability, never removing the label
        assert fake.temporary == {"security.selinux": b"user_home_t\0", "user.origin": b"camera"}

    def test_inherited_default_acl_is_replaced_by_the_source_state(self, tmp_path, monkeypatch):
        image = make_image(tmp_path / "a.png")
        fake = FakeXattrs(monkeypatch, image, {}, {img_tagger.ACL_XATTR: b"inherited"})
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
        assert fake.written == [f"-{img_tagger.ACL_XATTR}"]

    def test_unreadable_acl_fails_closed(self, tmp_path, monkeypatch):
        image = make_image(tmp_path / "a.png")
        fake = FakeXattrs(monkeypatch, image, {img_tagger.ACL_XATTR: b"acl"}, {})
        fake.unreadable[img_tagger.ACL_XATTR] = errno.EACCES
        with pytest.raises(RuntimeError, match="Permission denied"):
            img_tagger.tag_image(str(image), SAMPLE_TAGS)
        assert not img_tagger.is_already_processed(image)
        assert [p.name for p in tmp_path.iterdir()] == ["a.png"]

    @pytest.mark.parametrize("error", [errno.ENODATA, errno.EACCES])
    def test_vanished_or_unreadable_user_attribute_is_skipped(self, tmp_path, monkeypatch, error):
        image = make_image(tmp_path / "a.png")
        fake = FakeXattrs(monkeypatch, image, {"user.gone": b"x", "user.kept": b"y"}, {})
        fake.unreadable["user.gone"] = error
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
        assert fake.temporary == {"user.kept": b"y"}


def test_reads_do_not_capture_permissions(tmp_path, monkeypatch):
    image = make_image(tmp_path / "a.png")

    def no_attributes(fd):
        raise AssertionError("only edits need the permissions")

    monkeypatch.setattr(img_tagger, "_file_attributes", no_attributes)
    assert img_tagger.get_image_format(image) == "PNG"
    assert not img_tagger.is_already_processed(image)


def other_group_or_skip(directory: Path) -> int:
    """
    A group of this user other than the one new files get, so the temporary's group differs. Only
    groups a file in directory can really be given count: in containers and user namespaces an
    unmapped supplementary group shows up as the overflow gid and chown() fails with EINVAL.
    """
    probe = directory / "group-probe"
    probe.touch()
    try:
        for group in os.getgroups():
            if group == os.getegid():
                continue
            try:
                os.chown(probe, -1, group)
            except OSError:
                continue
            return group
    finally:
        probe.unlink()
    pytest.skip("needs a user with a secondary group that files can be given")


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
@pytest.mark.parametrize("clear", [False, True])
@pytest.mark.parametrize("extension", ["png", "gif"])
def test_keeps_the_source_group_instead_of_the_temporary_one(tmp_path, clear, extension):
    image = tmp_path / f"a.{extension}"
    (make_gif if extension == "gif" else make_image)(image)
    group = other_group_or_skip(tmp_path)
    os.chown(image, -1, group)
    image.chmod(0o640)
    if clear:
        img_tagger.clear_tags(image)
    else:
        img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert image.stat().st_gid == group
    assert stat.S_IMODE(image.stat().st_mode) == 0o640


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
def test_unkeepable_group_drops_group_access(tmp_path, monkeypatch, capsys):
    image = make_image(tmp_path / "a.png")
    os.chown(image, -1, other_group_or_skip(tmp_path))
    image.chmod(0o640)

    def not_a_member(fd, uid, gid):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(img_tagger.os, "fchown", not_a_member)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert stat.S_IMODE(image.stat().st_mode) == 0o600
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
@pytest.mark.parametrize(
    ("source_mode", "expected"),
    # Source-group members become "others" once the group is gone: they must not gain the other bits
    [(0o604, 0o600), (0o644, 0o604), (0o664, 0o604), (0o2754, 0o2704), (0o640, 0o600)],
)
def test_unkeepable_group_never_widens_access_for_former_group(monkeypatch, capsys, source_mode, expected):
    source = os.stat_result((source_mode | stat.S_IFREG, 0, 0, 1, 0, 1000, 0, 0, 0, 0))
    monkeypatch.setattr(img_tagger.os, "fstat", lambda fd: os.stat_result((0o100600, 0, 0, 1, 0, 2000, 0, 0, 0, 0)))

    def not_a_member(fd, uid, gid):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(img_tagger.os, "fchown", not_a_member)
    assert img_tagger._restore_group(3, source, "a.png") == expected
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
@pytest.mark.parametrize(
    ("group_obj", "expected"),
    # mode 0664 with an ACL: its group bits are the mask (rw-), the owning group itself has group_obj
    [(0, 0o600), (4, 0o604), (6, 0o604), (None, 0o600)],
    ids=["group-denied", "group-read", "group-rw", "no-group-entry"],
)
def test_unkeepable_group_limits_others_by_the_acl_group_entry(monkeypatch, capsys, group_obj, expected):
    entries = [(1, 6, 0xFFFFFFFF), (16, 6, 0xFFFFFFFF), (32, 4, 0xFFFFFFFF)]  # user::rw- mask::rw- other::r--
    if group_obj is not None:
        entries.insert(1, (4, group_obj, 0xFFFFFFFF))
    acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)
    source = os.stat_result((0o100664, 0, 0, 1, 0, 1000, 0, 0, 0, 0))
    monkeypatch.setattr(img_tagger.os, "fstat", lambda fd: os.stat_result((0o100600, 0, 0, 1, 0, 2000, 0, 0, 0, 0)))

    def not_a_member(fd, uid, gid):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(img_tagger.os, "fchown", not_a_member)
    assert img_tagger._restore_group(3, source, "a.png", acl) == expected
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "linux", reason="Linux POSIX ACL extended attributes")
def test_unkeepable_group_with_group_denying_acl_keeps_former_group_out(tmp_path, monkeypatch, capsys):
    image = make_image(tmp_path / "a.png")
    os.chown(image, -1, other_group_or_skip(tmp_path))
    entries = [(1, 6, 0xFFFFFFFF), (4, 0, 0xFFFFFFFF), (16, 6, 0xFFFFFFFF), (32, 4, 0xFFFFFFFF)]
    acl = struct.pack("<I", 2) + b"".join(struct.pack("<HHI", *entry) for entry in entries)
    try:
        os.setxattr(image, img_tagger.ACL_XATTR, acl)  # group::--- mask::rw- other::r--, shown as 0664
    except OSError as error:
        pytest.skip(f"ACLs unavailable on test filesystem: {error}")
    assert stat.S_IMODE(image.stat().st_mode) == 0o664

    def not_a_member(fd, uid, gid):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(img_tagger.os, "fchown", not_a_member)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert stat.S_IMODE(image.stat().st_mode) & 0o077 == 0  # no group or other access left
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
def test_unkeepable_group_on_world_readable_but_group_denied_image(tmp_path, monkeypatch, capsys):
    image = make_image(tmp_path / "a.png")
    os.chown(image, -1, other_group_or_skip(tmp_path))
    image.chmod(0o604)  # the owning group may not read it, everybody else may

    def not_a_member(fd, uid, gid):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(img_tagger.os, "fchown", not_a_member)
    img_tagger.clear_tags(image)
    assert stat.S_IMODE(image.stat().st_mode) == 0o600
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX owning group")
@pytest.mark.parametrize("error", [errno.EINVAL, errno.EOPNOTSUPP, errno.ENOSYS])
def test_group_refused_by_filesystem_drops_group_access(tmp_path, monkeypatch, capsys, error):
    image = make_image(tmp_path / "a.png")
    os.chown(image, -1, other_group_or_skip(tmp_path))
    image.chmod(0o640)

    def refuse(fd, uid, gid):
        raise OSError(error, os.strerror(error))

    monkeypatch.setattr(img_tagger.os, "fchown", refuse)
    img_tagger.tag_image(str(image), SAMPLE_TAGS)
    assert img_tagger.is_already_processed(image)
    assert stat.S_IMODE(image.stat().st_mode) == 0o600
    assert "removed its group permissions" in capsys.readouterr().out


@pytest.mark.skipif(os.name == "nt", reason="POSIX folder permissions")
class TestGroupWritableFolder:
    """A folder its group may write (mkdir under umask 0002) is refused with the real reason, per image."""

    def test_tagging_fails_that_image_with_the_reason(self, tmp_path):
        folder = tmp_path / "shared"
        folder.mkdir(mode=0o775)
        folder.chmod(0o775)
        client = FakeOllamaClient()
        status, _, message, _ = img_tagger.process_single_image(
            make_image(folder / "a.png"), client, "ollama", "m", "p", threading.Event()
        )
        assert status == "FAILED"
        assert "must not be writable by its group or other users" in message
        assert str(folder) in message
        assert client.calls == []

    def test_clearing_reports_the_reason(self, tmp_path, capsys):
        folder = tmp_path / "shared"
        folder.mkdir()
        image = make_image(folder / "a.png")
        folder.chmod(0o775)
        img_tagger.clear_tags(image)
        assert "must not be writable by its group" in capsys.readouterr().out


@pytest.mark.parametrize("change", ["mtime", "size"])
def test_edit_by_another_program_during_the_write_is_not_overwritten(tmp_path, change):
    """Each _same_version() check on its own: same size with a new mtime, or a new size with the old mtime."""
    image = make_image(tmp_path / "a.png")
    before = image.stat()
    original = image.read_bytes()
    newer = bytes(reversed(original)) if change == "mtime" else original + b"appended"
    # set explicitly, so a coarse filesystem timestamp can't hide the change or leak one into the size case
    mtime_ns = before.st_mtime_ns + 1_000_000_000 if change == "mtime" else before.st_mtime_ns

    def edit_while_another_program_writes():
        with img_tagger._image_edit(image) as (source, output):
            output.write(source)
            image.write_bytes(newer)  # same file, before the commit
            os.utime(image, ns=(before.st_atime_ns, mtime_ns))

    with pytest.raises(img_tagger._UnsafeImagePath, match="changed during processing"):
        edit_while_another_program_writes()
    assert image.read_bytes() == newer
    assert [p.name for p in tmp_path.iterdir() if p.suffix == ".tmp"] == []
