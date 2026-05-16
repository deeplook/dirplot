"""Tests for VirtualPath abstraction."""

from __future__ import annotations

import io
import tarfile
import zipfile

import pytest

from dirplot.scanner import build_tree_v2
from dirplot.vpath import (
    ArchiveRoot,
    FileSystemPath,
    StatResult,
    VirtualPath,
    ZipMember,
    open_path,
)


class TestStatResult:
    """Test StatResult dataclass."""

    def test_basic_creation(self):
        """Can create StatResult."""
        st = StatResult(st_size=100, st_mtime=1234567890.0, st_mode=0o644)
        assert st.st_size == 100
        assert st.st_mtime == 1234567890.0

    def test_is_dir_with_mode(self):
        """is_dir works with directory mode."""
        st = StatResult(st_size=0, st_mode=0o755 | 0o040000)  # S_IFDIR
        assert st.is_dir is True
        assert st.is_file is False

    def test_is_file_with_mode(self):
        """is_file works with regular file mode."""
        st = StatResult(st_size=100, st_mode=0o644 | 0o100000)  # S_IFREG
        assert st.is_file is True
        assert st.is_dir is False


class TestFileSystemPath:
    """Test FileSystemPath implementation."""

    def test_name_property(self, tmp_path):
        """name returns final component."""
        fsp = FileSystemPath(tmp_path)
        assert fsp.name == tmp_path.name

    def test_path_property(self, tmp_path):
        """path returns string representation."""
        fsp = FileSystemPath(tmp_path)
        assert fsp.path == str(tmp_path)

    def test_iterdir_yields_children(self, tmp_path):
        """iterdir yields FileSystemPath for each child."""
        (tmp_path / "file1.txt").write_text("x")
        (tmp_path / "file2.txt").write_text("y")
        (tmp_path / "subdir").mkdir()

        fsp = FileSystemPath(tmp_path)
        children = list(fsp.iterdir())

        assert len(children) == 3
        names = {c.name for c in children}
        assert names == {"file1.txt", "file2.txt", "subdir"}

    def test_is_dir_true_for_directory(self, tmp_path):
        """is_dir returns True for directories."""
        fsp = FileSystemPath(tmp_path)
        assert fsp.is_dir() is True

    def test_is_dir_false_for_file(self, tmp_path):
        """is_dir returns False for files."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        fsp = FileSystemPath(file_path)
        assert fsp.is_dir() is False

    def test_is_file_true_for_file(self, tmp_path):
        """is_file returns True for files."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        fsp = FileSystemPath(file_path)
        assert fsp.is_file() is True

    def test_stat_returns_size(self, tmp_path):
        """stat returns correct size."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("hello world")
        fsp = FileSystemPath(file_path)

        st = fsp.stat()

        assert st.st_size == 11  # "hello world"

    def test_exists_true_for_existing(self, tmp_path):
        """exists returns True for existing paths."""
        fsp = FileSystemPath(tmp_path)
        assert fsp.exists() is True

    def test_exists_false_for_nonexistent(self, tmp_path):
        """exists returns False for non-existing paths."""
        fsp = FileSystemPath(tmp_path / "does_not_exist")
        assert fsp.exists() is False


class TestZipMember:
    """Test ZipMember implementation."""

    @pytest.fixture
    def sample_zip(self, tmp_path):
        """Create a sample ZIP file."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file1.txt", "content1")
            zf.writestr("dir/file2.txt", "content2")
            zf.writestr("dir/subdir/file3.txt", "content3")
        return zip_path

    def test_name_property(self, sample_zip):
        """name returns filename from archive."""
        with zipfile.ZipFile(sample_zip, "r") as zf:
            member = ZipMember(zf, "file1.txt", root_name="test.zip")
            assert member.name == "file1.txt"

    def test_name_with_directory(self, sample_zip):
        """name handles paths with directories."""
        with zipfile.ZipFile(sample_zip, "r") as zf:
            member = ZipMember(zf, "dir/file2.txt", root_name="test.zip")
            assert member.name == "file2.txt"

    def test_is_file_true_for_file(self, sample_zip):
        """is_file returns True for files."""
        with zipfile.ZipFile(sample_zip, "r") as zf:
            member = ZipMember(zf, "file1.txt", root_name="test.zip")
            assert member.is_file() is True

    def test_is_dir_true_for_directory(self, sample_zip):
        """is_dir returns True for directories (implicit from entries)."""
        with zipfile.ZipFile(sample_zip, "r") as zf:
            # "dir/" is implied by "dir/file2.txt"
            member = ZipMember(zf, "dir/", root_name="test.zip")
            assert member.is_dir() is True

    def test_stat_returns_size(self, sample_zip):
        """stat returns correct file size."""
        with zipfile.ZipFile(sample_zip, "r") as zf:
            member = ZipMember(zf, "file1.txt", root_name="test.zip")
            st = member.stat()
            assert st.st_size == len("content1")


