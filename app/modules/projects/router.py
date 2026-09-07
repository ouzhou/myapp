from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.response import Envelope, ErrorEnvelope, PageResult, PaginationParams, ok
from app.db.session import get_db
from app.modules.projects import service as project_service
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectQuery,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}


@router.get("/")
def list_projects(
    db: Annotated[Session, Depends(get_db)],
    pagination: PaginationParams,
    query: Annotated[ProjectQuery, Query()],
) -> Envelope[PageResult[ProjectRead]]:
    return ok(project_service.list_projects(db, query, pagination))


@router.post("/", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
def create_project(
    payload: ProjectCreate,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[ProjectRead]:
    return ok(project_service.create_project(db, payload))


@router.get("/{project_id}", responses=NOT_FOUND)
def get_project(
    project_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[ProjectRead]:
    return ok(project_service.get_project(db, project_id))


@router.patch("/{project_id}", responses=NOT_FOUND | CONFLICT)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Annotated[Session, Depends(get_db)],
) -> Envelope[ProjectRead]:
    return ok(project_service.update_project(db, project_id, payload))


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND,
)
def delete_project(
    project_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    project_service.delete_project(db, project_id)
