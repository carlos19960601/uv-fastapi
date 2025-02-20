from typing import Literal, Optional

from pydantic import BaseModel, PostgresDsn
from pydantic_core import MultiHostUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


# FastAPI 设置 | FastAPI settings
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


# Whisper 服务类设置 | Whisper service class settings
class WhisperServiceSettings(BaseModel):
    # Whisper 服务的最大并发任务数，设置为 1 时为单任务模式 | The maximum number of concurrent tasks for the Whisper service, set to 1 for single task mode
    # 如果你有多个 GPU，可以设置大于 1，在单一 GPU 上运行多个任务无法缩短任务时间，但可以提高任务并发度 | If you have multiple GPUs, you can set it to more than 1. Running multiple tasks on a single GPU cannot shorten the task time, but can increase the task concurrency
    MAX_CONCURRENT_TASKS: int = 1
    # 检查任务状态的时间间隔（秒），如果设置过小可能会导致数据库查询频繁，设置过大可能会导致任务状态更新不及时。
    # Time interval for checking task status (seconds). If set too small, it may cause frequent database queries.
    TASK_STATUS_CHECK_INTERVAL: int = 3


# Faster Whisper 设置 | Faster Whisper settings
class FasterWhisperSettings(BaseModel):
    # 模型名称 | Model name
    faster_whisper_model_size_or_path: str = "large-v3"
    # 设备名称，如 "cpu" 或 "cuda", 为 'auto' 时自动选择 | Device name, such as "cpu" or "cuda", automatically selected when 'auto'
    faster_whisper_device: str = "auto"
    # 设备ID，当 faster_whisper_device 为 "cuda" 时有效 | Device ID, valid when faster_whisper_device is "cuda"
    faster_whisper_device_index: int = 0
    # 模型推理计算类型 | Model inference calculation type
    faster_whisper_compute_type: str = "float16"
    # 模型使用的CPU线程数，设置为 0 时使用所有可用的CPU线程 | The number of CPU threads used by the model, set to 0 to use all available CPU threads
    faster_whisper_cpu_threads: int = 0
    # 模型worker数 | Model worker count
    faster_whisper_num_workers: int = 1
    # 模型下载根目录 | Model download root directory
    faster_whisper_download_root: Optional[str] = None


# OpenAI Whisper 设置 | OpenAI Whisper settings
class OpenAIWhisperSettings(BaseModel):
    # 模型名称 | Model name
    openai_whisper_model_name: str = "large-v3"
    # 设备名称，如 "cpu" 或 "cuda", 为 None 时自动选择 | Device name, such as "cpu" or "cuda", automatically selected when None
    openai_whisper_device: Optional[str] = None
    # 模型下载根目录 | Model download root directory
    openai_whisper_download_root: Optional[str] = None
    # 是否在内存中加载模型 | Whether to load the model in memory
    openai_whisper_in_memory: bool = False


# 数据库设置 | Database settings
class DatabaseSettings(BaseModel):
    # 选择数据库类型，支持 "sqlite" 和 "mysql" | Select the database type, support "sqlite" and "mysql"
    # "sqlite"：适合小规模项目单机运行，无需安装数据库，直接使用文件存储数据 | "sqlite": Suitable for small-scale projects running on a single machine, no need to install a database, directly use file storage data
    # "mysql"：适合大规模项目分布式部署，需要安装 MySQL 数据库 | "mysql": Suitable for large-scale projects distributed deployment, need to install MySQL database
    # 如果你选择 "mysql"，请确保安装了 aiomysql | If you choose "mysql", please make sure aiomysql is installed
    # 如果你选择 "sqlite"，请确保安装了 aiosqlite | If you choose "sqlite", please make sure aiosqlite is installed
    db_type: str = "sqlite"

    # SQLite 数据库设置 | SQLite database settings
    # 数据库名字 | Database name
    sqlite_db_name: str = "WhisperServiceAPI.db"
    # 数据库 URL | Database URL
    sqlite_url: str = f"sqlite:///{sqlite_db_name}"

    # MySQL 数据库设置 | MySQL database settings
    # 数据库名字 | Database name
    mysql_db_name: str = ""
    # 数据库用户名 | Database username
    mysql_username: str = ""
    # 数据库密码 | Database password
    mysql_password: str = ""
    # 数据库地址 | Database host
    mysql_host: str = ""
    # 数据库端口 | Database port
    mysql_port: int = 3306
    # 数据库 URL | Database URL
    mysql_url: str = (
        f"mysql://{mysql_username}:{mysql_password}@{mysql_host}:{mysql_port}/{mysql_db_name}"
    )


