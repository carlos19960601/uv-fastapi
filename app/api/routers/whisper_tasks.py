from re import A
from typing import Union
from urllib.parse import urlparse

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status

from app.api.models.api_response_model import ErrorResponseModel, ResponseModel
from app.api.models.whisper_task_request import WhisperTaskFileOption
from app.database.models.task_models import (
    TaskStatus,
    TaskStatusHttpCode,
    TaskStatusHttpMessage,
)
from app.utils.logging_utils import configure_logging

router = APIRouter()


logger = configure_logging(name=__name__)


@router.post(
    "/tasks/create",
    response_model=ResponseModel,
    summary="创建任务 / Create task",
    response_description="创建任务的结果信息 / Result information of creating a task",
)
async def task_create(
    request: Request,
    file_upload: Union[UploadFile, str, None] = File(
        None,
        description="媒体文件（支持的格式：音频和视频，如 MP3, WAV, MP4, MKV 等） / Media file (supported formats: audio and video, e.g., MP3, WAV, MP4, MKV)",
    ),
    task_data: WhisperTaskFileOption = Query(),
) -> ResponseModel:
    """
    # [中文]

    ### 用途说明:

    - 上传媒体文件或指定媒体文件的 URL 地址，并创建一个后台处理的 Whisper 任务。
    - 任务的处理优先级可以通过`priority`参数指定。
    - 任务的类型可以通过`task_type`参数指定。
    - 任务的处理不是实时的，这样的好处是可以避免线程阻塞，提高性能。
    - 可以通过`/api/whisper/tasks/result`端点查询任务结果。
    - 此接口提供一个回调参数，用于在任务完成时通知客户端，默认发送一个 POST 请求，你可以在接口文档中回调测试接口查看示例。

    ### 参数说明:

    - `file` (UploadFile): 上传的媒体文件，支持 Ffmpeg 支持的音频和视频格式，与`file_url`参数二选一。
    - `file_url` (Optional[str]): 媒体文件的 URL 地址，与`file`参数二选一。
    - `task_type` (str): 任务类型，默认为 'transcription'，具体取值如下。
        - 当后端使用 `openai_whisper` 引擎时，支持如下取值:
            - `transcribe`: 转录任务。
            - `translate`: 根据`language`参数指定的语言进行翻译任务。
        - 当后端使用 `faster_whisper` 引擎时，支持如下取值:
            - `transcribe`: 转录任务。
            - `translate`: 根据`language`参数指定的语言进行翻译任务。
    - `callback_url` (Optional[str]): 回调URL，任务完成时通知客户端，默认为空。
        - 任务完成后回调程序会发送一个 POST 请求，包含任务数据。
        - 你可以参考接口文档中的回调测试接口在控制台查看回调信息。
        - 例如：`http://localhost/api/whisper/callback/test`
    - `priority` (TaskPriority): 任务优先级，默认为 `normal`，具体取值如下：
        - `low`: 低优先级，使用小写字母。
        - `normal`: 正常优先级，使用小写字母。
        - `high`: 高优先级，使用小写字母。
    - `language` (str): 指定输出语言，例如 'en' 或 'zh'，留空则自动检测。

    ### 返回:

    - 返回一个包含任务信息的响应，包括任务ID、状态、优先级等信息。

    ### 错误代码说明:

    - `400`: 请求参数错误，例如文件或文件URL为空。
    - `500`: 服务器内部错误，例如无法创建任务。

    # [English]

    ### Purpose:

    - Upload a media file or specify the URL address of the media file and create a Whisper task for background processing.
    - The processing priority of the task can be specified using the `priority` parameter.
    - The type of task can be specified using the `task_type` parameter.
    - The processing of the task is not real-time, which avoids thread blocking and improves performance.
    - The task result can be queried using the `/api/whisper/tasks/result` endpoint.
    - This endpoint provides a callback interface to notify the client when the task is completed, which sends a POST request by default. You can view an example in the callback test interface in the API documentation.

    ### Parameters:

    - `file` (UploadFile): The uploaded media file, supporting audio and video formats supported by Ffmpeg, either `file` or `file_url` parameter is required.
    - `file_url` (Optional[str]): URL address of the media file, either `file` or `file_url` parameter is required.
    - `task_type` (str): The type of
    task, default is 'transcription', specific values are as follows.
        - When the backend uses the `openai_whisper` engine, the following values are supported:
            - `transcribe`: Transcription task.
            - `translate`: Translation task based on the language specified by the `language` parameter.
        - When the backend uses the `faster_whisper` engine, the following values are supported:
            - `transcribe`: Transcription task.
            - `translate`: Translation task based on the language specified by the `language` parameter.
    - `callback_url` (Optional[str]): Callback URL to notify the client when the task is completed, default is empty.
        - The callback program will send a POST request containing task data after the task is completed.
        - You can view the callback information in the console by referring to the callback test interface in the API documentation.
        - For example: `http://localhost/api/whisper/callback/test`
    - `priority` (TaskPriority): Task priority, default is `normal`, specific values are as follows:
        - `low`: Low priority, use lowercase letters.
        - `normal`: Normal priority, use lowercase letters.
        - `high`: High priority, use lowercase letters.
    - `language` (str): Specify the output language, e.g., 'en' or 'zh', leave empty for auto-detection.

    ### Returns:

    - Returns a response containing task information, including task ID, status, priority, etc.

    ### Error Code Description:

    - `400`: Request parameter error, such as file or file URL is empty.
    - `500`: Unknown error.
    """

    # 检查文件或文件URL是否为空 | Check if the file or file URL is empty
    if not (file_upload or task_data.file_url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponseModel(
                code=status.HTTP_400_BAD_REQUEST,
                message="The 'file_upload' and 'file_url' parameters cannot be both provided, you must provide only one of them.",
                params=dict(request.query_params),
            ).model_dump(),
        )

    # 检查文件和文件URL是否同时存在 | Check if both file and file URL are provided
    if file_upload and task_data.file_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ErrorResponseModel(
                code=status.HTTP_400_BAD_REQUEST,
                message="The 'file_upload' and 'file_url' parameters cannot be both provided, you must provide only one of them.",
                params=dict(request.query_params),
            ).model_dump(),
        )

    # 检查 URL 格式是否正确 | Check if the URL format is correct
    if task_data.file_url:
        parsed_url = urlparse(task_data.file_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ErrorResponseModel(
                    code=status.HTTP_400_BAD_REQUEST,
                    message="The 'file_url' parameter is not a valid URL address.",
                    params=dict(request.query_params),
                ).model_dump(),
            )

    try:
        decode_options = {
            "language": task_data.language if task_data.language else None,
            "temperature": (
                [float(temp) for temp in task_data.temperature.split(",")]
                if "," in task_data.temperature
                else float(task_data.temperature)
            ),
        }

        task_info = await request.app.state.whisper_service.create_whisper_task(
            file_upload=file_upload if file_upload else None,
            file_name=file_upload.filename if file_upload else None,
            file_url=task_data.file_url if task_data.file_url else None,
            callback_url=task_data.callback_url,
            decode_options=decode_options,
            task_type=task_data.task_type,
            priority=task_data.priority,
            request=request,
        )

        return ResponseModel(
            code=200,
            params={
                **decode_options,
                "task_type": task_data.task_type,
                "callback_url": task_data.callback_url,
            },
            data=task_info.to_dict(),
        )

    except HTTPException as http_error:
        raise http_error
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseModel(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"An unexpected error occurred while creating the transcription task: {str(e)}",
                params=dict(request.query_params),
            ).model_dump(),
        )


