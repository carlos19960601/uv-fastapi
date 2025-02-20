from fastapi import APIRouter

from app.api.routers import health_check, login, whisper_tasks

api_router = APIRouter()

# Health Check routers
api_router.include_router(health_check.router, prefix="/health", tags=["Health Check"])

# Whisper Tasks routers
api_router.include_router(
    whisper_tasks.router, prefix="/whisper", tags=["Whisper Tasks"]
)
