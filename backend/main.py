import logging
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.me import router as me_router
from routers.sessions import router as sessions_router
from routers.viewer_ws import router as viewer_ws_router
from routers.ws import router as ws_router

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Pédiluve")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(viewer_ws_router)
app.include_router(me_router)
app.include_router(sessions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
