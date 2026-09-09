from fastapi import APIRouter

from app.modules.health.router import router as health_router
from app.modules.iam.router import router as iam_router
from app.modules.projects.router import router as projects_router
from app.modules.tenants.router import router as tenants_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(projects_router)
api_router.include_router(users_router)
api_router.include_router(iam_router)
api_router.include_router(tenants_router)
