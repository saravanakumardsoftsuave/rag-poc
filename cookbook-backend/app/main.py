import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.core.mcp_adapter import build_mcp_registry
from app.config import settings
from app.database import init_db
from app.routes import router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

MCP_CONFIG_PATH = "config/mcp_servers.json"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
    tool_registry, mcp_stack = await build_mcp_registry(MCP_CONFIG_PATH)
    app.state.tool_registry = tool_registry
    try:
        yield
    finally:
        await mcp_stack.aclose()


app = FastAPI(title="Cookbook RAG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
