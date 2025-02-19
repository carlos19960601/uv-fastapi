from fastapi import APIRouter, status
from pydantic import BaseModel

router = APIRouter(tags=["Health Check"])


class HealthCheckResponse(BaseModel):
    status: str = "ok"


@router.get(
    "/check",
    summary="检查服务器是否正确响应请求 / Check if the server responds to requests correctly",
    status_code=status.HTTP_200_OK,
    response_model=HealthCheckResponse,
    responses={
        status.HTTP_200_OK: {
            "description": "服务器响应成功 / Server responds successfully",
            "content": {"application/json": {"example": {"status": "ok"}}},
        },
    },
)
def health_check():
    """
    # [中文]

    ### 用途说明:

    - 检查服务器是否正确响应请求。

    ### 参数说明:

    - 无参数。

    ### 返回结果:

    - `status`: 服务器状态，正常为 `ok`。

    # [English]

    ### Purpose:

    - Check if the server responds to requests correctly.

    ### Parameter Description:

    - No parameters.

    ### Return Result:

    - `status`: Server status, normal is `ok`.
    """
    return HealthCheckResponse()
