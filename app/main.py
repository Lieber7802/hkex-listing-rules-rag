from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from app.api import chat, chat_v2
from app.api.chat_v2_stream import router as stream_router
from app.core.config import settings
from app.core.logger import logger

FRONTEND_DIR = Path("frontend/dist")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.project_name} v{settings.version}")
    yield
    logger.info("Shutting down application")


app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description="Agentic RAG system for HKEX Listing Rules compliance Q&A",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers (must be before static file mount)
app.include_router(chat.router, tags=["chat"])
app.include_router(chat_v2.router, prefix="/v2", tags=["chat-v2"])
app.include_router(stream_router, prefix="/v2", tags=["streaming"])


# Frontend static files (served from Vite build output)
if FRONTEND_DIR.exists():
    # Serve static assets (JS, CSS, images)
    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        """Serve the React SPA."""
        return FileResponse(str(FRONTEND_DIR / "index.html"))
else:
    # Fallback when frontend is not built
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "name": settings.project_name,
            "version": settings.version,
            "docs": "/docs",
            "note": "Frontend not built. Run 'cd frontend && npm run build' to enable the web UI.",
        }
