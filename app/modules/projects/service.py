from datetime import UTC, datetime
from enum import IntEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError, register_constraint_error
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


def list_projects(db: Session, query: ProjectQuery) -> list[ProjectRead]:
    stmt = select(Project).where(Project.deleted_at.is_(None))
    if query.q is not None:
        stmt = stmt.where(Project.name.ilike(f"%{query.q}%"))
    stmt = stmt.order_by(Project.created_at.desc())
    return [ProjectRead.model_validate(row) for row in db.scalars(stmt)]


def get_project(db: Session, project_id: UUID) -> ProjectRead:
    return ProjectRead.model_validate(_get_active(db, project_id))


def create_project(db: Session, payload: ProjectCreate) -> ProjectRead:
    project = Project(
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    db.add(project)
    db.flush()
    return ProjectRead.model_validate(project)


def update_project(
    db: Session, project_id: UUID, payload: ProjectUpdate
) -> ProjectRead:
    project = _get_active(db, project_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    db.flush()
    return ProjectRead.model_validate(project)


def delete_project(db: Session, project_id: UUID) -> None:
    project = _get_active(db, project_id)
    project.deleted_at = datetime.now(UTC)
    db.flush()
