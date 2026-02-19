"""Unified entry point — mounts MCP (/mcp) and REST API (/api)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

import db
from api_server import app as api_app
from mcp_server import mount_mcp


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.startup()
    yield
    db.shutdown()


app = FastAPI(lifespan=lifespan)
app.mount("/api", api_app)
mount_mcp(app)


@app.get("/healthcheck")
async def healthcheck():
    db_status = db.check_health()
    return {
        "msg": "pg-vector is alive",
        "db": db_status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
