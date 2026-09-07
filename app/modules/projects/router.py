from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.projects import service as project_service
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectQuery,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("/")
def list_projects(
    db: Annotated[Session, Depends(get_db)],
    q: Annotated[str | None, Query()] = None,
) -> list[ProjectRead]:
    return project_service.list_projects(db, ProjectQuery(q=q))


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    return project_service.create_project(db, payload)


@router.get("/{project_id}")
def get_project(
    project_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    return project_service.get_project(db, project_id)


@router.patch("/{project_id}")
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> ProjectRead:
    return project_service.update_project(db, project_id, payload)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    project_service.delete_project(db, project_id)