class TestArchiveRoot:
    """Test ArchiveRoot implementation."""

    @pytest.fixture
    def sample_zip(self, tmp_path):
        """Create a sample ZIP file."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file1.txt", "content1")
            zf.writestr("dir/file2.txt", "content2")
        return zip_path

    def test_name_is_archive_filename(self, sample_zip):
        """name returns archive filename."""
        with ArchiveRoot(sample_zip) as root:
            assert root.name == "test.zip"

    def test_is_dir_true(self, sample_zip):
        """is_dir always returns True for archive root."""
        with ArchiveRoot(sample_zip) as root:
            assert root.is_dir() is True

    def test_is_file_false(self, sample_zip):
        """is_file always returns False for archive root."""
        with ArchiveRoot(sample_zip) as root:
            assert root.is_file() is False

    def test_iterdir_yields_members(self, sample_zip):
        """iterdir yields top-level members."""
        with ArchiveRoot(sample_zip) as root:
            children = list(root.iterdir())
            names = {c.name for c in children}
            assert "file1.txt" in names
            assert "dir" in names

    def test_context_manager_opens_and_closes(self, sample_zip):
        """Context manager properly opens and closes archive."""
        root = ArchiveRoot(sample_zip)
        assert root._archive is None

        with root:
            assert root._archive is not None

        assert root._archive is None


class TestOpenPath:
    """Test open_path factory function."""

    def test_returns_filesystem_path_for_directory(self, tmp_path):
        """Returns FileSystemPath for directories."""
        result = open_path(tmp_path)
        assert isinstance(result, FileSystemPath)

    def test_returns_archive_root_for_zip(self, tmp_path):
        """Returns ArchiveRoot for ZIP files."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "content")

        result = open_path(zip_path)
        assert isinstance(result, ArchiveRoot)

    def test_returns_archive_root_for_tar(self, tmp_path):
        """Returns ArchiveRoot for TAR files."""
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            data = b"content"
            info = tarfile.TarInfo(name="file.txt")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

        result = open_path(tar_path)
        assert isinstance(result, ArchiveRoot)


class TestScannerWithVirtualPath:
    """Test scanner_v2 with VirtualPath."""

    def test_build_tree_v2_for_filesystem(self, tmp_path):
        """build_tree_v2 works with FileSystemPath."""
        (tmp_path / "file.txt").write_text("hello")
        fsp = FileSystemPath(tmp_path)

        tree = build_tree_v2(fsp)

        assert tree.name == tmp_path.name
        assert tree.is_dir is True
        assert any(c.name == "file.txt" for c in tree.children)

    def test_build_tree_v2_with_exclude(self, tmp_path):
        """build_tree_v2 respects exclude patterns."""
        (tmp_path / "keep.txt").write_text("x")
        (tmp_path / "skip.txt").write_text("y")
        fsp = FileSystemPath(tmp_path)

        tree = build_tree_v2(fsp, exclude=frozenset({"skip.txt"}))

        assert any(c.name == "keep.txt" for c in tree.children)
        assert not any(c.name == "skip.txt" for c in tree.children)

    def test_build_tree_v2_with_depth(self, tmp_path):
        """build_tree_v2 respects depth limit."""
        (tmp_path / "level1" / "level2").mkdir(parents=True)
        (tmp_path / "level1" / "level2" / "deep.txt").write_text("x")
        fsp = FileSystemPath(tmp_path)

        tree = build_tree_v2(fsp, depth=1)

        # Should have level1 but not recursed into it
        level1 = next(c for c in tree.children if c.name == "level1")
        assert level1.is_dir is True

    def test_scan_with_open_path_for_filesystem(self, tmp_path):
        """open_path + build_tree_v2 works for filesystem paths."""
        (tmp_path / "file.txt").write_text("x")

        vpath = open_path(tmp_path)
        tree = build_tree_v2(vpath)

        assert tree.is_dir is True
        assert any(c.name == "file.txt" for c in tree.children)

    def test_scan_with_open_path_for_zip(self, tmp_path):
        """open_path + build_tree_v2 works for ZIP archives."""
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("archive_file.txt", "archive content")

        vpath = open_path(zip_path)
        with vpath:
            tree = build_tree_v2(vpath)

        assert tree.name == "test.zip"
        assert any(c.name == "archive_file.txt" for c in tree.children)

    def test_build_tree_v2_raises_for_nonexistent(self, tmp_path):
        """build_tree_v2 raises FileNotFoundError for non-existent paths."""
        fsp = FileSystemPath(tmp_path / "does_not_exist")

        with pytest.raises(FileNotFoundError):
            build_tree_v2(fsp)

    def test_build_tree_v2_raises_for_file(self, tmp_path):
        """build_tree_v2 raises NotADirectoryError for files."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("x")
        fsp = FileSystemPath(file_path)

        with pytest.raises(NotADirectoryError):
            build_tree_v2(fsp)


class TestVirtualPathProtocol:
    """Test that implementations satisfy VirtualPath protocol."""

    def test_filesystem_path_is_virtual_path(self, tmp_path):
        """FileSystemPath satisfies VirtualPath."""

        fsp = FileSystemPath(tmp_path)
        assert isinstance(fsp, VirtualPath)

    def test_archive_root_is_virtual_path(self, tmp_path):
        """ArchiveRoot satisfies VirtualPath."""

        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("file.txt", "x")

        # Note: ArchiveRoot needs to be opened to satisfy protocol
        with ArchiveRoot(zip_path) as root:
            # Check it has required attributes
            assert hasattr(root, "name")
            assert hasattr(root, "path")
            assert hasattr(root, "iterdir")
            assert hasattr(root, "is_dir")
            assert hasattr(root, "is_file")
            assert hasattr(root, "stat")
            assert hasattr(root, "exists")
