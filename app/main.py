"""Application entrypoint."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.settings import get_settings


settings = get_settings()

app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="API gateway for the Kubernetes AIOps proof of concept.",
)
app.include_router(api_router)

