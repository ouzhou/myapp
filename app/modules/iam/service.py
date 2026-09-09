from collections.abc import Sequence
from enum import IntEnum
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.exceptions import AppError, BizCode, register_constraint_error
from app.core.permissions import Perm
from app.core.response import PageResult, Pagination
from app.modules.audit.service import record as record_audit
from app.modules.iam.models import MembershipRole, Role, RolePermission
from app.modules.iam.schemas import (
    MemberCreate,
    MemberRead,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleSummary,
    RoleUpdate,
)
from app.modules.users.models import Membership, User
from app.modules.users.schemas import UserCreate, UserProfile
from app.modules.users.service import get_or_create_membership, get_or_create_user

RESOURCE_ROLE = "role"
RESOURCE_MEMBER = "membership"

SYSTEM_ROLE_CODE = Role.CODE_TENANT_ADMIN
SYSTEM_ROLE_NAME = "租户管理员"


class IamCode(IntEnum):
    """iam 的专属业务码。资源序号 02 起，编码规则见 core/exceptions.py。"""

    ROLE_NOT_FOUND = 40402
    MEMBER_NOT_FOUND = 40403
    ROLE_CODE_CONFLICT = 40902
    LAST_TENANT_ADMIN = 40903
    SYSTEM_ROLE_PROTECTED = 40904
    SYSTEM_PERMS_LOCKED = 40905
    MEMBER_CONFLICT = 40906


register_constraint_error(
    "uq_roles_tenant_id_code",
    IamCode.ROLE_CODE_CONFLICT,
    "角色编码已存在",
)
register_constraint_error(
    "uq_memberships_user_id_tenant_id",
    IamCode.MEMBER_CONFLICT,
    "该用户已在本租户中",
)


def _all_permission_codes() -> list[str]:
    return sorted(perm.value for perm in Perm)


def _effective_permissions(db: Session, role: Role) -> list[str]:
    if role.is_system:
        return _all_permission_codes()
    return sorted(_permissions_of(db, role.id))


def list_permissions_for_membership(db: Session, membership_id: UUID) -> list[str]:
    has_system = db.scalars(
        select(Role.id)
        .join(MembershipRole, MembershipRole.role_id == Role.id)
        .where(
            MembershipRole.membership_id == membership_id,
            Role.is_system.is_(True),
        )
    ).first()
    if has_system is not None:
        return _all_permission_codes()
    rows = db.scalars(
        select(RolePermission.permission)
        .join(MembershipRole, MembershipRole.role_id == RolePermission.role_id)
        .where(MembershipRole.membership_id == membership_id)
        .distinct()
    ).all()
    return sorted(set(rows))


def ensure_system_roles(db: Session, tenant_id: UUID) -> None:
    existing = db.scalars(
        select(Role).where(
            Role.tenant_id == tenant_id,
            Role.is_system.is_(True),
            Role.code == SYSTEM_ROLE_CODE,
        )
    ).first()
    if existing is not None:
        return
    db.add(
        Role(
            tenant_id=tenant_id,
            code=SYSTEM_ROLE_CODE,
            name=SYSTEM_ROLE_NAME,
            is_system=True,
        )
    )
    db.flush()


def ensure_custom_role(
    db: Session,
    tenant_id: UUID,
    *,
    code: str,
    name: str,
    permissions: Sequence[Perm],
) -> Role:
    role = db.scalars(
        select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
    ).first()
    if role is not None:
        return role
    role = Role(tenant_id=tenant_id, code=code, name=name, is_system=False)
    db.add(role)
    db.flush()
    _replace_role_permissions(db, role, permissions)
    return role


def ensure_membership_role_by_code(
    db: Session, membership: Membership, code: str
) -> None:
    role = db.scalars(
        select(Role).where(Role.tenant_id == membership.tenant_id, Role.code == code)
    ).first()
    if role is None:
        raise AppError(IamCode.ROLE_NOT_FOUND, "角色不存在")
    already = db.scalars(
        select(MembershipRole).where(
            MembershipRole.membership_id == membership.id,
            MembershipRole.role_id == role.id,
        )
    ).first()
    if already is not None:
        return
    db.add(
        MembershipRole(
            membership_id=membership.id,
            role_id=role.id,
            tenant_id=membership.tenant_id,
        )
    )
    db.flush()


