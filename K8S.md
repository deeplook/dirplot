# K8s Pod Debug Notes

## Issue: `dirplot map pod://kube-apiserver-minikube -N kube-system --depth 2`

### Root cause

`kube-apiserver-minikube` is a **fully distroless container** — only the
`kube-apiserver` binary exists. There is no shell (`sh`), no `find`, no `ls`.

```
$ kubectl exec kube-apiserver-minikube -n kube-system -- find /
OCI runtime exec failed: exec: "find": executable file not found in $PATH
command terminated with exit code 126
```

### Current error (unhelpful)

```
Error: find failed in pod 'kube-apiserver-minikube' at '/': command terminated with exit code 126
```

### What to fix next session

In `src/dirplot/k8s.py` → `build_tree_pod()`, improve the error handling block
after `_run_find()` returns a non-zero result:

- Detect exit code **126** (or stderr containing `"executable file not found"`
  / `"not found in $PATH"`) and raise a clearer `OSError` explaining the
  container is likely distroless and dirplot requires a POSIX `find` inside the
  container.

**Suggested message:**
```
No shell or 'find' utility in pod 'kube-apiserver-minikube' — the container is
likely distroless (scratch/distroless image with no OS tools).
dirplot requires a POSIX 'find' binary inside the container.
```

This is a pure error-message improvement; no logic change needed.

### Also note: `_run_find` fallback condition

The BusyBox fallback triggers only when `"unrecognized" in stderr`. Exit code
126 from a distroless container bypasses the fallback (correctly — sh isn't
available either), but the condition could be documented more clearly.
