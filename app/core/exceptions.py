from __future__ import annotations

import logging
from collections.abc import Callable
from enum import IntEnum
from typing import cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ExceptionHandler

from app.core.response import ErrorDetail, ErrorEnvelope

logger = logging.getLogger(__name__)

# 业务码编码规则：业务码 = HTTP 状态码 * 100 + 两位资源序号。
#   40401 = HTTP 404 + 资源序号 01
#   40400 = HTTP 404 的通用错误，序号 00 保留给没有专属码的场合
# 这条规则是双向的，下面两个函数必须互为逆运算——别再在别处手写 //100 或 *100。
_CODE_SCALE = 100
_MIN_ERROR_STATUS = 400
_MAX_ERROR_STATUS = 599


def http_status_of(code: int) -> int:
    """业务码 → HTTP 状态码。不符合编码规则的码在这里就炸，而不是回一个非法状态。"""
    status = code // _CODE_SCALE
    if not _MIN_ERROR_STATUS <= status <= _MAX_ERROR_STATUS:
        raise ValueError(
            f"业务码 {code} 不符合编码规则：前三位必须是 4xx / 5xx 的 HTTP 状态码"
        )
    return status


def biz_code_of(http_status: int) -> int:
    """HTTP 状态码 → 该状态的通用业务码。404 → 40400。"""
    return http_status * _CODE_SCALE


class BizCode(IntEnum):
    """core 自己抛的通用码。模块专属码定义在各自模块里，编码规则同上。"""

    UNAUTHORIZED = 40100
    FORBIDDEN = 40300
    VALIDATION_ERROR = 42200
    INTERNAL_ERROR = 50000


class AppError(Exception):
    def __init__(
        self,
        code: int,
        message: str,
        *,
        details: list[ErrorDetail] | None = None,
    ) -> None:
        super().__init__(message)
        # 在 raise 处校验，traceback 才指向真正写错码的那一行
        self.http_status = http_status_of(code)
        self.code = int(code)
        self.message = message
        self.details = details or []


_CONSTRAINT_ERRORS: dict[str, tuple[int, str]] = {}


def register_constraint_error(constraint: str, code: int, message: str) -> None:
    """登记「数据库约束名 → 业务 409」。由拥有该约束的模块调用，core 不认识业务。"""
    if http_status_of(code) != 409:
        raise ValueError(f"约束冲突的业务码必须是 409xx，收到 {code}")
    _CONSTRAINT_ERRORS[constraint] = (code, message)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def envelope_json(
    request: Request,
    *,
    http_status: int,
    code: int,
    message: str,
    details: list[ErrorDetail] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    payload = ErrorEnvelope(
        code=code,
        message=message,
        details=details or [],
        request_id=request_id,
    )
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(
        status_code=http_status,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return envelope_json(
        request,
        http_status=exc.http_status,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return envelope_json(
        request,
        http_status=exc.status_code,
        code=biz_code_of(exc.status_code),
        message=message,
    )


def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details = [
        ErrorDetail(loc=list(error["loc"]), msg=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    return envelope_json(
        request,
        http_status=http_status_of(BizCode.VALIDATION_ERROR),
        code=BizCode.VALIDATION_ERROR,
        message="参数校验失败",
        details=details,
    )


def _violated_constraint(exc: IntegrityError) -> str | None:
    name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    return name if isinstance(name, str) else None


def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    mapped = _CONSTRAINT_ERRORS.get(_violated_constraint(exc) or "")
    if mapped is None:
        # NOT NULL / 外键违约，以及没登记的唯一约束，都是代码 bug 而不是客户端冲突。
        # 一律 500 + traceback，别伪装成 409 咽掉。
        return unhandled_exception_handler(request, exc)
    code, message = mapped
    return envelope_json(
        request,
        http_status=http_status_of(code),
        code=code,
        message=message,
    )


def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 必须用 exc_info=exc：handler 有时在 sys.exc_info() 已经清空后才被调用，
    # logger.exception() 那时会打出一条没有 traceback 的日志。
    logger.error(
        "unhandled error",
        exc_info=exc,
        extra={"request_id": _request_id(request)},
    )
    return envelope_json(
        request,
        http_status=http_status_of(BizCode.INTERNAL_ERROR),
        code=BizCode.INTERNAL_ERROR,
        message="服务器内部错误",
    )


def register_exception_handlers(application: FastAPI) -> None:
    # handler 按真实异常类型标注，只在注册这一处 cast。
    # Starlette 的 ExceptionHandler 只认 (Request, Exception)，原先靠
    # `assert isinstance(exc, ...)` 收窄，而 assert 在 `python -O` 下会被剥掉。
    handlers: list[tuple[type[Exception], Callable[..., JSONResponse]]] = [
        (AppError, app_error_handler),
        (StarletteHTTPException, http_exception_handler),
        (RequestValidationError, validation_exception_handler),
        (IntegrityError, integrity_error_handler),
        (Exception, unhandled_exception_handler),
    ]
    for exc_type, handler in handlers:
        application.add_exception_handler(exc_type, cast(ExceptionHandler, handler))
