from enum import Enum
from typing import Optional

from fastapi import Form
from pydantic import BaseModel, ConfigDict


class TaskPriority(str, Enum):
    high = "high"
    normal = "normal"
    low = "low"


class TaskType(str, Enum):
    transcribe: str = "transcribe"
    translate: str = "translate"


class WhisperTaskRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": """
            Request model for creating a Whisper transcription task.

            **Usage Notes:**
            - Upload media file or specify URL, and set task type, priority, and callback options as needed.
            - Task processing is asynchronous, with results accessible through `/api/whisper/tasks/result`.
            - See API documentation for callback examples and task type details.

            **Common Parameters:**
            - `file` or `file_url`: Specify a media file directly or provide its URL.
            - `task_type`: Choose transcription or translation as supported by the engine.
            - `priority`, `language`, and other parameters control task behavior and output formatting.
            """
        }
    )

    task_type: TaskType = Form(
        TaskType.transcribe,
        description="任务类型，默认为 'transcribe'，具体取值请参考文档 / Task type, default is 'transcribe', refer to the documentation for specific values",
    )

    callback_url: Optional[str] = Form(
        "",
        description="回调URL，任务完成时通知客户端 / Callback URL to notify the client when the task is completed",
    )

    priority: TaskPriority = Form(
        TaskPriority.normal, description="任务优先级 / Task priority"
    )


class WhisperTaskFileOption(WhisperTaskRequest):
    file_url: Optional[str] = Form(
        "", description="媒体文件的 URL 地址 / URL address of the media file"
    )
    language: str = Form(
        "",
        description="指定输出语言，例如 'en' 或 'zh'，留空则自动检测 / Specify the output language, e.g., 'en' or 'zh', leave empty for auto-detection",
    )
