from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.projects.models import Project
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectQuery,
    ProjectRead,
    ProjectUpdate,
)


def _get_active(db: Session, project_id: UUID) -> Project:
    project = db.scalars(
        select(Project).where(
            Project.id == project_id,
            Project.deleted_at.is_(None),
        )
    ).first()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
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
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project name already exists",
        ) from exc
    return ProjectRead.model_validate(project)


def update_project(
    db: Session, project_id: UUID, payload: ProjectUpdate
) -> ProjectRead:
    project = _get_active(db, project_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(project, field, value)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project name already exists",
        ) from exc
    return ProjectRead.model_validate(project)


def delete_project(db: Session, project_id: UUID) -> None:
    project = _get_active(db, project_id)
    project.deleted_at = datetime.now(UTC)
    db.flush()