# 日志设置 | Log settings
class LogSettings(BaseModel):
    # 日志级别 | Log level
    """
    CRITICAL = 50
    FATAL = CRITICAL
    ERROR = 40
    WARNING = 30
    WARN = WARNING
    INFO = 20
    DEBUG = 10
    NOTSET = 0
    """
    level: int = 10
    # 日志文件目录 | Log file directory
    log_dir: str = "./log_files"
    # 日志文件前缀 | Log file prefix
    log_file_prefix: str = "app"
    # 日志文件编码 | Log file encoding
    encoding: str = "utf-8"
    # 日志文件备份数 | Log file backup count
    backup_count: int = 7


# 异步模型池设置 | Asynchronous model pool settings
class AsyncModelPoolSettings(BaseModel):
    # 引擎名称 | Engine name
    # 目前只支持 "openai_whisper" 和 "faster_whisper" | Currently only supports "openai_whisper" and "faster_whisper"
    engine: str = "faster_whisper"

    # 最小的模型池大小 | Minimum model pool size
    min_size: int = 1

    # 最大的模型池大小，如果你没有多个 GPU，建议设置为 1 | Maximum model pool size, if you don't have multiple GPUs, it is recommended to set it to 1
    # 如果你有多个 GPU，可以设置大于 1，程序会自动为每个 GPU 创建一个模型实例 | If you have multiple GPUs, you can set it to more than 1, and the program will automatically create a model instance for each GPU
    max_size: int = 1

    # 每个 GPU 最多支持的实例数量，如果你的 GPU 内存足够大，可以设置大于 1 | The maximum number of instances supported by each GPU, if your GPU memory is large enough, you can set it to more than 1
    max_instances_per_gpu: int = 1

    # 是否在模型池初始化时以最大的模型池大小创建模型实例 | Whether to create model instances with the maximum model pool size when the model pool is initialized
    init_with_max_pool_size: bool = True


# 文件设置 | File settings
class FileSettings(BaseModel):
    # 是否自动删除临时文件 | Whether to automatically delete temporary files
    auto_delete: bool = True
    # 是否限制上传文件大小 | Whether to limit the size of uploaded files
    limit_file_size: bool = True
    # 最大上传文件大小（字节）| Maximum upload file size (bytes)
    max_file_size: int = 2 * 1024 * 1024 * 1024
    # 临时文件目录 | Temporary file directory
    temp_files_dir: str = "./temp_files"
    # 是否在处理后删除临时文件 | Whether to delete temporary files after processing
    delete_temp_files_after_processing: bool = True
    # 允许保存的文件类型，加强服务器安全性，为空列表时不限制 | Allowed file types, enhance server security, no restrictions when the list is empty
    allowed_file_types: list = [
        # （FFmpeg 支持的媒体文件）| (FFmpeg supported media files)
        ".3g2",
        ".3gp",
        ".aac",
        ".ac3",
        ".aiff",
        ".alac",
        ".amr",
        ".ape",
        ".asf",
        ".avi",
        ".avs",
        ".cavs",
        ".dirac",
        ".dts",
        ".dv",
        ".eac3",
        ".f4v",
        ".flac",
        ".flv",
        ".g722",
        ".g723_1",
        ".g726",
        ".g729",
        ".gif",
        ".gsm",
        ".h261",
        ".h263",
        ".h264",
        ".hevc",
        ".jpeg",
        ".jpg",
        ".lpcm",
        ".m4a",
        ".m4v",
        ".mkv",
        ".mlp",
        ".mmf",
        ".mov",
        ".mp2",
        ".mp3",
        ".mp4",
        ".mpc",
        ".mpeg",
        ".mpg",
        ".oga",
        ".ogg",
        ".ogv",
        ".opus",
        ".png",
        ".rm",
        ".rmvb",
        ".rtsp",
        ".sbc",
        ".spx",
        ".svcd",
        ".swf",
        ".tak",
        ".thd",
        ".tta",
        ".vc1",
        ".vcd",
        ".vid",
        ".vob",
        ".wav",
        ".wma",
        ".wmv",
        ".wv",
        ".webm",
        ".yuv",
        # （字幕文件）| (Subtitle files)
        ".srt",
        ".vtt",
    ]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_ignore_empty=True, env_nested_delimiter="__"
    )

    fastapi: FastAPISettings = FastAPISettings()

    database: DatabaseSettings = DatabaseSettings()

    log: LogSettings = LogSettings()

    file: FileSettings = FileSettings()

    async_model_pool: AsyncModelPoolSettings = AsyncModelPoolSettings()

    whisper_service: WhisperServiceSettings = WhisperServiceSettings()

    faster_whisper: FasterWhisperSettings = FasterWhisperSettings()

    openai_whisper: OpenAIWhisperSettings = OpenAIWhisperSettings()

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
