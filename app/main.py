from pydoc import doc

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings

# API Tags
tags_metadata = [
    {
        "name": "Health Check",
        "description": "**(服务器健康检查 / Server Health Check)**",
    },
    {
        "name": "Whisper Tasks",
        "description": "**(Whisper 任务 / Whisper Tasks)**",
    },
]

app = FastAPI(
    title=settings.fastapi.title,
    description=settings.fastapi.description,
    version=settings.fastapi.version,
    openapi_tags=tags_metadata,
    docs_url=settings.fastapi.docs_url,
    debug=settings.fastapi.debug,
)

app.include_router(api_router, prefix="/api")
