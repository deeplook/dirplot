# Python API

> **Note:** The programmatic Python API is still evolving and may change between releases without notice. Pin a specific version if you depend on it. The CLI interface is stable.

The public API centres on `build_tree`, `create_treemap`, and `create_treemap_svg`:

```python
from pathlib import Path
from dirplot import build_tree, apply_log_sizes, create_treemap, create_treemap_svg

root = build_tree(Path("/path/to/project"))

# PNG — returns a BytesIO containing PNG bytes
buf = create_treemap(root, width_px=1920, height_px=1080, colormap="tab20", cushion=True)
Path("treemap.png").write_bytes(buf.read())

# SVG — returns a BytesIO containing UTF-8 SVG bytes
# Includes CSS hover highlight, a JS floating tooltip, and cushion gradient shading.
buf = create_treemap_svg(root, width_px=1920, height_px=1080, cushion=True)
Path("treemap.svg").write_bytes(buf.read())

# Log scale — compress large size differences before rendering.
# Original byte counts are preserved in node.original_size for display.
apply_log_sizes(root)
buf = create_treemap(root, width_px=1920, height_px=1080)
```

To open a PNG in the system image viewer or display it inline in the terminal:

```python
from dirplot.display import display_window, display_inline

buf.seek(0)
display_window(buf)   # system viewer (works everywhere)

buf.seek(0)
display_inline(buf)   # inline in terminal (iTerm2 / Kitty / WezTerm)
```

In a Jupyter notebook, PNG output renders automatically via PIL:

```python
from PIL import Image
buf = create_treemap(root, width_px=1280, height_px=720)
Image.open(buf)  # Jupyter renders PIL images automatically via _repr_png_()
```

## Metrics

`tree_metrics` and `tree_metrics_dict` compute statistics from a scanned `Node` tree — the same data shown by `dirplot metrics`:

```python
from pathlib import Path
from dirplot import build_tree
from dirplot.scanner import tree_metrics, tree_metrics_dict

root = build_tree(Path("/path/to/project"))

# Human-readable string (same as CLI output)
print(tree_metrics(root, t_scan=0.0))

# Sort extensions by total bytes instead of file count
print(tree_metrics(root, t_scan=0.0, sort_by="size"))

# Limit to top 5 entries per list
print(tree_metrics(root, t_scan=0.0, top_n=5))

# Structured dict — suitable for JSON serialisation or downstream processing
import json
data = tree_metrics_dict(root, t_scan=0.0)
print(json.dumps(data, indent=2))
```

`tree_metrics_dict` returns:

```python
{
    "files": int,            # total file count
    "dirs": int,             # total directory count
    "empty_dirs": int,       # directories with no children
    "total_size_bytes": int,
    "depth": int,            # maximum tree depth
    "scan_time_s": float,
    "top_extensions": [
        {"ext": str, "count": int, "size_bytes": int},
        …
    ],
    "largest_files": [
        {"path": str, "size_bytes": int, "pct": float},  # pct = % of total size
        …
    ],
    "largest_dirs": [
        {"path": str, "size_bytes": int, "pct": float},
        …
    ],
}
```

## Remote backends

Each remote backend exposes a `build_tree_*` function that returns the same `Node` type accepted by `create_treemap`:

```python
# GitHub
from dirplot.github import build_tree_github
root, branch = build_tree_github("pallets", "flask", token="ghp_…", depth=4)

# SSH
from dirplot.ssh import connect, build_tree_ssh
client = connect("prod.example.com", "alice", ssh_key="~/.ssh/prod_key")
sftp = client.open_sftp()
root = build_tree_ssh(sftp, "/var/www", depth=5)
sftp.close(); client.close()

# S3
from dirplot.s3 import make_s3_client, build_tree_s3
s3 = make_s3_client(profile="prod")          # authenticated
s3 = make_s3_client(no_sign=True)            # public bucket
root = build_tree_s3(s3, "my-bucket", "path/to/prefix/", depth=5)

# Docker
from dirplot.docker import build_tree_docker
root = build_tree_docker("my-container", "/app", depth=5)

# Kubernetes
from dirplot.k8s import build_tree_pod
root = build_tree_pod("my-pod", "/app", namespace="staging", container="main", depth=5)
```
