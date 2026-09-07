from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class Envelope(BaseModel, Generic[T]):
    """成功响应。`data` 必填，OpenAPI 里才会是 $ref 而不是 anyOf null。"""

    code: int = 0
    message: str = "ok"
    data: T


class ErrorEnvelope(BaseModel):
    """失败响应。只有这一侧才有 `details` 和 `request_id`。"""

    code: int
    message: str
    data: None = None
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None


def ok(data: T, message: str = "ok") -> Envelope[T]:
    return Envelope(code=0, message=message, data=data)
