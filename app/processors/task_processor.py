import asyncio
import datetime
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable, List, Optional
from dataclasses import asdict, is_dataclass

from app.api.routers.whisper_tasks import task_create
from app.core.config import settings
from app.database.database_manager import DatabaseManager
from app.database.models.task_models import Task, TaskStatus
from app.model_pool.async_model_pool import AsyncModelPool
from app.utils.file_utils import FileUtils
from app.utils.logging_utils import configure_logging

# 初始化静态线程池，所有实例共享 | Initialize static thread pool, shared by all instances
_executor: ThreadPoolExecutor = ThreadPoolExecutor()


class TaskProcessor:
    """
    任务处理器类，用于从数据库中获取任务并在后台处理任务。

    Task processor class for fetching tasks from the database and processing them in the background.
    """

    def __init__(
        self,
        model_pool: AsyncModelPool,
        file_utils: FileUtils,
        database_type: str,
        database_url: str,
        max_concurrent_tasks: int,
        task_status_check_interval: int,
    ) -> None:
        self.model_pool: AsyncModelPool = model_pool
        self.file_utils: FileUtils = file_utils
        # 保存数据库类型 | Save database type
        self.database_type = database_type
        # 保存数据库 URL | Save database URL
        self.database_url = database_url
        # 初始化数据库管理器 | Initialize database manager
        self.db_manager: Optional[DatabaseManager] = None

        self.logger = configure_logging(name=__name__)
        self.loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self.thread: threading.Thread = threading.Thread(target=self.run_loop)
        self.shutdown_event: threading.Event = threading.Event()
        self.max_concurrent_tasks: int = max_concurrent_tasks
        self.task_status_check_interval: int = task_status_check_interval

    def start(self) -> None:
        """
        启动任务处理器的后台线程和事件循环。

        Starts the background thread and event loop for task processing.

        :return: None
        """
        self.thread.start()
        self.logger.info("TaskProcessor started.")

    def stop(self) -> None:
        self.shutdown_event.set()
        # 以线程安全的方式停止事件循环 | Stop the event loop in a thread-safe manner
        self.loop.call_soon_threadsafe(self.loop.stop)
        # 等待线程结束 | Wait for the thread to finish
        self.thread.join()
        self.logger.info("TaskProcessor stopped.")

    def run_loop(self) -> None:
        """
        在后台运行异步事件循环以处理任务队列，直到停止信号触发。

        Runs the asynchronous event loop in the background to process the task queue until a stop signal is triggered.
        """
        asyncio.set_event_loop(self.loop)

        # 初始化查询请求队列 | Initialize query request queue
        self.fetch_queue: asyncio.Queue = asyncio.Queue()
        # 创建任务处理队列 | Create task processing queue
        self.task_processing_queue = asyncio.Queue()
        # 初始化任务队列 | Initialize task queue
        self.update_queue = asyncio.Queue()
        # 创建清理队列 | Create cleanup queue
        self.cleanup_queue = asyncio.Queue()
        # 创建回调队列 | Create callback queue
        self.callback_queue = asyncio.Queue()

        # 在事件循环中初始化数据库管理器
        self.loop.run_until_complete(self.initialize_db_manager())

        # 使用 create_task 启动 fetch_task_worker 作为持续运行的后台任务 | Start fetch_task_worker as a continuous background task using create_task
        self.loop.create_task(self.fetch_task_worker())

        # 使用 create_task 启动 process_update_queue 作为持续运行的后台任务 | Start process_update_queue as a continuous background task using create_task
        self.loop.create_task(self.update_task_worker())

        # 使用 create_task 启动 process_tasks 作为持续运行的后台任务 | Start process_tasks as a continuous background task using create_task
        self.loop.create_task(self.process_tasks_worker())

        # 使用 create_task 启动 cleanup_worker 作为持续运行的后台任务 | Start cleanup_worker as a continuous background task using create_task
        self.loop.create_task(self.cleanup_worker())

        # 使用 create_task 启动 callback_worker 作为持续运行的后台任务 | Start callback_worker as a continuous background task using create_task
        # self.loop.create_task(self.callback_worker())

        # 使用 run_forever 让事件循环一直运行，直到 stop 被调用 | Use run_forever to keep the event loop running until stop is called
        self.loop.run_forever()

        self.loop.close()
        self.logger.info("TaskProcessor Event loop closed.")

    async def initialize_db_manager(self) -> None:
        """
        在 TaskProcessor 的事件循环中初始化独立的数据库管理器，这是为了确保连接池绑定到 TaskProcessor 的事件循环。

        Initializes a separate database manager in the TaskProcessor's event loop to ensure the connection pool is bound to the TaskProcessor's event loop.

        :return: None
        """
        self.db_manager = DatabaseManager(
            database_type=self.database_type,
            database_url=self.database_url,
            loop=self.loop,
        )
        self.db_manager.initialize()

    async def process_tasks_worker(self):
        """
        持续从数据库中按优先级拉取任务并处理。若无任务，则等待并重试。

        Continuously fetches tasks from the database by priority and processes them. Waits and retries if no tasks are available.

        :return: None
        """
        # 记录上次日志输出的时间 | Record the time of the last log output
        last_log_time = 0
        # 日志输出间隔，单位为秒 | Log output interval in seconds
        log_delay = 30

        while not self.shutdown_event.is_set():
            try:
                await self.fetch_queue.put("fetch")
                tasks: list[Task] = await self.task_processing_queue.get()

                if tasks:
                    await self._process_multiple_tasks(tasks)
                else:
                    current_time = time.time()
                    if current_time - last_log_time >= log_delay:
                        self.logger.info(
                            f"No tasks to process, waiting for new tasks..."
                        )
                        last_log_time = current_time
                    await asyncio.sleep(self.task_status_check_interval)

            except Exception as e:
                self.logger.error(
                    f"Error while pulling tasks from the database: {str(e)}"
                )
                await asyncio.sleep(self.task_status_check_interval)

    async def fetch_task_worker(self):
        """
        处理 fetch_queue 中的数据库查询请求

        Processes database query requests in the fetch_queue
        """
        while not self.shutdown_event.is_set():
            # 从 fetch_queue 中获取请求（阻塞等待） | Get request from fetch_queue (blocking wait)
            await self.fetch_queue.get()

            try:
                # 执行数据库查询
                tasks = self.db_manager.get_queued_tasks(self.max_concurrent_tasks)
                for task in tasks:
                    # 将任务状态更新为处理中 | Update task status to processing
                    self.db_manager.update_task(task.id, status=TaskStatus.processing)
                    # 将结果放入 task_result_queue 中 | Put the result into task_result_queue
                await self.task_processing_queue.put(tasks)
            except Exception as e:
                self.logger.error(f"Error fetching tasks from database: {str(e)}")
            finally:
                # 标记查询完成 | Mark the query as completed
                self.fetch_queue.task_done()

    async def update_task_worker(self):
        """
        异步处理更新队列中的数据库操作

        Asynchronously processes database operations in the update queue
        """
        while not self.shutdown_event.is_set():
            task_id, update_data = await self.update_queue.get()
            try:
                self.db_manager.update_task(task_id, **update_data)
            except Exception as e:
                self.logger.error(f"Error updating task {task_id}: {str(e)}")
            finally:
                # 标记更新完成 | Mark the query as completed
                self.update_queue.task_done()

    async def cleanup_worker(self):
        """
        异步清理工作协程，从队列中获取任务并执行文件删除和回调。

        Asynchronous cleanup worker coroutine that takes tasks from the queue and performs file deletion and callback.
        """
        while not self.shutdown_event.is_set():
            cleanup_task = await self.cleanup_queue.get()
            task = cleanup_task["task"]

            try:
                # 删除临时文件 | Delete temporary file
                if settings.file.delete_temp_files_after_processing and task.file_path:
                    await self.file_utils.delete_file(task.file_path)
                else:
                    self.logger.debug(f"Keeping temporary file: {task.file_path}")

            except Exception as e:
                self.logger.error(f"Error during cleanup for task ID {task.id}: {e}")
            finally:
                self.cleanup_queue.task_done()

    async def _process_multiple_tasks(self, tasks: List[Task]) -> None:
        """
        并行处理给定的多个任务，将每个任务提交到线程池。

        Processes multiple tasks in parallel, submitting each to the thread pool.

        :param tasks: 要处理的任务列表 | List of tasks to process
        :return: None
        """
        loop = asyncio.get_event_loop()

        # 为了不阻塞当前的事件循环，_process_task_sync 同步方法放在线程池中执行
        futures = [
            loop.run_in_executor(_executor, self._process_task_sync, task)
            for task in tasks
        ]

        # 使用 gather 并设置 return_exceptions=True 以便即使某个任务失败也不会影响其他任务
        # Use gather with return_exceptions=True to allow all tasks to complete even if some fail
        results = await asyncio.gather(*futures, return_exceptions=True)

        for task, result in zip(tasks, results):
            # 添加清理任务到队列中 | Add cleanup task to queue
            task_and_task = {
                "task": task,
                "result": result,
            }
            await self.cleanup_queue.put(task_and_task)
            if isinstance(result, Exception):
                self.logger.error(
                    f"""
                    Error processing task:
                    ID          : {task.id}
                    Engine      : {task.engine_name}
                    Priority    : {task.priority}
                    File        : {task.file_name}
                    Size        : {task.file_size_bytes} bytes
                    Duration    : {task.file_duration} seconds
                    Created At  : {task.created_at}
                    Output URL  : {task.output_url}
                    Error       : {str(result)}
                    """,
                    exc_info=result,
                )
            else:
                self.logger.info(f"Task {task.id} processed successfully.")

    def _process_task_sync(self, task: Task) -> dict:
        """
        在线程池中同步处理单个任务，包括音频转录和数据库更新。

        Synchronously processes a single task in the thread pool, including audio transcription and database updates.

        :param task: 要处理的任务实例 | The task instance to process
        :return: dict: 任务处理结果 | dict: Task processing result
        """
        try:
            self.logger.info(
                f"""
                Processing queued task:
                ID          : {task.id}
                Engine      : {task.engine_name}
                Type        : {task.task_type}
                Priority    : {task.priority}
                File        : {task.file_name}
                Size        : {task.file_size_bytes} bytes
                Duration    : {task.file_duration} seconds
                Created At  : {task.created_at}
                Output URL  : {task.output_url}
                """
            )

            # 检查任务是否需要从 URL 下载文件 | Check if the task requires downloading the file from a URL
            if not task.file_path and task.file_url:
                self.logger.info(
                    "Detected task with file URL, start downloading file from URL..."
                )

                # 异步下载文件并获取相关信息 | Asynchronously download the file and get relevant information
                task.file_path = asyncio.run(
                    self.file_utils.download_file_from_url(task.file_url)
                )

                # 检查文件路径是否有效 | Check if the file path is valid
                if not task.file_path:
                    raise ValueError("Failed to download file: file path is missing")

                # 获取文件时长和大小 | Get file duration and size
                task.file_duration = asyncio.run(
                    self.file_utils.get_audio_duration(task.file_path)
                )
                task.file_size_bytes = os.path.getsize(task.file_path)

                # 检查下载后的文件属性是否齐全 | Check if the downloaded file attributes are complete
                if (
                    not task.file_path
                    or task.file_size_bytes == 0
                    or task.file_duration == 0
                ):
                    raise ValueError(
                        "Error: Incomplete file download or invalid file attributes"
                    )

                # 日志记录 | Log the download
                self.logger.info(
                    f"""
                    Downloaded task file from URL:
                    ID          : {task.id}
                    File Path   : {task.file_path}
                    File Size   : {task.file_size_bytes} bytes
                    Duration    : {task.file_duration} seconds
                    URL         : {task.file_url}
                    """
                )

            # 获取模型实例 | Acquire a model instance
            # 同步方法中不能直接运行协程，只能通过事件循环来调度。
            model = asyncio.run(self.model_pool.get_model())

            # 如果模型是线程安全的，可以直接使用 acquire_model 方法 | If the model is thread-safe, you can use the acquire_model method directly
            # model = asyncio.run(self.model_pool.acquire_model())

            try:
                # 记录任务开始时间 | Record task start time
                task_start_time: datetime.datetime = datetime.datetime.now()

                # 执行转录任务 | Perform transcription task
                if self.model_pool.engine == "openai_whisper":
                    transcribe_result = model.transcribe(
                        task.file_path, **task.decode_options or {}, task=task.task_type
                    )
                    segments = transcribe_result["segments"]
                    language = transcribe_result.get("language")
                    # OpenAI Whisper不返回info，保持空字典 | OpenAI Whisper does not return info, keep an empty dictionary
                    info = {}
                elif self.model_pool.engine == "faster_whisper":
                    segments, info = model.transcribe(
                        task.file_path, **task.decode_options or {}, task=task.task_type
                    )
                    segments = [self.segments_to_dict(segment) for segment in segments]
                    language = info.language
                    # 转换info为字典格式 | Convert info to dictionary format
                    info = self.segments_to_dict(info)
                else:
                    raise ValueError(
                        f"Trying to process task with unsupported engine: {self.model_pool.engine}"
                    )

                # 通用的结果结构 | Common result structure
                result = {
                    "text": " ".join([seg["text"] for seg in segments]).strip(),
                    "segments": segments,
                    "info": info,
                }

                # 记录任务结束时间 | Record task end time
                task_end_time: datetime.datetime = datetime.datetime.now()
                task_processing_time = (task_end_time - task_start_time).total_seconds()

                self.logger.info(
                    f"""
                    Task processed successfully:
                    ID          : {task.id}
                    Engine      : {task.engine_name}
                    Priority    : {task.priority}
                    Type        : {task.task_type}
                    File        : {task.file_name}
                    Size        : {task.file_size_bytes} bytes
                    Duration    : {task.file_duration} seconds
                    Created At  : {task.created_at}
                    Output URL  : {task.output_url}
                    Language    : {language}
                    Processing Time: {task_processing_time} seconds
                    """
                )

                # 更新任务状态和结果 | Update task status and result
                task_update = {
                    "status": TaskStatus.completed,
                    "file_path": task.file_path,
                    "file_size_bytes": task.file_size_bytes,
                    "file_duration": task.file_duration,
                    "language": language,
                    "result": result,
                    "task_processing_time": task_processing_time,
                }
                self.update_queue.put_nowait((task.id, task_update))

            finally:
                # 将模型实例归还到池中 | Return the model instance to the pool
                asyncio.run(self.model_pool.return_model(model))

            # 返回字典格式的结果 | Return the result in dictionary format
            return task_update

        except Exception as e:
            task_update = {
                "status": TaskStatus.failed,
                "error_message": str(e)
            }
            self.update_queue.put_nowait((task.id, task_update)) 
            self.logger.error(
                f"""
                Error processing task: 
                ID          : {task.id}
                Engine      : {task.engine_name}
                Priority    : {task.priority}
                Type        : {task.task_type}
                File        : {task.file_name}
                Size        : {task.file_size_bytes} bytes
                Duration    : {task.file_duration} seconds
                Created At  : {task.created_at}
                Output URL  : {task.output_url}
                Error       : {str(e)}
                """
            )
            
            # 返回字典格式的结果 | Return the result in dictionary format
            return task_update

    @staticmethod
    def segments_to_dict(obj: Any) -> Any:
        """
        使用递归方式将Faster Whisper的 NamedTuple 转换为字典。

        Recursively converts a NamedTuple from Faster Whisper to a dictionary.

        :param obj: 要转换的对象 | Object to convert
        :return: 转换后的对象 | Converted object
        """
        # 检查对象是否具有 _asdict 方法（适用于 NamedTuple 实例）
        if hasattr(obj, "_asdict"):
            return {key: TaskProcessor.segments_to_dict(value) for key, value in obj._asdict().items()}
        # 检查对象是否是dataclass
        elif is_dataclass(obj):
            return asdict(obj)
        # 如果是列表或元组，递归转换每个元素，并保持类型
        elif isinstance(obj, (list, tuple)):
            return type(obj)(TaskProcessor.segments_to_dict(item) for item in obj)
        # 如果是字典，递归转换每个键值对
        elif isinstance(obj, dict):
            return {key: TaskProcessor.segments_to_dict(value) for key, value in obj.items()}
        # 如果是其他可迭代类型（如生成器），转为列表后递归处理dataclass
        elif isinstance(obj, Iterable) and not isinstance(obj, (str, bytes)):
            return [TaskProcessor.segments_to_dict(item) for item in obj]
        # 直接返回非复杂类型
        return obj