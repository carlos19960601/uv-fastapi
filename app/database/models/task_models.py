import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class TaskStatus(enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TaskPriority(enum.Enum):
    high = "high"
    normal = "normal"
    low = "low"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    # 任务ID | Task ID
    id: Optional[int] = Field(default=None, primary_key=True)
    # 任务类型 | Task type
    task_type: str = Field(max_length=50, nullable=False)
    # 回调 URL | Callback URL
    callback_url: str = Field(max_length=512, nullable=True)
    # 回调状态码 | Callback status code
    callback_status_code: int = Field(nullable=True)
    # 回调消息 | Callback message
    callback_message: str = Field(max_length=512, nullable=True)
    # 回调时间 | Callback time
    callback_time: datetime = Field(nullable=True)
    # 任务优先级 | Task priority
    priority: TaskPriority = Field(max_length=50, nullable=True)
    # 任务状态，初始为 QUEUED | Task status, initially QUEUED
    status: TaskStatus = Field(default=TaskStatus.queued)
    # 检测到的语言 | Detected language
    language: str = Field(max_length=10, nullable=True)
    # 任务对应的平台 | Platform for the task
    platform: str = Field(max_length=50, nullable=True)
    # 引擎名称 | Engine name
    engine_name: str = Field(max_length=50, nullable=True)
    # 创建日期 | Creation date
    created_at: datetime = Field(default=datetime.now())
    # 更新时间 | Update date
    updated_at: datetime = Field(default=datetime.now())
    # 处理任务花费的总时间 | Total time spent processing the task
    task_processing_time: float = Field(nullable=True)

    # 文件路径 | File path
    file_path: str = Field(nullable=True)
    # 文件名称 | File name
    file_name: str = Field(nullable=True)
    # 文件URL | File URL
    file_url: str = Field(nullable=True)
    # 文件大小（字节） | File size (bytes)
    file_size_bytes: int = Field(nullable=True)
    # 音频时长 | Audio duration
    file_duration: float = Field(nullable=True)

    # 解码选项 | Decode options
    decode_options: dict = Field(sa_type=JSON)

    # 结果 | Result
    result: dict = Field(nullable=True, sa_type=JSON)
    # 错误信息 | Error message
    error_message: str = Field(nullable=True)
    # 输出结果链接 | Output URL
    output_url: str = Field(max_length=255, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status.value,
            "callback_url": self.callback_url,
            "callback_status_code": self.callback_status_code,
            "callback_message": self.callback_message,
            "callback_time": (
                self.callback_time.isoformat() if self.callback_time else None
            ),
            "priority": self.priority.value,
            "engine_name": self.engine_name,
            "task_type": self.task_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "task_processing_time": self.task_processing_time,
            "file_path": self.file_path,
            "file_url": self.file_url,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "file_duration": self.file_duration,
            "language": self.language,
            "platform": self.platform,
            "decode_options": self.decode_options,
            "error_message": self.error_message,
            "output_url": self.output_url,
            "result": self.result,
        }
