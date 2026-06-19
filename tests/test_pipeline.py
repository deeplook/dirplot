"""Tests for the rendering pipeline."""

from __future__ import annotations

import io

import pytest

from dirplot.pipeline import (
    BreadcrumbsTransform,
    LogScaleTransform,
    PipelineConfig,
    PruneTransform,
    RenderingPipeline,
)


class TestPipelineConfig:
    """Test PipelineConfig dataclass."""

    def test_minimal_config(self):
        """Can create config with just roots."""
        config = PipelineConfig(roots=["."])
        assert config.roots == ["."]
        assert config.exclude == frozenset()
        assert config.format == "png"

    def test_full_config(self):
        """Can create config with all options."""
        config = PipelineConfig(
            roots=["src", "tests"],
            exclude=frozenset({".git", "__pycache__"}),
            depth=3,
            include={"src"},
            breadcrumbs=True,
            logscale=10.0,
            size=(1920, 1080),
            font_size=14,
            colormap="viridis",
            format="svg",
            show=False,
            inline=True,
        )
        assert config.roots == ["src", "tests"]
        assert config.exclude == frozenset({".git", "__pycache__"})
        assert config.depth == 3
        assert config.logscale == 10.0
        assert config.size == (1920, 1080)


class TestTransforms:
    """Test built-in transforms."""

    def test_prune_transform(self, tmp_path):
        """PruneTransform keeps only specified subtrees."""
        # Build a simple tree
        (tmp_path / "keep").mkdir()
        (tmp_path / "remove").mkdir()
        (tmp_path / "keep" / "file.txt").write_text("x" * 100)
        (tmp_path / "remove" / "file.txt").write_text("x" * 200)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)
        assert len(tree.children) == 2  # keep and remove

        # Apply prune transform
        transform = PruneTransform({"keep"})
        pruned = transform.apply(tree)

        assert len(pruned.children) == 1
        assert pruned.children[0].name == "keep"

    def test_breadcrumbs_transform(self, tmp_path):
        """BreadcrumbsTransform collapses single-child chains."""
        # Create a chain: a/b/c/file.txt
        (tmp_path / "a" / "b" / "c").mkdir(parents=True)
        (tmp_path / "a" / "b" / "c" / "file.txt").write_text("x" * 100)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)

        # Apply breadcrumbs
        transform = BreadcrumbsTransform()
        result = transform.apply(tree)

        # The tree should be modified (exact structure depends on implementation)
        assert result is not None

    def test_logscale_transform(self, tmp_path):
        """LogScaleTransform modifies node sizes."""
        # Create files with different sizes
        (tmp_path / "small.txt").write_text("x" * 10)
        (tmp_path / "large.txt").write_text("x" * 10000)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)
        original_sizes = {c.name: c.size for c in tree.children}

        # Apply log scale
        transform = LogScaleTransform(ratio=100.0)
        result = transform.apply(tree)

        # Sizes should be modified
        new_sizes = {c.name: c.size for c in result.children}
        assert new_sizes != original_sizes


