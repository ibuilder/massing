"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import analysis, authoring, bim, drawings, exports, properties


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


app = FastAPI(title="AEC BIM Platform API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # web viewer dev origin
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(bim.router, tags=["bim"])
app.include_router(properties.router, tags=["properties"])
app.include_router(exports.router, tags=["exports"])
app.include_router(analysis.router, tags=["analysis"])
app.include_router(drawings.router, tags=["drawings"])
app.include_router(authoring.router, tags=["authoring"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