def list_permission_catalog() -> list[PermissionRead]:
    return [PermissionRead(code=perm.value) for perm in Perm]


def _permissions_of(db: Session, role_id: UUID) -> list[str]:
    return list(
        db.scalars(
            select(RolePermission.permission).where(RolePermission.role_id == role_id)
        )
    )


def _role_read(db: Session, role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        tenant_id=role.tenant_id,
        code=role.code,
        name=role.name,
        is_system=role.is_system,
        permissions=_effective_permissions(db, role),
        created_at=role.created_at,
        updated_at=role.updated_at,
    )


def _role_snapshot(db: Session, role: Role) -> dict[str, Any]:
    return {
        "code": role.code,
        "name": role.name,
        "is_system": role.is_system,
        "permissions": _effective_permissions(db, role),
    }


def _get_role(db: Session, user: CurrentUser, role_id: UUID) -> Role:
    role = db.scalars(
        select(Role).where(Role.id == role_id, Role.tenant_id == user.tenant_id)
    ).first()
    if role is None:
        raise AppError(IamCode.ROLE_NOT_FOUND, "角色不存在")
    return role


def _replace_role_permissions(
    db: Session, role: Role, permissions: Sequence[Perm]
) -> None:
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    seen: set[str] = set()
    for perm in permissions:
        if perm.value in seen:
            continue
        seen.add(perm.value)
        db.add(RolePermission(role_id=role.id, permission=perm.value))
    db.flush()


