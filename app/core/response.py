from typing import Annotated, Generic, TypeVar

from fastapi import Depends, Query
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


class Pagination(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


def pagination_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Pagination:
    return Pagination(page=page, page_size=page_size)


PaginationParams = Annotated[Pagination, Depends(pagination_params)]


def ok(data: T, message: str = "ok") -> Envelope[T]:
    return Envelope(code=0, message=message, data=data)
