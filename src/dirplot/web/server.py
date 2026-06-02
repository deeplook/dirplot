"""FastAPI application factory for the dirplot web interface."""

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

_HERE = Path(__file__).parent
_TEMPLATES_DIR = _HERE / "templates"
_STATIC_DIR = _HERE / "static"


@dataclass
class ServeConfig:
    root: str
    root_path: Path | None  # None for remote / read-only sources
    colormap: str
    depth: int | None
    exclude: frozenset[str]
    breadcrumbs: bool
    allow_write: bool


def create_app(config: ServeConfig):  # type: ignore[no-untyped-def]
    import fastapi
    from fastapi import Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel

    app = fastapi.FastAPI(title="dirplot", docs_url=None, redoc_url=None)
    templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    def _scan_and_serialize(
        depth: int | None,
        log_scale: float,
        colormap: str,
        exclude: list[str],
        include: list[str],
    ) -> dict[str, object]:
        from dirplot.scanner import apply_breadcrumbs, apply_log_sizes, prune_to_subtrees
        from dirplot.sources import registry as source_registry
        from dirplot.tree_json import build_color_map, node_to_dict

        effective_exclude = frozenset(exclude) if exclude else config.exclude
        source = source_registry.find_source(config.root)
        root_node = source.scan(config.root, exclude=effective_exclude, depth=depth)
        if include:
            root_node = prune_to_subtrees(root_node, set(include))
        if log_scale > 1:
            apply_log_sizes(root_node, logscale=log_scale)
        if config.breadcrumbs:
            root_node = apply_breadcrumbs(root_node)
        color_map = build_color_map(root_node, colormap)
        return node_to_dict(root_node, color_map)

    @app.get("/")
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "root_name": config.root,
                "allow_write": config.allow_write,
            },
        )

    @app.get("/api/config")
    async def api_config() -> JSONResponse:
        import cmap as _cmap_lib

        colormaps = sorted(_cmap_lib.Catalog().short_keys())
        return JSONResponse(
            content={
                "root": config.root,
                "depth": config.depth,
                "colormap": config.colormap,
                "exclude": sorted(config.exclude),
                "allow_write": config.allow_write,
                "colormaps": colormaps,
            }
        )

    @app.get("/api/tree")
    async def api_tree(
        depth: int | None = None,
        log_scale: float = 0.0,
        colormap: str | None = None,
        exclude: list[str] = fastapi.Query(default=[]),
        include: list[str] = fastapi.Query(default=[]),
    ) -> JSONResponse:
        effective_depth = depth if depth is not None else config.depth
        effective_colormap = colormap if colormap else config.colormap
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            _scan_and_serialize,
            effective_depth,
            log_scale,
            effective_colormap,
            exclude,
            include,
        )
        return JSONResponse(content=data)

    class OperationRequest(BaseModel):
        op: str  # "delete" or "move"
        path: str
        dest: str | None = None
        overwrite: bool = False

    class OperationResponse(BaseModel):
        ok: bool
        message: str

    @app.post("/api/operation")
    async def api_operation(body: OperationRequest) -> OperationResponse:
        if not config.allow_write:
            return OperationResponse(
                ok=False, message="Write operations not allowed for this source."
            )
        if config.root_path is None:
            return OperationResponse(ok=False, message="No local root path configured.")

        target = Path(body.path).resolve()
        if not target.is_relative_to(config.root_path):
            return OperationResponse(ok=False, message="Path is outside the served root.")

        if body.op == "delete":
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            return OperationResponse(ok=True, message=f"Deleted {target.name}.")

        if body.op == "move":
            if not body.dest:
                return OperationResponse(ok=False, message="Destination path required for move.")
            dest = Path(body.dest).resolve()
            if not dest.is_relative_to(config.root_path):
                return OperationResponse(
                    ok=False, message="Destination is outside the served root."
                )
            if dest.exists() and not body.overwrite:
                return OperationResponse(
                    ok=False, message="Destination exists; set overwrite=true to replace."
                )
            shutil.move(str(target), str(dest))
            return OperationResponse(ok=True, message=f"Moved to {dest.name}.")

        return OperationResponse(ok=False, message=f"Unknown operation: {body.op!r}")

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        if config.root_path is None:
            await ws.close()
            return

        import threading
        import time

        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer

        queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_event_loop()
        _pending: list[float] = []
        _DEBOUNCE = 0.5

        class _Handler(FileSystemEventHandler):
            def on_any_event(self, event: object) -> None:
                _pending.append(time.monotonic())

        observer = Observer()
        observer.schedule(_Handler(), str(config.root_path), recursive=True)
        observer.start()

        def _debouncer() -> None:
            while observer.is_alive():
                if _pending and (time.monotonic() - _pending[-1]) >= _DEBOUNCE:
                    _pending.clear()
                    payload = json.dumps({"event": "change"})
                    loop.call_soon_threadsafe(queue.put_nowait, payload)
                time.sleep(0.1)

        threading.Thread(target=_debouncer, daemon=True).start()

        try:
            while True:
                msg = await asyncio.wait_for(queue.get(), timeout=30)
                await ws.send_text(msg)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            observer.stop()
            observer.join()

    return app
