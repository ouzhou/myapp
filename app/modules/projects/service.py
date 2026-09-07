from datetime import UTC, datetime
from enum import IntEnum
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import CurrentUser
from app.core.exceptions import AppError, register_constraint_error
from app.core.response import PageResult, Pagination
from app.modules.projects.models import Project
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectQuery,
    ProjectRead,
    ProjectUpdate,
)


class ProjectCode(IntEnum):
    """projects 的专属业务码。资源序号 01，编码规则见 core/exceptions.py。"""

    NOT_FOUND = 40401
    NAME_CONFLICT = 40901


# 约束名跟 models.py 里 __table_args__ 的 Index 同名，改一处要改两处。
register_constraint_error(
    "uq_projects_name_active",
    ProjectCode.NAME_CONFLICT,
    "项目名称已存在",
)


def _get_active(db: Session, project_id: UUID) -> Project:
    project = db.scalars(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
        )
    ).first()
    if project is None:
        raise AppError(ProjectCode.NOT_FOUND, "项目不存在")
    return project


_SORT_COLUMNS = {
    "created_at": Project.created_at,
    "name": Project.name,
}


def list_projects(
    db: Session,
    user: CurrentUser,
    query: ProjectQuery,
    pagination: Pagination,
) -> PageResult[ProjectRead]:
    conditions = [Project.deleted_at.is_(None)]
    if query.q:
        conditions.append(Project.name.ilike(f"%{query.q}%"))
    column = _SORT_COLUMNS[query.sort]
    order_by = column.asc() if query.order == "asc" else column.desc()
    total = db.scalar(select(func.count()).select_from(Project).where(*conditions)) or 0
    rows = db.scalars(
        select(Project)
        .where(*conditions)
        .order_by(order_by)
        .offset((pagination.page - 1) * pagination.page_size)
        .limit(pagination.page_size)
    )
    return PageResult(
        items=[ProjectRead.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


def get_project(db: Session, user: CurrentUser, project_id: UUID) -> ProjectRead:
    return ProjectRead.model_validate(_get_active(db, project_id))


def create_project(
    db: Session, user: CurrentUser, payload: ProjectCreate
) -> ProjectRead:
    project = Project(
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    db.add(project)
    db.flush()
    return ProjectRead.model_validate(project)


def update_project(
    db: Session, user: CurrentUser, project_id: UUID, payload: ProjectUpdate
) -> ProjectRead:
    project = _get_active(db, project_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    db.flush()
    return ProjectRead.model_validate(project)


def delete_project(db: Session, user: CurrentUser, project_id: UUID) -> None:
    project = _get_active(db, project_id)
    project.deleted_at = datetime.now(UTC)
    db.flush()
