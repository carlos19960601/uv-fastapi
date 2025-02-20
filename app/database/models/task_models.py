import enum
from typing import Optional

from sqlmodel import Field, SQLModel


class TaskStatus(enum.Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    # 任务ID | Task ID
    id: Optional[int] = Field(default=None, primary_key=True)
    # 任务类型 | Task type
    task_type: str = Field(max_length=50, nullable=False)
    # 任务状态，初始为 QUEUED | Task status, initially QUEUED
    status: TaskStatus = Field(default=TaskStatus.queued)
    # 引擎名称 | Engine name
    engine_name: str = Field(max_length=50, nullable=True)

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

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status.value,
            "engine_name": self.engine_name,
            "task_type": self.task_type,
            "file_path": self.file_path,
            "file_url": self.file_url,
            "file_name": self.file_name,
            "file_size_bytes": self.file_size_bytes,
            "file_duration": self.file_duration,
        }
