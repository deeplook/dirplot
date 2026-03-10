"""Tests for Docker container directory scanning."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dirplot.docker import (
    _entries_to_tree,
    build_tree_docker,
    is_docker_path,
    parse_docker_path,
)

# ---------------------------------------------------------------------------
# Integration fixture
# ---------------------------------------------------------------------------


_CONTAINER_NAME = "dirplot-integration-test"


_PROBE_NAME = "dirplot-exec-probe"


def _docker_available() -> bool:
    """Return True if docker CLI is in PATH, daemon responds, and exec works.

    Runs a detached smoke-test container and execs into it to verify that
    ``docker exec`` actually works end-to-end. Docker Desktop with the
    containerd image store can pass ``docker info`` yet still fail on exec;
    this catches that case.
    """
    if shutil.which("docker") is None:
        return False
    try:
        if subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode != 0:
            return False

        # Clean up any leftover probe container
        subprocess.run(["docker", "rm", "-f", _PROBE_NAME], capture_output=True)

        # Start a detached container
        r = subprocess.run(
            ["docker", "run", "-d", "--name", _PROBE_NAME, "python:3.12-slim", "sleep", "30"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return False

        # Verify exec works
        r2 = subprocess.run(
            ["docker", "exec", _PROBE_NAME, "echo", "ok"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return r2.returncode == 0 and r2.stdout.strip() == "ok"
    except Exception:
        return False
    finally:
        subprocess.run(["docker", "rm", "-f", _PROBE_NAME], capture_output=True)


@pytest.fixture(scope="session")
def docker_container():
    """Run a temporary container with known files for integration tests.

    Uses python:3.12-slim so file creation via python3 -c is guaranteed.
    Skips the whole session if Docker is unavailable or exec is broken.
    """
    if not _docker_available():
        pytest.skip("Docker not available or exec is broken (e.g. Docker Desktop containerd mode)")

    # Clean up any leftover container from a previous interrupted run
    subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True)

    result = subprocess.run(
        ["docker", "run", "-d", "--name", _CONTAINER_NAME, "python:3.12-slim", "sleep", "infinity"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Could not start container: {result.stderr.strip()}")

    # Create a known directory tree inside the container
    subprocess.run(
        [
            "docker",
            "exec",
            _CONTAINER_NAME,
            "python3",
            "-c",
            (
                "import os; "
                "os.makedirs('/testdata/src', exist_ok=True); "
                "open('/testdata/src/app.py', 'wb').write(b'x' * 100); "
                "open('/testdata/src/util.py', 'wb').write(b'x' * 200); "
                "open('/testdata/README.md', 'wb').write(b'y' * 50); "
            ),
        ],
        check=True,
    )

    yield _CONTAINER_NAME

    subprocess.run(["docker", "rm", "-f", _CONTAINER_NAME], capture_output=True)


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def test_is_docker_path_valid() -> None:
    assert is_docker_path("docker://my-container:/app")


def test_is_docker_path_no_colon() -> None:
    assert is_docker_path("docker://my-container/app")


@pytest.mark.parametrize("path", ["/local/path", "ssh://user@host/path", "s3://bucket"])
def test_is_docker_path_non_docker(path: str) -> None:
    assert not is_docker_path(path)


def test_parse_docker_path_with_colon() -> None:
    container, path = parse_docker_path("docker://my-container:/app/static")
    assert container == "my-container"
    assert path == "/app/static"


def test_parse_docker_path_without_colon() -> None:
    container, path = parse_docker_path("docker://my-container/app/static")
    assert container == "my-container"
    assert path == "/app/static"


def test_parse_docker_path_root() -> None:
    container, path = parse_docker_path("docker://my-container:/")
    assert container == "my-container"
    assert path == "/"


def test_parse_docker_path_no_path() -> None:
    container, path = parse_docker_path("docker://my-container:")
    assert container == "my-container"
    assert path == "/"


# ---------------------------------------------------------------------------
# _entries_to_tree
# ---------------------------------------------------------------------------


def test_entries_to_tree_flat() -> None:
    entries = [
        ("file.py", 1000, False),
        ("README.md", 500, False),
    ]
    node = _entries_to_tree("/project", entries)
    assert node.is_dir
    assert node.size == 1500
    assert {c.name for c in node.children} == {"file.py", "README.md"}


def test_entries_to_tree_extensions() -> None:
    entries = [
        ("script.py", 100, False),
        ("Makefile", 50, False),
    ]
    node = _entries_to_tree("/project", entries)
    py = next(c for c in node.children if c.name == "script.py")
    mk = next(c for c in node.children if c.name == "Makefile")
    assert py.extension == ".py"
    assert mk.extension == "(no ext)"


def test_entries_to_tree_nested() -> None:
    entries = [
        ("src", 0, True),
        ("src/app.py", 200, False),
        ("README.md", 50, False),
    ]
    node = _entries_to_tree("/project", entries)
    assert node.size == 250
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.size == 200
    assert src.children[0].name == "app.py"


def test_entries_to_tree_missing_intermediate_dirs() -> None:
    # find output may not always list intermediate directories explicitly
    entries = [
        ("a/b/file.txt", 100, False),
    ]
    node = _entries_to_tree("/root", entries)
    a = next(c for c in node.children if c.name == "a")
    assert a.is_dir
    b = next(c for c in a.children if c.name == "b")
    assert b.is_dir
    assert b.children[0].name == "file.txt"


# ---------------------------------------------------------------------------
# build_tree_docker (mocked subprocess)
# ---------------------------------------------------------------------------


def _mock_run(find_stdout: str = "", returncode: int = 0, inspect_rc: int = 0):
    """Return a side_effect function for subprocess.run that fakes docker calls."""

    def _side_effect(cmd, **kwargs):
        result = MagicMock()
        if "inspect" in cmd:
            result.returncode = inspect_rc
            result.stdout = ""
            result.stderr = "no such container" if inspect_rc != 0 else ""
        else:
            # docker exec ... find ...
            result.returncode = returncode
            result.stdout = find_stdout
            result.stderr = "find error" if returncode != 0 else ""
        return result

    return _side_effect


def test_build_tree_docker_flat() -> None:
    output = "file.py\t1000\tf\nREADME.md\t500\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_docker("my-container", "/app")
    assert node.is_dir
    assert node.size == 1500
    assert {c.name for c in node.children} == {"file.py", "README.md"}


def test_build_tree_docker_skips_dotfiles() -> None:
    output = ".hidden\t100\tf\nvisible.txt\t200\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_docker("my-container", "/app")
    names = {c.name for c in node.children}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_build_tree_docker_exclude() -> None:
    output = "keep.py\t100\tf\nskip.py\t200\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_docker("my-container", "/app", exclude=frozenset({"/app/skip.py"}))
    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_docker_nested() -> None:
    output = "src\t0\td\nsrc/app.py\t300\tf\ntop.txt\t100\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_docker("my-container", "/app")
    assert node.size == 400
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir


def test_build_tree_docker_find_failure() -> None:
    with (
        patch("subprocess.run", side_effect=_mock_run(returncode=1)),
        pytest.raises(OSError, match="find failed"),
    ):
        build_tree_docker("my-container", "/missing")


def test_build_tree_docker_container_not_found() -> None:
    with (
        patch("subprocess.run", side_effect=_mock_run(inspect_rc=1)),
        pytest.raises(FileNotFoundError),
    ):
        build_tree_docker("no-such-container", "/app")


def test_build_tree_docker_progress_reported() -> None:
    lines = "\n".join(f"file{i}.txt\t100\tf" for i in range(101))
    progress: list[int] = [0]
    with patch("subprocess.run", side_effect=_mock_run(lines + "\n")):
        build_tree_docker("my-container", "/app", _progress=progress)
    assert progress[0] == 101


def test_build_tree_docker_depth_passed_to_find() -> None:
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=_capture):
        build_tree_docker("my-container", "/app", depth=2)

    find_call = next(c for c in calls if "exec" in c)
    assert "-xdev" in find_call
    assert "-maxdepth" in find_call
    assert "2" in find_call


# ---------------------------------------------------------------------------
# Integration tests (require a running Docker daemon)
# ---------------------------------------------------------------------------


@pytest.mark.docker
def test_docker_integration_structure(docker_container: str) -> None:
    """Scanning the test container returns the expected directory structure."""
    node = build_tree_docker(docker_container, "/testdata")
    assert node.is_dir
    names = {c.name for c in node.children}
    assert "src" in names
    assert "README.md" in names


@pytest.mark.docker
def test_docker_integration_file_sizes(docker_container: str) -> None:
    """Files inside the container have the exact sizes we wrote."""
    node = build_tree_docker(docker_container, "/testdata")
    readme = next(c for c in node.children if c.name == "README.md")
    assert readme.size == 50
    src = next(c for c in node.children if c.name == "src")
    app = next(c for c in src.children if c.name == "app.py")
    util = next(c for c in src.children if c.name == "util.py")
    assert app.size == 100
    assert util.size == 200


@pytest.mark.docker
def test_docker_integration_extensions(docker_container: str) -> None:
    """File extensions are correctly detected inside a real container."""
    node = build_tree_docker(docker_container, "/testdata")
    readme = next(c for c in node.children if c.name == "README.md")
    assert readme.extension == ".md"
    src = next(c for c in node.children if c.name == "src")
    app = next(c for c in src.children if c.name == "app.py")
    assert app.extension == ".py"


@pytest.mark.docker
def test_docker_integration_total_size(docker_container: str) -> None:
    """Root node size equals sum of all file sizes (100 + 200 + 50 = 350)."""
    node = build_tree_docker(docker_container, "/testdata")
    assert node.size == 350


@pytest.mark.docker
def test_docker_integration_exclude(docker_container: str) -> None:
    """Excluded paths are omitted from the result."""
    node = build_tree_docker(
        docker_container, "/testdata", exclude=frozenset({"/testdata/README.md"})
    )
    names = {c.name for c in node.children}
    assert "README.md" not in names
    assert "src" in names


@pytest.mark.docker
def test_docker_integration_depth(docker_container: str) -> None:
    """Depth limit prevents recursion into subdirectories."""
    node = build_tree_docker(docker_container, "/testdata", depth=1)
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.children == []


@pytest.mark.docker
def test_docker_integration_missing_container() -> None:
    """A non-existent container name raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        build_tree_docker("dirplot-no-such-container-xyz", "/app")