def list_roles(
    db: Session, user: CurrentUser, pagination: Pagination
) -> PageResult[RoleRead]:
    conditions = [Role.tenant_id == user.tenant_id]
    total = db.scalar(select(func.count()).select_from(Role).where(*conditions)) or 0
    rows = db.scalars(
        select(Role)
        .where(*conditions)
        .order_by(Role.is_system.desc(), Role.code.asc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    return PageResult(
        items=[_role_read(db, role) for role in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


def _require_unique_code(
    db: Session, tenant_id: UUID, code: str, *, exclude_id: UUID | None = None
) -> None:
    query = select(Role).where(Role.tenant_id == tenant_id, Role.code == code)
    if exclude_id is not None:
        query = query.where(Role.id != exclude_id)
    if db.scalars(query).first() is not None:
        raise AppError(IamCode.ROLE_CODE_CONFLICT, "角色编码已存在")


def create_role(db: Session, user: CurrentUser, payload: RoleCreate) -> RoleRead:
    _require_unique_code(db, user.tenant_id, payload.code)
    role = Role(
        tenant_id=user.tenant_id,
        code=payload.code,
        name=payload.name,
        is_system=False,
    )
    db.add(role)
    db.flush()
    _replace_role_permissions(db, role, payload.permissions)
    record_audit(
        db,
        user=user,
        action="create",
        resource_type=RESOURCE_ROLE,
        resource_id=role.id,
        after=_role_snapshot(db, role),
    )
    return _role_read(db, role)


def update_role(
    db: Session, user: CurrentUser, role_id: UUID, payload: RoleUpdate
) -> RoleRead:
    role = _get_role(db, user, role_id)
    if role.is_system:
        raise AppError(IamCode.SYSTEM_ROLE_PROTECTED, "系统角色不能修改")
    before = _role_snapshot(db, role)
    changes = payload.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] != role.code:
        _require_unique_code(db, user.tenant_id, changes["code"], exclude_id=role.id)
    for field, value in changes.items():
        setattr(role, field, value)
    db.flush()
    record_audit(
        db,
        user=user,
        action="update",
        resource_type=RESOURCE_ROLE,
        resource_id=role.id,
        before=before,
        after=_role_snapshot(db, role),
    )
    return _role_read(db, role)


def delete_role(db: Session, user: CurrentUser, role_id: UUID) -> None:
    role = _get_role(db, user, role_id)
    if role.is_system:
        raise AppError(IamCode.SYSTEM_ROLE_PROTECTED, "系统角色不能删除")
    before = _role_snapshot(db, role)
    record_audit(
        db,
        user=user,
        action="delete",
        resource_type=RESOURCE_ROLE,
        resource_id=role.id,
        before=before,
    )
    db.delete(role)
    db.flush()


def replace_role_permissions(
    db: Session,
    user: CurrentUser,
    role_id: UUID,
    permissions: Sequence[Perm],
) -> RoleRead:
    role = _get_role(db, user, role_id)
    if role.is_system:
        raise AppError(IamCode.SYSTEM_PERMS_LOCKED, "系统角色的权限不能修改")
    before = _role_snapshot(db, role)
    _replace_role_permissions(db, role, permissions)
    record_audit(
        db,
        user=user,
        action="update",
        resource_type=RESOURCE_ROLE,
        resource_id=role.id,
        before=before,
        after=_role_snapshot(db, role),
    )
    return _role_read(db, role)


def _get_membership(db: Session, user: CurrentUser, membership_id: UUID) -> Membership:
    membership = db.scalars(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == user.tenant_id,
            Membership.status == Membership.STATUS_ACTIVE,
        )
    ).first()
    if membership is None:
        raise AppError(IamCode.MEMBER_NOT_FOUND, "成员不存在")
    return membership


def _tenant_admin_count(db: Session, tenant_id: UUID) -> int:
    return db.scalar(
        select(func.count(func.distinct(MembershipRole.membership_id)))
        .select_from(MembershipRole)
        .join(Role, Role.id == MembershipRole.role_id)
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .where(
            Membership.tenant_id == tenant_id,
            Membership.status == Membership.STATUS_ACTIVE,
            Role.tenant_id == tenant_id,
            Role.is_system.is_(True),
        )
    ) or 0


def _has_system_role(db: Session, membership_id: UUID, tenant_id: UUID) -> bool:
    return (
        db.scalars(
            select(MembershipRole.role_id)
            .join(Role, Role.id == MembershipRole.role_id)
            .where(
                MembershipRole.membership_id == membership_id,
                Role.tenant_id == tenant_id,
                Role.is_system.is_(True),
            )
        ).first()
        is not None
    )


def _reject_last_tenant_admin(
    db: Session, membership: Membership, *, keeping_system: bool
) -> None:
    if keeping_system or not _has_system_role(
        db, membership.id, membership.tenant_id
    ):
        return
    if _tenant_admin_count(db, membership.tenant_id) <= 1:
        raise AppError(IamCode.LAST_TENANT_ADMIN, "不能撤销租户里最后一个租户管理员")


def _roles_in_tenant(
    db: Session, tenant_id: UUID, role_ids: Sequence[UUID]
) -> list[Role]:
    unique_ids = list(dict.fromkeys(role_ids))
    if not unique_ids:
        return []
    roles = list(
        db.scalars(
            select(Role).where(Role.id.in_(unique_ids), Role.tenant_id == tenant_id)
        ).all()
    )
    if len(roles) != len(unique_ids):
        raise AppError(BizCode.VALIDATION_ERROR, "角色不属于当前租户")
    by_id = {role.id: role for role in roles}
    return [by_id[role_id] for role_id in unique_ids]


def _replace_membership_roles(
    db: Session, membership: Membership, roles: Sequence[Role]
) -> None:
    keeping_system = any(role.is_system for role in roles)
    _reject_last_tenant_admin(db, membership, keeping_system=keeping_system)
    db.execute(
        delete(MembershipRole).where(
            MembershipRole.membership_id == membership.id
        )
    )
    for role in roles:
        db.add(
            MembershipRole(
                membership_id=membership.id,
                role_id=role.id,
                tenant_id=membership.tenant_id,
            )
        )
    db.flush()


def _role_ids_of(db: Session, membership_id: UUID) -> list[UUID]:
    return list(
        db.scalars(
            select(MembershipRole.role_id).where(
                MembershipRole.membership_id == membership_id
            )
        )
    )


def _member_snapshot(db: Session, membership: Membership) -> dict[str, Any]:
    return {
        "user_id": str(membership.user_id),
        "status": membership.status,
        "role_ids": [str(role_id) for role_id in _role_ids_of(db, membership.id)],
    }


def _member_read(db: Session, membership: Membership) -> MemberRead:
    user = db.get(User, membership.user_id)
    if user is None:
        raise AppError(IamCode.MEMBER_NOT_FOUND, "成员不存在")
    roles = list(
        db.scalars(
            select(Role)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(MembershipRole.membership_id == membership.id)
            .order_by(Role.code.asc())
        ).all()
    )
    return MemberRead(
        id=membership.id,
        tenant_id=membership.tenant_id,
        user=UserProfile.model_validate(user),
        roles=[RoleSummary.model_validate(role) for role in roles],
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def list_members(
    db: Session, user: CurrentUser, pagination: Pagination
) -> PageResult[MemberRead]:
    conditions = [
        Membership.tenant_id == user.tenant_id,
        Membership.status == Membership.STATUS_ACTIVE,
    ]
    total = (
        db.scalar(select(func.count()).select_from(Membership).where(*conditions)) or 0
    )
    rows = db.scalars(
        select(Membership)
        .where(*conditions)
        .order_by(Membership.created_at.asc(), Membership.id.asc())
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    return PageResult(
        items=[_member_read(db, membership) for membership in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


def create_member(
    db: Session, user: CurrentUser, payload: MemberCreate
) -> MemberRead:
    target = get_or_create_user(
        db,
        UserCreate(email=payload.email, display_name=payload.display_name),
    )
    existing = db.scalars(
        select(Membership).where(
            Membership.user_id == target.id,
            Membership.tenant_id == user.tenant_id,
            Membership.status == Membership.STATUS_ACTIVE,
        )
    ).first()
    if existing is not None:
        raise AppError(IamCode.MEMBER_CONFLICT, "该用户已在本租户中")
    membership = get_or_create_membership(
        db, user_id=target.id, tenant_id=user.tenant_id
    )
    roles = _roles_in_tenant(db, user.tenant_id, payload.role_ids)
    _replace_membership_roles(db, membership, roles)
    record_audit(
        db,
        user=user,
        action="create",
        resource_type=RESOURCE_MEMBER,
        resource_id=membership.id,
        after=_member_snapshot(db, membership),
    )
    return _member_read(db, membership)


def delete_member(db: Session, user: CurrentUser, membership_id: UUID) -> None:
    membership = _get_membership(db, user, membership_id)
    _reject_last_tenant_admin(db, membership, keeping_system=False)
    before = _member_snapshot(db, membership)
    db.execute(
        delete(MembershipRole).where(MembershipRole.membership_id == membership.id)
    )
    membership.status = Membership.STATUS_DISABLED
    db.flush()
    record_audit(
        db,
        user=user,
        action="delete",
        resource_type=RESOURCE_MEMBER,
        resource_id=membership.id,
        before=before,
        after=_member_snapshot(db, membership),
    )


def replace_member_roles(
    db: Session,
    user: CurrentUser,
    membership_id: UUID,
    role_ids: Sequence[UUID],
) -> MemberRead:
    membership = _get_membership(db, user, membership_id)
    before = _member_snapshot(db, membership)
    roles = _roles_in_tenant(db, user.tenant_id, role_ids)
    _replace_membership_roles(db, membership, roles)
    record_audit(
        db,
        user=user,
        action="update",
        resource_type=RESOURCE_MEMBER,
        resource_id=membership.id,
        before=before,
        after=_member_snapshot(db, membership),
    )
    return _member_read(db, membership)
