"""Tests for the unified TreeSource system."""

from __future__ import annotations

from pathlib import Path

import pytest

from dirplot.scanner import Node
from dirplot.sources import (
    SourceRegistry,
    register_source,
    registry,
    scan_any,
)
from dirplot.sources.filesystem import FileSystemSource


class MockSource:
    """Mock source for testing."""

    def __init__(self, name: str, handles_prefix: str):
        self._name = name
        self._prefix = handles_prefix

    @property
    def name(self) -> str:
        return self._name

    def can_handle(self, path: str) -> bool:
        return path.startswith(self._prefix)

    def scan(
        self,
        path: str,
        *,
        exclude: frozenset[str] = frozenset(),
        depth: int | None = None,
    ) -> Node:
        return Node(name="mock", path=Path("/mock"), size=100, is_dir=True)

    def get_display_name(self, path: str) -> str:
        return f"mock:{path}"


class TestSourceRegistry:
    """Test the SourceRegistry class."""

    def test_empty_registry_raises(self):
        """Empty registry should raise ValueError for any path."""
        reg = SourceRegistry()
        with pytest.raises(ValueError, match="No source can handle"):
            reg.find_source("/some/path")

    def test_register_and_find(self):
        """Registering a source makes it findable."""
        reg = SourceRegistry()
        source = MockSource("test", "test://")

        reg.register(source)

        found = reg.find_source("test://something")
        assert found.name == "test"

    def test_find_returns_first_match(self):
        """First registered source that can handle path is returned."""
        reg = SourceRegistry()
        source1 = MockSource("first", "shared://")
        source2 = MockSource("second", "shared://")

        reg.register(source1)
        reg.register(source2)

        found = reg.find_source("shared://path")
        assert found.name == "first"

    def test_no_match_raises(self):
        """If no source can handle path, ValueError is raised."""
        reg = SourceRegistry()
        source = MockSource("test", "test://")
        reg.register(source)

        with pytest.raises(ValueError, match="No source can handle"):
            reg.find_source("other://path")

    def test_scan_delegates_to_source(self):
        """scan() finds source and delegates."""
        reg = SourceRegistry()
        source = MockSource("test", "test://")
        reg.register(source)

        result = reg.scan("test://path")

        assert result.name == "mock"
        assert result.size == 100

    def test_get_display_name_delegates_to_source(self):
        """get_display_name() finds source and delegates."""
        reg = SourceRegistry()
        source = MockSource("test", "test://")
        reg.register(source)

        display = reg.get_display_name("test://path")

        assert display == "mock:test://path"

    def test_sources_property_returns_copy(self):
        """sources property returns a copy of the list."""
        reg = SourceRegistry()
        source = MockSource("test", "test://")
        reg.register(source)

        sources1 = reg.sources
        sources2 = reg.sources

        assert sources1 == sources2
        assert sources1 is not sources2


class TestFileSystemSource:
    """Test the FileSystemSource implementation."""

    def test_name_is_filesystem(self):
        source = FileSystemSource()
        assert source.name == "filesystem"

    def test_can_handle_local_path(self):
        source = FileSystemSource()
        assert source.can_handle("/some/path") is True
        assert source.can_handle("./relative") is True
        assert source.can_handle("..") is True

    def test_rejects_urls(self):
        source = FileSystemSource()
        assert source.can_handle("github://owner/repo") is False
        assert source.can_handle("ssh://host/path") is False
        assert source.can_handle("s3://bucket/key") is False
        assert source.can_handle("docker://container:/path") is False

    def test_rejects_special_prefixes(self):
        source = FileSystemSource()
        assert source.can_handle("github://owner/repo") is False
        assert source.can_handle("hg://repo") is False
        assert source.can_handle("ssh://host/path") is False

    def test_scan_nonexistent_raises(self, tmp_path):
        source = FileSystemSource()
        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(FileNotFoundError):
            source.scan(str(nonexistent))

    def test_scan_directory_returns_node(self, tmp_path):
        source = FileSystemSource()
        # Create some files
        (tmp_path / "file1.txt").write_text("hello")
        (tmp_path / "file2.txt").write_text("world")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "nested.txt").write_text("nested")

        result = source.scan(str(tmp_path))

        assert result.name == tmp_path.name
        assert result.is_dir is True
        assert result.size > 0
        assert len(result.children) == 3  # 2 files + 1 subdir

    def test_scan_with_exclude(self, tmp_path):
        source = FileSystemSource()
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "skip.txt").write_text("skip")

        result = source.scan(str(tmp_path), exclude=frozenset({"skip.txt"}))

        assert len(result.children) == 1
        assert result.children[0].name == "keep.txt"

    def test_scan_with_depth(self, tmp_path):
        source = FileSystemSource()
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "deep.txt").write_text("deep")

        # depth=1 should only scan immediate children
        result = source.scan(str(tmp_path), depth=1)

        # level1 directory exists but hasn't been recursed
        level1 = next(c for c in result.children if c.name == "level1")
        assert level1.is_dir is True

    def test_get_display_name_resolves_path(self, tmp_path):
        source = FileSystemSource()
        result = source.get_display_name(str(tmp_path))

        assert Path(result).is_absolute()


class TestGlobalRegistry:
    """Test the global registry instance."""

    def test_global_registry_has_filesystem(self):
        """The global registry should have filesystem source registered."""
        sources = registry.sources
        names = [s.name for s in sources]
        assert "filesystem" in names

    def test_global_registry_can_scan_local_path(self, tmp_path):
        """Can scan a local path through the global registry."""
        (tmp_path / "test.txt").write_text("test content")

        result = scan_any(str(tmp_path))

        assert result.is_dir is True
        assert any(c.name == "test.txt" for c in result.children)

    def test_scan_any_raises_for_invalid_path(self):
        """scan_any raises ValueError for paths no source can handle."""
        # This path format is not handled by any source
        with pytest.raises(ValueError, match="No source can handle"):
            scan_any("unknown://invalid/path")


class TestRegisterSourceDecorator:
    """Test the @register_source decorator."""

    def test_decorator_registers_instance(self):
        """The decorator should work with instances (not classes)."""

        # Note: The decorator expects an instance, not a class
        # This is the correct usage pattern:
        class TestSourceClass:
            @property
            def name(self) -> str:
                return "test_instance_source"

            def can_handle(self, path: str) -> bool:
                return path.startswith("testinstance://")

            def scan(
                self,
                path: str,
                *,
                exclude: frozenset[str] = frozenset(),
                depth: int | None = None,
            ) -> Node:
                return Node(name="test", path=Path("/test"), size=1, is_dir=True)

            def get_display_name(self, path: str) -> str:
                return path

        # Create instance and register it
        instance = TestSourceClass()
        result = register_source(instance)

        # Should return the same instance
        assert result is instance
        # Should be registered in global registry
        names = [s.name for s in registry.sources]
        assert "test_instance_source" in names
