from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import settings
from app.database.database_manager import DatabaseManager
from app.model_pool.async_model_pool import AsyncModelPool
from app.services.whisper_service import WhisperService
from app.utils.logging_utils import configure_logging

# 配置日志记录器 | Configure the logger
logger = configure_logging(name=__name__)

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期上下文管理器 | FastAPI Lifecycle context manager
    :param application: FastAPI 应用实例 | FastAPI application instance
    :return: None
    """
    # 选择数据库管理器并初始化数据库 | Choose the database manager and initialize the database
    if settings.database.db_type == "sqlite":
        database_url = settings.database.sqlite_url
    elif settings.database.db_type == "mysql":
        database_url = settings.database.mysql_url
    else:
        raise RuntimeError(
            "Can not recognize the database type, please check the database type in the settings."
        )

    auto_create_tables = settings.database.auto_create_tables
    db_manager = DatabaseManager(
        database_type=settings.database.db_type,
        database_url=database_url,
        auto_create_tables=auto_create_tables,
    )
    db_manager.initialize()

    # 将数据库管理器存储在应用的 state 中 | Store db_manager in the app state
    app.state.db_manager = db_manager

    # 实例化异步模型池 | Instantiate the asynchronous model pool
    model_pool = AsyncModelPool(
        # 模型池设置 | Model Pool Settings
        engine=settings.async_model_pool.engine,
        min_size=settings.async_model_pool.min_size,
        max_size=settings.async_model_pool.max_size,
        max_instances_per_gpu=settings.async_model_pool.max_instances_per_gpu,
        init_with_max_pool_size=settings.async_model_pool.init_with_max_pool_size,
        # openai_whisper 引擎设置 | openai_whisper Engine Settings
        openai_whisper_model_name=settings.openai_whisper.openai_whisper_model_name,
        openai_whisper_device=settings.openai_whisper.openai_whisper_device,
        openai_whisper_download_root=settings.openai_whisper.openai_whisper_download_root,
        openai_whisper_in_memory=settings.openai_whisper.openai_whisper_in_memory,
        # faster_whisper 引擎设置 | faster_whisper Engine Settings
        faster_whisper_model_size_or_path=settings.faster_whisper.faster_whisper_model_size_or_path,
        faster_whisper_device=settings.faster_whisper.faster_whisper_device,
        faster_whisper_device_index=settings.faster_whisper.faster_whisper_device_index,
        faster_whisper_compute_type=settings.faster_whisper.faster_whisper_compute_type,
        faster_whisper_cpu_threads=settings.faster_whisper.faster_whisper_cpu_threads,
        faster_whisper_num_workers=settings.faster_whisper.faster_whisper_num_workers,
        faster_whisper_download_root=settings.faster_whisper.faster_whisper_download_root,
    )
    # 初始化模型池，加载模型，这可能需要一些时间 | Initialize the model pool, load the model, this may take some time
    await model_pool.initialize_pool()

    # 实例化 WhisperService | Instantiate WhisperService
    whisper_service = WhisperService(
        model_pool=model_pool,
        db_manager=db_manager,
        max_concurrent_tasks=settings.whisper_service.MAX_CONCURRENT_TASKS,
        task_status_check_interval=settings.whisper_service.TASK_STATUS_CHECK_INTERVAL,
    )

    # 启动任务处理器 | Start the task processor
    whisper_service.start_task_processor()

    # 将数据库管理器存储在应用的 state 中 | Store db_manager in the app state
    app.state.db_manager = db_manager

    # 将 whisper_service 存储在应用的 state 中 | Store whisper_service in the app state
    app.state.whisper_service = whisper_service

    # 等待生命周期完成 | Wait for the lifecycle to complete
    yield

    # 停止任务处理器 | Stop the task processor
    whisper_service.stop_task_processor()


# 创建 FastAPI 应用实例
app = FastAPI(
    title=settings.fastapi.title,
    description=settings.fastapi.description,
    version=settings.fastapi.version,
    openapi_tags=tags_metadata,
    docs_url=settings.fastapi.docs_url,
    debug=settings.fastapi.debug,
    lifespan=lifespan,
)

app.include_router(api_router, prefix="/api")
