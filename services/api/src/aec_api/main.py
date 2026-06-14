"""FastAPI app entry (guide §7). Run: uvicorn aec_api.main:app --reload"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import bim, properties


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
)

app.include_router(bim.router, tags=["bim"])
app.include_router(properties.router, tags=["properties"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
