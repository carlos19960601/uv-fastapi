from typing import Literal

from pydantic import BaseModel, PostgresDsn
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class FastAPISettings(BaseModel):
    # 项目名称 | Project name
    title: str = "uv-fastapi"
    # 项目描述 | Project description
    description: str = "a uv fastapi project test"
    # 项目版本 | Project version
    version: str = "0.1.0"
    # 文档地址 | Docs URL
    docs_url: str = "/docs"
    # 是否开启 debug 模式 | Whether to enable debug mode
    debug: bool = False


class WhisperServiceSettings(BaseModel):
    # Whisper 服务的最大并发任务数，设置为 1 时为单任务模式 | The maximum number of concurrent tasks for the Whisper service, set to 1 for single task mode
    # 如果你有多个 GPU，可以设置大于 1，在单一 GPU 上运行多个任务无法缩短任务时间，但可以提高任务并发度 | If you have multiple GPUs, you can set it to more than 1. Running multiple tasks on a single GPU cannot shorten the task time, but can increase the task concurrency
    MAX_CONCURRENT_TASKS: int = 1
    # 检查任务状态的时间间隔（秒），如果设置过小可能会导致数据库查询频繁，设置过大可能会导致任务状态更新不及时。
    # Time interval for checking task status (seconds). If set too small, it may cause frequent database queries.
    TASK_STATUS_CHECK_INTERVAL: int = 3


class FasterWhisperSettings(BaseModel):
    # 模型名称 | Model name
    faster_whisper_model_size_or_path: str = "large-v3"
    # 设备名称，如 "cpu" 或 "cuda", 为 'auto' 时自动选择 | Device name, such as "cpu" or "cuda", automatically selected when 'auto'
    faster_whisper_device: str = "auto"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, env_nested_delimiter="__"
    )

    fastapi: FastAPISettings = FastAPISettings()

    whisper_service: WhisperServiceSettings = WhisperServiceSettings()

    faster_whisper: FasterWhisperSettings = FasterWhisperSettings()

    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str = ""
    POSTGRES_DB: str

    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        return MultiHostUrl.build(
            scheme="postgresql+psycopg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )


settings = Settings()
