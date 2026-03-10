"""Tests for Kubernetes pod directory scanning."""

from __future__ import annotations

import shutil
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from dirplot.k8s import (
    _entries_to_tree,
    build_tree_pod,
    is_pod_path,
    parse_pod_path,
)

# ---------------------------------------------------------------------------
# Integration fixture
# ---------------------------------------------------------------------------

_POD_NAME = "dirplot-k8s-integration-test"


def _kubectl_available() -> bool:
    """Return True if kubectl is in PATH and can reach a cluster."""
    if shutil.which("kubectl") is None:
        return False
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.fixture(scope="session")
def k8s_pod():
    """Run a temporary pod with known files for integration tests.

    Uses nginx (alpine-based) which is available in minikube's local registry.
    Skips the whole session if kubectl/cluster is unavailable.
    """
    if not _kubectl_available():
        pytest.skip("kubectl not available or no cluster reachable")

    # Clean up any leftover pod from a previous interrupted run
    subprocess.run(
        ["kubectl", "delete", "pod", _POD_NAME, "--ignore-not-found"], capture_output=True
    )

    result = subprocess.run(
        [
            "kubectl",
            "run",
            _POD_NAME,
            "--image=python:3.12-slim",
            "--restart=Never",
            "--",
            "sleep",
            "infinity",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.skip(f"Could not create pod: {result.stderr.strip()}")

    # Wait until Running
    wait = subprocess.run(
        ["kubectl", "wait", "--for=condition=Ready", f"pod/{_POD_NAME}", "--timeout=90s"],
        capture_output=True,
        text=True,
    )
    if wait.returncode != 0:
        subprocess.run(
            ["kubectl", "delete", "pod", _POD_NAME, "--ignore-not-found"], capture_output=True
        )
        pytest.skip(f"Pod did not become ready: {wait.stderr.strip()}")

    # Create a known directory tree inside the pod
    subprocess.run(
        [
            "kubectl",
            "exec",
            _POD_NAME,
            "--",
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

    yield _POD_NAME

    subprocess.run(
        ["kubectl", "delete", "pod", _POD_NAME, "--ignore-not-found", "--grace-period=0"],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# URI helpers – is_pod_path
# ---------------------------------------------------------------------------


def test_is_pod_path_valid() -> None:
    assert is_pod_path("pod://mypod:/app")


def test_is_pod_path_without_colon() -> None:
    assert is_pod_path("pod://mypod/app")


def test_is_pod_path_with_namespace() -> None:
    assert is_pod_path("pod://mypod@default/app")


@pytest.mark.parametrize("path", ["/local/path", "docker://container:/app", "s3://bucket"])
def test_is_pod_path_non_pod(path: str) -> None:
    assert not is_pod_path(path)


# ---------------------------------------------------------------------------
# URI helpers – parse_pod_path
# ---------------------------------------------------------------------------


def test_parse_pod_path_slash_separator() -> None:
    pod, ns, path = parse_pod_path("pod://mypod/app/static")
    assert pod == "mypod"
    assert ns is None
    assert path == "/app/static"


def test_parse_pod_path_colon_separator() -> None:
    pod, ns, path = parse_pod_path("pod://mypod:/app/static")
    assert pod == "mypod"
    assert ns is None
    assert path == "/app/static"


def test_parse_pod_path_namespace_slash() -> None:
    pod, ns, path = parse_pod_path("pod://mypod@default/app/static")
    assert pod == "mypod"
    assert ns == "default"
    assert path == "/app/static"


def test_parse_pod_path_namespace_colon() -> None:
    pod, ns, path = parse_pod_path("pod://mypod@default:/app/static")
    assert pod == "mypod"
    assert ns == "default"
    assert path == "/app/static"


def test_parse_pod_path_root_only() -> None:
    pod, ns, path = parse_pod_path("pod://mypod:")
    assert pod == "mypod"
    assert ns is None
    assert path == "/"


def test_parse_pod_path_no_path() -> None:
    pod, ns, path = parse_pod_path("pod://mypod/")
    assert pod == "mypod"
    assert ns is None
    assert path == "/"


def test_parse_pod_path_namespace_no_path() -> None:
    pod, ns, path = parse_pod_path("pod://mypod@staging/")
    assert pod == "mypod"
    assert ns == "staging"
    assert path == "/"


# ---------------------------------------------------------------------------
# _entries_to_tree
# ---------------------------------------------------------------------------


def test_entries_to_tree_flat() -> None:
    entries = [("file.py", 1000, False), ("README.md", 500, False)]
    node = _entries_to_tree("/project", entries)
    assert node.is_dir
    assert node.size == 1500
    assert {c.name for c in node.children} == {"file.py", "README.md"}


def test_entries_to_tree_extensions() -> None:
    entries = [("script.py", 100, False), ("Makefile", 50, False)]
    node = _entries_to_tree("/project", entries)
    py = next(c for c in node.children if c.name == "script.py")
    mk = next(c for c in node.children if c.name == "Makefile")
    assert py.extension == ".py"
    assert mk.extension == "(no ext)"


def test_entries_to_tree_nested() -> None:
    entries = [("src", 0, True), ("src/app.py", 200, False), ("README.md", 50, False)]
    node = _entries_to_tree("/project", entries)
    assert node.size == 250
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.size == 200
    assert src.children[0].name == "app.py"


def test_entries_to_tree_missing_intermediate_dirs() -> None:
    entries = [("a/b/file.txt", 100, False)]
    node = _entries_to_tree("/root", entries)
    a = next(c for c in node.children if c.name == "a")
    assert a.is_dir
    b = next(c for c in a.children if c.name == "b")
    assert b.is_dir
    assert b.children[0].name == "file.txt"


# ---------------------------------------------------------------------------
# build_tree_pod (mocked subprocess)
# ---------------------------------------------------------------------------


def _mock_run(find_stdout: str = "", returncode: int = 0, get_pod_rc: int = 0):
    """Return a side_effect function for subprocess.run that fakes kubectl calls."""

    def _side_effect(cmd, **kwargs):
        result = MagicMock()
        if "get" in cmd and "pod" in cmd:
            result.returncode = get_pod_rc
            result.stdout = ""
            result.stderr = "not found" if get_pod_rc != 0 else ""
        else:
            # kubectl exec ... find ...
            result.returncode = returncode
            result.stdout = find_stdout
            result.stderr = "find error" if returncode != 0 else ""
        return result

    return _side_effect


def test_build_tree_pod_flat() -> None:
    output = "file.py\t1000\tf\nREADME.md\t500\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_pod("mypod", "/app")
    assert node.is_dir
    assert node.size == 1500
    assert {c.name for c in node.children} == {"file.py", "README.md"}


def test_build_tree_pod_skips_dotfiles() -> None:
    output = ".hidden\t100\tf\nvisible.txt\t200\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_pod("mypod", "/app")
    names = {c.name for c in node.children}
    assert "visible.txt" in names
    assert ".hidden" not in names


def test_build_tree_pod_exclude() -> None:
    output = "keep.py\t100\tf\nskip.py\t200\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_pod("mypod", "/app", exclude=frozenset({"/app/skip.py"}))
    names = {c.name for c in node.children}
    assert "keep.py" in names
    assert "skip.py" not in names


def test_build_tree_pod_nested() -> None:
    output = "src\t0\td\nsrc/app.py\t300\tf\ntop.txt\t100\tf\n"
    with patch("subprocess.run", side_effect=_mock_run(output)):
        node = build_tree_pod("mypod", "/app")
    assert node.size == 400
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir


def test_build_tree_pod_find_failure() -> None:
    with (
        patch("subprocess.run", side_effect=_mock_run(returncode=1)),
        pytest.raises(OSError, match="find failed"),
    ):
        build_tree_pod("mypod", "/missing")


def test_build_tree_pod_not_found() -> None:
    with (
        patch("subprocess.run", side_effect=_mock_run(get_pod_rc=1)),
        pytest.raises(FileNotFoundError),
    ):
        build_tree_pod("no-such-pod", "/app")


def test_build_tree_pod_progress_reported() -> None:
    lines = "\n".join(f"file{i}.txt\t100\tf" for i in range(101))
    progress: list[int] = [0]
    with patch("subprocess.run", side_effect=_mock_run(lines + "\n")):
        build_tree_pod("mypod", "/app", _progress=progress)
    assert progress[0] == 101


def test_build_tree_pod_depth_passed_to_kubectl() -> None:
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=_capture):
        build_tree_pod("mypod", "/app", depth=2)

    exec_call = next(c for c in calls if "exec" in c)
    assert "-maxdepth" in exec_call
    assert "2" in exec_call


def test_build_tree_pod_namespace_passed_to_kubectl() -> None:
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=_capture):
        build_tree_pod("mypod", "/app", namespace="staging")

    for call in calls:
        assert "-n" in call
        assert "staging" in call


def test_build_tree_pod_container_passed_to_kubectl() -> None:
    calls: list[list[str]] = []

    def _capture(cmd, **kwargs):
        calls.append(list(cmd))
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        return r

    with patch("subprocess.run", side_effect=_capture):
        build_tree_pod("mypod", "/app", container="sidecar")

    exec_call = next(c for c in calls if "exec" in c)
    assert "-c" in exec_call
    assert "sidecar" in exec_call


# ---------------------------------------------------------------------------
# Integration tests (require kubectl + a running cluster)
# ---------------------------------------------------------------------------


@pytest.mark.k8s
def test_k8s_integration_structure(k8s_pod: str) -> None:
    """Scanning the test pod returns the expected directory structure."""
    node = build_tree_pod(k8s_pod, "/testdata")
    assert node.is_dir
    names = {c.name for c in node.children}
    assert "src" in names
    assert "README.md" in names


@pytest.mark.k8s
def test_k8s_integration_file_sizes(k8s_pod: str) -> None:
    """Files inside the pod have the exact sizes we wrote."""
    node = build_tree_pod(k8s_pod, "/testdata")
    readme = next(c for c in node.children if c.name == "README.md")
    assert readme.size == 50
    src = next(c for c in node.children if c.name == "src")
    app = next(c for c in src.children if c.name == "app.py")
    util = next(c for c in src.children if c.name == "util.py")
    assert app.size == 100
    assert util.size == 200


@pytest.mark.k8s
def test_k8s_integration_extensions(k8s_pod: str) -> None:
    """File extensions are correctly detected inside a real pod."""
    node = build_tree_pod(k8s_pod, "/testdata")
    readme = next(c for c in node.children if c.name == "README.md")
    assert readme.extension == ".md"
    src = next(c for c in node.children if c.name == "src")
    app = next(c for c in src.children if c.name == "app.py")
    assert app.extension == ".py"


@pytest.mark.k8s
def test_k8s_integration_total_size(k8s_pod: str) -> None:
    """Root node size equals sum of all file sizes (100 + 200 + 50 = 350)."""
    node = build_tree_pod(k8s_pod, "/testdata")
    assert node.size == 350


@pytest.mark.k8s
def test_k8s_integration_exclude(k8s_pod: str) -> None:
    """Excluded paths are omitted from the result."""
    node = build_tree_pod(k8s_pod, "/testdata", exclude=frozenset({"/testdata/README.md"}))
    names = {c.name for c in node.children}
    assert "README.md" not in names
    assert "src" in names


@pytest.mark.k8s
def test_k8s_integration_depth(k8s_pod: str) -> None:
    """Depth limit prevents recursion into subdirectories."""
    node = build_tree_pod(k8s_pod, "/testdata", depth=1)
    src = next(c for c in node.children if c.name == "src")
    assert src.is_dir
    assert src.children == []


@pytest.mark.k8s
def test_k8s_integration_namespace(k8s_pod: str) -> None:
    """Explicit namespace=default succeeds for a pod in the default namespace."""
    node = build_tree_pod(k8s_pod, "/testdata", namespace="default")
    assert node.is_dir
    assert node.size == 350


@pytest.mark.k8s
def test_k8s_integration_missing_pod() -> None:
    """A non-existent pod name raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        build_tree_pod("dirplot-no-such-pod-xyz", "/app")
