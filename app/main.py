"""Application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.api.router import api_router
from app.core.settings import get_settings

# Database imports
from app.database.database import Base, engine, seed_mock_chat_history, seed_permission_catalog

# Initialize the SQLite tables
Base.metadata.create_all(bind=engine)
seed_permission_catalog()
seed_mock_chat_history()

settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API gateway for the Kubernetes AIOps proof of concept.",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files to serve the UI
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", summary="Serve Dashboard UI", tags=["UI"])
def read_root():
    return FileResponse("app/static/index.html")

app.include_router(api_router)

