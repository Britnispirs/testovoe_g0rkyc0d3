import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.database import init_db
from backend.app.seed import seed_database
from backend.app.api.auth import router as auth_router
from backend.app.api.events import router as events_router
from backend.app.api.assistant import router as assistant_router
from backend.app.api.voice import router as voice_router

app = FastAPI(
    title="Голосовой Ассистент Задач и Встреч",
    description="Минималистичный голосовой ассистент с NLU, мультидиалогом и умным поиском",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(events_router)
app.include_router(assistant_router)
app.include_router(voice_router)


@app.on_event("startup")
def on_startup():
    init_db()
    count = seed_database(force=False)
    print(f"[Startup] Database initialized with {count} events.")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "voice-assistant"}


FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend"))

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_frontend_root():
        index_file = os.path.join(FRONTEND_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"message": "Frontend index.html not found yet"}