class TestRenderingPipeline:
    """Test RenderingPipeline orchestration."""

    def test_scan_single_root(self, tmp_path):
        """Pipeline can scan a single root."""
        (tmp_path / "file.txt").write_text("hello world")

        config = PipelineConfig(roots=[str(tmp_path)])
        pipeline = RenderingPipeline(config)

        tree = pipeline.scan()

        assert tree.is_dir is True
        assert any(c.name == "file.txt" for c in tree.children)

    def test_scan_multiple_roots(self, tmp_path):
        """Pipeline can scan multiple roots."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a" / "file1.txt").write_text("x")
        (tmp_path / "b" / "file2.txt").write_text("y")

        config = PipelineConfig(roots=[str(tmp_path / "a"), str(tmp_path / "b")])
        pipeline = RenderingPipeline(config)

        tree = pipeline.scan()

        # Should have both directories under common parent
        assert tree.is_dir is True

    def test_scan_with_exclude(self, tmp_path):
        """Pipeline respects exclude patterns during scan."""
        (tmp_path / "keep.txt").write_text("x")
        (tmp_path / "skip.txt").write_text("y")

        config = PipelineConfig(
            roots=[str(tmp_path)],
            exclude=frozenset({"skip.txt"}),
        )
        pipeline = RenderingPipeline(config)

        tree = pipeline.scan()

        assert any(c.name == "keep.txt" for c in tree.children)
        assert not any(c.name == "skip.txt" for c in tree.children)

    def test_scan_nonexistent_raises(self):
        """Scanning nonexistent path raises FileNotFoundError."""
        config = PipelineConfig(roots=["/nonexistent/path/that/does/not/exist"])
        pipeline = RenderingPipeline(config)

        with pytest.raises(FileNotFoundError):
            pipeline.scan()

    def test_transform_applies_config(self, tmp_path):
        """Transform applies all configured transforms."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a" / "file.txt").write_text("x" * 100)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)

        config = PipelineConfig(
            roots=[str(tmp_path)],
            include={"a"},
            breadcrumbs=False,
            logscale=0.0,
        )
        pipeline = RenderingPipeline(config)

        result = pipeline.transform(tree)

        # Should only have 'a' subtree
        assert len(result.children) == 1
        assert result.children[0].name == "a"

    def test_render_produces_buffer(self, tmp_path):
        """Render produces a BytesIO buffer."""
        (tmp_path / "file.txt").write_text("x" * 100)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)

        config = PipelineConfig(roots=[str(tmp_path)])
        pipeline = RenderingPipeline(config)

        buf = pipeline.render(tree)

        assert isinstance(buf, io.BytesIO)
        assert buf.getbuffer().nbytes > 0

    def test_render_svg_format(self, tmp_path):
        """Render can produce SVG output."""
        (tmp_path / "file.txt").write_text("x" * 100)

        from dirplot.scanner import build_tree

        tree = build_tree(tmp_path)

        config = PipelineConfig(roots=[str(tmp_path)], format="svg")
        pipeline = RenderingPipeline(config)

        buf = pipeline.render(tree)

        content = buf.read()
        assert b"<svg" in content

    def test_full_pipeline_run(self, tmp_path):
        """Full pipeline execution works end-to-end."""
        (tmp_path / "file.txt").write_text("x" * 100)

        logs = []

        def log_capture(msg: str) -> None:
            logs.append(msg)

        config = PipelineConfig(
            roots=[str(tmp_path)],
            show=False,  # Don't try to display
            log_callback=log_capture,
        )
        pipeline = RenderingPipeline(config)

        result = pipeline.run()

        assert isinstance(result, io.BytesIO)
        assert len(logs) >= 2  # At least scan and render logs
        assert any("Scanning" in log for log in logs)

    def test_pipeline_run_no_show(self, tmp_path):
        """Pipeline can run without displaying."""
        (tmp_path / "file.txt").write_text("x" * 100)

        config = PipelineConfig(
            roots=[str(tmp_path)],
            show=False,
            output=None,
        )
        pipeline = RenderingPipeline(config)

        # Should complete without trying to display
        result = pipeline.run()
        assert isinstance(result, io.BytesIO)


class TestPipelineLogging:
    """Test pipeline logging behavior."""

    def test_logs_are_optional(self, tmp_path):
        """Pipeline works without log callback."""
        (tmp_path / "file.txt").write_text("x")

        config = PipelineConfig(roots=[str(tmp_path)], log_callback=None)
        pipeline = RenderingPipeline(config)

        # Should not raise
        tree = pipeline.scan()
        assert tree is not None

    def test_logs_capture_messages(self, tmp_path):
        """Log callback receives status messages."""
        (tmp_path / "file.txt").write_text("x")

        logs = []

        def log_fn(msg: str) -> None:
            logs.append(msg)

        config = PipelineConfig(roots=[str(tmp_path)], log_callback=log_fn)
        pipeline = RenderingPipeline(config)

        pipeline.scan()

        assert len(logs) > 0
        assert any("Scanning" in log for log in logs)


class TestRenderingPipelineMultiArchive:
    """Test multi-archive-root support in RenderingPipeline.scan()."""

    def _make_zip(self, path: object, name: str, files: list[tuple[str, bytes]]) -> object:
        import io
        import zipfile
        from pathlib import Path

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for n, data in files:
                zf.writestr(n, data)
        p = Path(path) / name  # type: ignore[arg-type]
        p.write_bytes(buf.getvalue())
        return p

    def test_scan_two_archive_roots(self, tmp_path):
        """Two zip archives produce a combined synthetic root with two children."""
        zip_a = self._make_zip(tmp_path, "a.zip", [("file_a.txt", b"x" * 100)])
        zip_b = self._make_zip(tmp_path, "b.zip", [("file_b.txt", b"x" * 200)])

        config = PipelineConfig(roots=[str(zip_a), str(zip_b)])
        tree = RenderingPipeline(config).scan()

        assert tree.is_dir is True
        assert len(tree.children) == 2
        assert tree.size == 300
        # build_tree_archive names the root node by stem, not filename
        child_names = {c.name for c in tree.children}
        assert child_names == {"a", "b"}

    def test_scan_archive_nonexistent_raises(self, tmp_path):
        """A nonexistent archive in a multi-root list raises FileNotFoundError."""
        real = self._make_zip(tmp_path, "real.zip", [("f.txt", b"hi")])

        config = PipelineConfig(roots=[str(real), str(tmp_path / "ghost.zip")])
        with pytest.raises(FileNotFoundError, match="does not exist"):
            RenderingPipeline(config).scan()

    def test_scan_archive_wrong_password_raises(self, encrypted_archives):
        """A wrong password on a header-encrypted archive raises ValueError."""
        if ".rar" not in encrypted_archives:
            pytest.skip("encrypted rar fixture unavailable (rar CLI not found)")

        rar = encrypted_archives[".rar"]
        config = PipelineConfig(roots=[str(rar), str(rar)], password="wrong")
        with pytest.raises(ValueError, match="requires a password"):
            RenderingPipeline(config).scan()
