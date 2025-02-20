import asyncio
import threading
import time

from app.database.database_manager import DatabaseManager
from app.database.models.task_models import Task, TaskStatus
from app.model_pool.async_model_pool import AsyncModelPool
from app.utils.logging_utils import configure_logging


class TaskProcessor:
    """
    任务处理器类，用于从数据库中获取任务并在后台处理任务。

    Task processor class for fetching tasks from the database and processing them in the background.
    """

    def __init__(
        self,
        model_pool: AsyncModelPool,
        database_type: str,
        database_url: str,
        max_concurrent_tasks: int,
        task_status_check_interval: int,
    ) -> None:
        self.model_pool: AsyncModelPool = model_pool
        # 保存数据库类型 | Save database type
        self.database_type = database_type
        # 保存数据库 URL | Save database URL
        self.database_url = database_url
        # 初始化查询请求队列 | Initialize query request queue
        self.fetch_queue: asyncio.Queue = asyncio.Queue()
        # 初始化任务队列 | Initialize task queue
        self.update_queue = asyncio.Queue()
        # 创建任务处理队列 | Create task processing queue
        self.task_processing_queue = asyncio.Queue()
        # 创建清理队列 | Create cleanup queue
        self.cleanup_queue = asyncio.Queue()
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

        # 在事件循环中初始化数据库管理器
        self.loop.run_until_complete(self.initialize_db_manager())

        # 使用 create_task 启动 fetch_task_worker 作为持续运行的后台任务 | Start fetch_task_worker as a continuous background task using create_task
        self.loop.create_task(self.fetch_task_worker())

        # 使用 create_task 启动 process_update_queue 作为持续运行的后台任务 | Start process_update_queue as a continuous background task using create_task
        # self.loop.create_task(self.update_task_worker())

        # 使用 create_task 启动 process_tasks 作为持续运行的后台任务 | Start process_tasks as a continuous background task using create_task
        self.loop.create_task(self.process_tasks_worker())

        # 使用 create_task 启动 cleanup_worker 作为持续运行的后台任务 | Start cleanup_worker as a continuous background task using create_task
        # self.loop.create_task(self.cleanup_worker())

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
        while not self.shutdown_event.is_set():
            try:
                await self.fetch_queue.put("fetch")
                tasks: list[Task] = await self.task_processing_queue.get()

                if tasks:
                    await self._process_multiple_tasks(tasks)
                else:
                    current_time = time.time()
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
                    await self.db_manager.update_task(
                        task.id, status=TaskStatus.processing
                    )
                    # 将结果放入 task_result_queue 中 | Put the result into task_result_queue
                await self.task_processing_queue.put(tasks)
            except Exception as e:
                self.logger.error(f"Error fetching tasks from database: {str(e)}")
            finally:
                # 标记查询完成 | Mark the query as completed
                self.fetch_queue.task_done()