@router.get(
    "/tasks/result",
    response_model=ResponseModel,
    summary="获取任务结果 / Get task result",
    response_description="获取任务结果的结果信息 / Result information of getting task result",
)
async def task_result(
    request: Request,
    task_id: int = Query(..., description="任务ID / Task ID"),
) -> ResponseModel:
    """
    # [中文]

    ### 用途说明:
    - 获取指定任务的结果信息。

    ### 参数说明:
    - `task_id` (int): 任务ID。

    ### 返回:
    - 返回一个包含任务结果信息的响应，包括任务ID、状态、优先级等信息。

    ### 错误代码说明:
    - `200`: 任务已完成，返回任务结果信息。
    - `202`: 任务处于排队中，或正在处理中。
    - `404`: 任务未找到，可能是任务ID不存在。
    - `500`: 任务处理失败，或发生未知错误。
    - `503`: 数据库错误。

    # [English]

    ### Purpose:
    - Get the result information of the specified task.

    ### Parameters:
    - `task_id` (int): Task ID.

    ### Returns:
    - Returns a response containing task result information, including task ID, status, priority, etc.

    ### Error Code Description:
    - `200`: Task is completed, return task result information.
    - `202`: Task is queued or processing.
    - `404`: Task not found, possibly because the task ID does not exist.
    - `500`: Task processing failed or an unknown error occurred.
    - `503`: Database error.
    """
    try:
        # 通过任务ID查询任务 | Query task by task ID
        task = request.app.state.db_manager.get_task(task_id)
        if not task:
            # 任务未找到 - 返回404 | Task not found - return 404
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ErrorResponseModel(
                    code=status.HTTP_404_NOT_FOUND,
                    message=TaskStatusHttpMessage.not_found.value,
                    router=str(request.url),
                    params=dict(request.query_params),
                ).model_dump(),
            )
        # 任务处于排队中 - 返回202 | Task is queued - return 202
        if task.status == TaskStatus.queued:
            raise HTTPException(
                status_code=TaskStatusHttpCode.queued.value,
                detail=ErrorResponseModel(
                    code=TaskStatusHttpCode.queued.value,
                    message=TaskStatusHttpMessage.queued.value,
                    router=str(request.url),
                    params=dict(request.query_params),
                ).model_dump(),
            )
        # 任务正在处理中 - 返回202 | Task is processing - return 202
        elif task.status == TaskStatus.processing:
            raise HTTPException(
                status_code=TaskStatusHttpCode.processing.value,
                detail=ErrorResponseModel(
                    code=TaskStatusHttpCode.processing.value,
                    message=TaskStatusHttpMessage.processing.value,
                    router=str(request.url),
                    params=dict(request.query_params),
                ).model_dump(),
            )
        # 任务失败 - 返回500 | Task failed - return 500
        elif task.status == TaskStatus.failed:
            raise HTTPException(
                status_code=TaskStatusHttpCode.failed.value,
                detail=ErrorResponseModel(
                    code=TaskStatusHttpCode.failed.value,
                    message=TaskStatusHttpMessage.failed.value,
                    router=str(request.url),
                    params=dict(request.query_params),
                ).model_dump(),
            )

        # 任务已完成 - 返回200 | Task is completed - return 200
        return ResponseModel(
            code=TaskStatusHttpCode.completed.value,
            router=str(request.url),
            params=dict(request.query_params),
            data=task.to_dict(),
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ErrorResponseModel(
                code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                message=f"An unexpected error occurred while getting the task result: {str(e)}",
            ).model_dump(),
        )
