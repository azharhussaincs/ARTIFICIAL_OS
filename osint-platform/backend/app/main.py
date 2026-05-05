"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.dorks import router as dorks_router
from app.api.export import router as export_router
from app.api.history import router as history_router
from app.api.image_proxy import router as image_proxy_router
from app.api.search import router as search_router
from app.config import get_settings
from app.database import init_db
from app.osint.elastic_search import ElasticIntel, es_health


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_db()
    yield
    await ElasticIntel.instance().close()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title=s.app_name,
        version="1.0.0",
        description=(
            "Ethical OSINT platform — discovers publicly available information "
            "using Google dorks, polite scraping, and username correlation. "
            "Strictly public sources; respects robots.txt; no auth bypass."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(search_router, prefix="/api")
    app.include_router(dorks_router, prefix="/api")
    app.include_router(history_router, prefix="/api")
    app.include_router(export_router, prefix="/api")
    app.include_router(image_proxy_router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return JSONResponse({
            "status": "ok",
            "service": s.app_name,
            "env": s.app_env,
            "elasticsearch": await es_health(),
        })

    @app.get("/api/elastic/health")
    async def elastic_health():
        return JSONResponse(await es_health())

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir)), name="assets")

        @app.get("/")
        async def index():
            return FileResponse(str(static_dir / "index.html"))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    s = get_settings()
    uvicorn.run("app.main:app", host=s.host, port=s.port, reload=s.debug)
