from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import chat
from app.core.config import settings
from app.core.logger import logger


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

app.include_router(chat.router, tags=["chat"])


@app.get("/", include_in_schema=False)
async def root():
    return {
        "name": settings.project_name,
        "version": settings.version,
        "docs": "/docs"
    }
