from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.context import CurrentUser, client_ip_ctx, request_id_ctx
from app.modules.audit.models import AuditLog

RESOURCE_PROJECT = "project"


def record(
    db: Session,
    *,
    user: CurrentUser,
    action: str,
    resource_type: str,
    resource_id: UUID,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            request_id=request_id_ctx.get(),
            ip=client_ip_ctx.get(),
        )
    )
    db.flush()
