import pytest

from app.core.exceptions import (
    AppError,
    BizCode,
    biz_code_of,
    http_status_of,
    register_constraint_error,
)
from app.modules.projects.service import ProjectCode


@pytest.mark.parametrize("code", [*BizCode, *ProjectCode])
def test_declared_codes_follow_the_encoding_rule(code: int) -> None:
    assert 400 <= http_status_of(code) <= 599


@pytest.mark.parametrize("status", [400, 401, 404, 409, 422, 500])
def test_encoding_rule_is_bidirectional(status: int) -> None:
    assert http_status_of(biz_code_of(status)) == status


def test_app_error_rejects_code_outside_the_rule() -> None:
    with pytest.raises(ValueError, match="不符合编码规则"):
        AppError(0, "0 是成功码，不能当业务错误")
    with pytest.raises(ValueError, match="不符合编码规则"):
        AppError(404, "漏了两位资源序号")


def test_constraint_error_must_be_a_409_code() -> None:
    with pytest.raises(ValueError, match="必须是 409xx"):
        register_constraint_error("uq_whatever", ProjectCode.NOT_FOUND, "状态不匹配")
