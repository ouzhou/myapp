from fastapi import APIRouter

# 租户管理接口第 10 步才做。这一步只建表，路由先占位、不挂到 api/router。
router = APIRouter(prefix="/tenants", tags=["tenants"])
