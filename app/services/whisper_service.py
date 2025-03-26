import os
from typing import Optional

from fastapi import UploadFile
from fastapi.responses import FileResponse
from h11 import Request

from app.core.config import settings
from app.database.database_manager import DatabaseManager
from app.database.models.task_models import Task
from app.model_pool.async_model_pool import AsyncModelPool
from app.processors.task_processor import TaskProcessor
from app.utils.file_utils import FileUtils
from app.utils.logging_utils import configure_logging


class WhisperService:
    """
    Whisper 服务类，用于处理音频和视频的转录和音频提取。

    Whisper service class for handling transcription and audio extraction of audio and video files.
    """

    def __init__(
        self,
        model_pool: AsyncModelPool,
        db_manager: DatabaseManager,
        max_concurrent_tasks: int,
        task_status_check_interval: int,
    ) -> None:
        # 配置日志记录器 | Configure logger
        self.logger = configure_logging(name=__name__)

        # 模型池 | Model pool
        self.model_pool = model_pool

        # 数据库管理器 | Database manager
        self.db_manager = db_manager

        # 最大并发任务数 | Maximum concurrent tasks
        self.max_concurrent_tasks = self.get_optimal_max_concurrent_tasks(
            max_concurrent_tasks
        )

        # 任务状态检查间隔 | Task status check interval
        self.task_status_check_interval = task_status_check_interval

        # 初始化 FileUtils 实例 | Initialize FileUtils instance
        self.file_utils = FileUtils(
            temp_dir=settings.file.temp_files_dir,
        )

        # 初始化任务处理器 | Initialize task processor
        self.task_processor = TaskProcessor(
            model_pool=self.model_pool,
            file_utils=self.file_utils,
            database_type=self.db_manager.database_type,
            database_url=self.db_manager.database_url,
            max_concurrent_tasks=self.max_concurrent_tasks,
            task_status_check_interval=self.task_status_check_interval,
        )

    def start_task_processor(self) -> None:
        """
        启动任务处理器

        Start the task processor

        :return: None
        """
        self.task_processor.start()

    def stop_task_processor(self):
        """
        停止任务处理器

        Stop the task processor

        :return: None
        """
        self.task_processor.stop()

    async def extract_audio_from_video(
        self, file: UploadFile, sample_rate: int
    ) -> FileResponse:
        self.logger.debug(f"Starting audio extraction from video file: {file.filename}")

        if not file.content_type.startswith("video/"):
            error_message = (
                f"Invalid upload file type for audio extraction: {file.content_type}"
            )
            self.logger.error(error_message)
            raise ValueError(error_message)

    async def create_whisper_task(
        self,
        file_upload: Optional[UploadFile],
        file_name: Optional[str],
        file_url: Optional[str],
        callback_url: Optional[str],
        decode_options: dict,
        task_type: str,
        priority: str,
        request: Request,
    ) -> Task:
        """
        创建一个 Whisper 任务然后保存到数据库。

        Create a Whisper task and save it to the database.

        :param file_upload: FastAPI 上传的文件对象 | FastAPI uploaded file object
        :param file_name: 文件名称 | File name
        :param file_url: 文件 URL | File URL
        :param callback_url: 回调 URL | Callback URL
        :param platform: 平台名称 | Platform name
        :param decode_options: Whisper 解码选项 | Whisper decode options
        :param task_type: Whisper 任务类型 | Whisper task type
        :param priority: 任务优先级 | Task priority
        :param request: FastAPI 请求对象 | FastAPI request object
        :return: 保存到数据库的任务对象 | Task object saved to the database
        """
        # 如果file是UploadFile对象或者bytes对象，那么就保存到临时文件夹，然后返回临时文件路径
        # If file is an UploadFile object or bytes object, save it to the temporary folder and return the temporary file path
        if file_upload:
            temp_file_path = await self.file_utils.save_uploaded_file(
                file=file_upload, file_name=file_name
            )
            self.logger.debug(
                f"Saved uploaded file to temporary path: {temp_file_path}"
            )
            duration = await self.file_utils.get_audio_duration(temp_file_path)
            file_size_bytes = os.path.getsize(temp_file_path)
        else:
            temp_file_path = None
            duration = None
            file_size_bytes = None

        with self.db_manager.get_session() as session:
            task = Task(
                engine_name=self.model_pool.engine,
                callback_url=callback_url,
                task_type=task_type,
                file_path=temp_file_path,
                file_url=file_url,
                file_name=file_name,
                file_size_bytes=file_size_bytes,
                decode_options=decode_options,
                file_duration=duration,
                priority=priority,
            )
            session.add(task)
            session.commit()
            task_id = task.id
            # 设置任务输出链接 | Set task output URL
            task.output_url = f"{request.url_for('task_result')}?task_id={task_id}"
            session.commit()
            session.refresh(task)

        self.logger.info(f"Created transcription task with ID: {task_id}")
        return task

    def get_optimal_max_concurrent_tasks(self, max_concurrent_tasks: int) -> int:
        """
        根据模型池可用实例数量返回最优的 max_concurrent_tasks。
        Returns the optimal max_concurrent_tasks based on the number of available model pool instances.
        """
        # 检查用户输入是否为有效的正整数 | Validate user input
        if max_concurrent_tasks < 1:
            self.logger.warning(
                "Invalid `max_concurrent_tasks` provided. Setting to 1 to avoid issues."
            )
            max_concurrent_tasks = 1

        pool_size = self.model_pool.pool.maxsize
        if max_concurrent_tasks > pool_size:
            self.logger.warning(
                f"""
                Detected `MAX_CONCURRENT_TASKS` had been set to {max_concurrent_tasks}, but the model pool size is only {pool_size}.
                Optimal MWhisper Service `max_concurrent_tasks` attribute from user input: {max_concurrent_tasks} -> {pool_size}.
                """
            )
            return pool_size

        return max_concurrent_tasks
