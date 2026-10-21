"""Local-only HTTP transport for the same engine used by the browser worker."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles


def create_app(
    bundle: dict[str, Any] | None = None,
    *,
    static_directory: Path | None = None,
    serve_frontend: bool = True,
) -> FastAPI:
    """An injected immutable bundle supports parity tests without changing engine inputs."""
    app = FastAPI(title="MacroLab local analysis", docs_url=None, redoc_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    def execute(operation: str, config: dict[str, Any]) -> Any:
        from macrolab.analysis.engine import compatibility, run_analysis

        try:
            if operation == "compatibility":
                return compatibility(config, bundle=bundle)
            return run_analysis(config, bundle=bundle)
        except FileNotFoundError as exc:
            raise HTTPException(
                404,
                detail={
                    "code": "snapshot_unavailable",
                    "message": "The requested local data snapshot is unavailable.",
                },
            ) from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                422,
                detail={
                    "code": "invalid_analysis",
                    "message": str(exc),
                },
            ) from exc

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "runtime": "local Python", "network_binding": "127.0.0.1"}

    @app.get("/models")
    def models() -> dict[str, Any]:
        from macrolab.models.registry import catalogue

        return {"models": catalogue(), "runtime": "local Python"}

    @app.get("/capabilities")
    def capabilities() -> dict[str, Any]:
        return {
            "local_only": True,
            "publication_approved": False,
            "operations": [
                "run",
                "compatibility",
                "export/python",
                "config/encode",
                "config/decode",
            ],
            "data": "Prepared static country bundles; observations load only when selected.",
        }

    @app.post("/config/encode")
    def encode(config: Annotated[dict[str, Any], Body()]) -> dict[str, str]:
        from macrolab.analysis.config import encode_config

        try:
            return {"token": encode_config(config)}
        except (ValueError, KeyError) as exc:
            raise HTTPException(
                422, detail={"code": "invalid_analysis", "message": str(exc)}
            ) from exc

    @app.post("/config/decode")
    def decode(body: Annotated[dict[str, Any], Body()]) -> dict[str, Any]:
        from macrolab.analysis.config import decode_config

        try:
            if set(body) != {"token"}:
                raise ValueError("Supply one configuration token")
            return decode_config(body["token"])
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, detail={"code": "invalid_token", "message": str(exc)}) from exc

    @app.post("/run")
    def run(config: Annotated[dict[str, Any], Body()]) -> Any:
        return execute("run", config)

    @app.post("/compatibility")
    def compatible(config: Annotated[dict[str, Any], Body()]) -> Any:
        return execute("compatibility", config)

    @app.post("/export/python")
    def export_python(config: Annotated[dict[str, Any], Body()]) -> Response:
        from macrolab.analysis.config import normalise_config, required_concepts
        from macrolab.analysis.data import snapshot_bundle
        from macrolab.export.script import standalone

        try:
            config = normalise_config(config)
            selected = bundle or snapshot_bundle(
                config["snapshot_id"],
                config["countries"],
                required_concepts(config),
            )
            script = standalone(config, selected)
        except FileNotFoundError as exc:
            raise HTTPException(404, detail="Local snapshot unavailable") from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        return Response(
            script,
            media_type="text/x-python",
            headers={"Content-Disposition": 'attachment; filename="macrolab_analysis.py"'},
        )

    # Embedders can add their own mounts without a root static route shadowing them.
    if not serve_frontend:
        return app
    # API routes take precedence; only the compiled frontend directory is exposed.
    static = static_directory or Path(__file__).resolve().parents[3] / "web/dist"
    if (static / "index.html").is_file():
        app.mount("/", StaticFiles(directory=static, html=True), name="local-review")
    else:

        @app.get("/")
        def build_required() -> Response:
            return Response(
                "MacroLab local review build is missing. "
                "Run make web-build, then restart make serve.",
                status_code=503,
                media_type="text/plain",
            )

    return app


app = create_app()
