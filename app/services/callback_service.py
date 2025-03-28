import datetime
from typing import Optional

from app.database.database_manager import DatabaseManager
from app.database.models.task_models import Task
from app.http_client.async_http_client import AsyncHttpClient
from app.utils.logging_utils import configure_logging


class CallbackService:
    def __init__(self):
        self.default_headers = {
            "User-Agent": "UV-Fastapi/HTTP Callback",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
        }
        self.logger = configure_logging(__name__)

    async def task_callback_notification(
        self,
        task: Task,
        db_manager: DatabaseManager,
        method: str = "POST",
        headers: Optional[dict] = None,
        request_timeout: int = 10,
    ) -> None:
        """
        发送任务处理结果的回调通知。

        Sends a callback notification with the result of the task processing.

        :param task: 要发送回调通知的任务实例 | Task instance to send callback notification for
        :param db_manager: 数据库管理器实例 | Database manager instance
        :param proxy_settings: 可选的代理设置 | Optional proxy settings
        :param method: 可选的请求方法 | Optional request method
        :param headers: 可选的请求头 | Optional request headers
        :param request_timeout: 请求超时时间 | Request timeout
        :return: None
        """
        callback_url = task.callback_url
        headers = headers or self.default_headers
        if callback_url:
            async with AsyncHttpClient() as client:
                # 获取任务数据 | Get task data
                task_data = await db_manager.get_task(task.id)

                response = await client.fetch_data(
                    method=method,
                    url=callback_url,
                    headers=headers,
                    json=task_data.to_dict(),
                )

                # 更新任务的回调状态码和消息 | Update the callback status code and message of the task
                self.logger.info(
                    f"Callback response status code for task {task.id}: {response.status_code}"
                )
                await db_manager.update_task_callback_status(
                    task_id=task.id,
                    callback_status_code=response.status_code,
                    callback_message=response.text,
                    callback_time=datetime.datetime.now(),
                )

        else:
            self.logger.info(
                f"No callback URL provided for task {task.id}, skipping callback notification."
            )
