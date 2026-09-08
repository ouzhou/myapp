from typing import Any

from fastapi import APIRouter

from app.core.response import Envelope, ErrorEnvelope, ok
from app.deps import DbSession, HeaderIdentityDep
from app.modules.users import service as user_service
from app.modules.users.schemas import CurrentTenantUpdate, MeRead

UNAUTHORIZED: dict[int | str, dict[str, Any]] = {401: {"model": ErrorEnvelope}}
FORBIDDEN: dict[int | str, dict[str, Any]] = {403: {"model": ErrorEnvelope}}

router = APIRouter(tags=["users"], responses=UNAUTHORIZED)


@router.get("/me", responses=FORBIDDEN)
def get_me(db: DbSession, identity: HeaderIdentityDep) -> Envelope[MeRead]:
    return ok(
        user_service.get_me(db, identity.user_id, identity.requested_tenant_id)
    )


@router.put("/me/current-tenant", responses=FORBIDDEN)
def put_current_tenant(
    payload: CurrentTenantUpdate,
    db: DbSession,
    identity: HeaderIdentityDep,
) -> Envelope[MeRead]:
    return ok(user_service.switch_current_tenant(db, identity.user_id, payload.tenant_id))
