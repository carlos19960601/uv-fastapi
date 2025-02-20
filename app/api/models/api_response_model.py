from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


# 创建一个通用的响应模型 | Create a common response model
class ResponseModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 200,
                "router": "/example/endpoint",
                "params": {"query": "example"},
                "data": {"key": "value"},
            }
        }
    )
    code: int = Field(default=200, description="HTTP status code | HTTP状态码")
    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The parameters used in the request | 请求中使用的参数",
    )
    data: Optional[Any] = Field(default=None, description="Response data | 响应数据")


# 定义错误响应模型 | Define an error response model
class ErrorResponseModel(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": 400,
                "message": "Invalid request parameters. | 请求参数无效。",
                "time": "2024-10-27 14:30:00",
                "router": "/example/endpoint",
                "params": {"param1": "invalid"},
            }
        }
    )
    
    code: int = Field(default=400, description="HTTP status code | HTTP状态码")

    message: str = Field(
        default="An error occurred. | 服务器发生错误。",
        description="Error message | 错误消息",
    )

    time: str = Field(
        default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        description="The time the error occurred | 发生错误的时间",
    )

    params: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="The parameters used in the request | 请求中使用的参数",
    )
