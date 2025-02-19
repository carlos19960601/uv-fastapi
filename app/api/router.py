from fastapi import APIRouter

from app.api.routers import health_check, login, private
from app.core.config import settings

api_router = APIRouter()

# Health Check routers
api_router.include_router(health_check.router, prefix="/health", tags=["Health Check"])

# Whisper Tasks routers
api_router.include_router(login.router, prefix="/whisper", tags=["Whisper Tasks"])

api_router.include_router(login.router)

if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
