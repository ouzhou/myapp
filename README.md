# myapp

A project created with FastAPI CLI.

## Quick Start

### Start Postgres

```bash
docker compose up -d
uv run alembic upgrade head
```

### Start the development server

```bash
uv run fastapi dev
```

Visit http://localhost:8000/docs

Health: `GET /api/v1/health`（会 `SELECT 1` 探数据库）

数据库 GUI（类似 Prisma Studio）：http://localhost:8080  
用 [pgweb](https://github.com/sosedoff/pgweb) 自动连上本地 Postgres，打开即可看表。

## Project Structure

- `app/main.py` - FastAPI 工厂与入口
- `app/db/` - engine、Session、DeclarativeBase
- `compose.yml` - 本地 Postgres + pgweb
- `alembic/` - 数据库迁移
- `pyproject.toml` - 依赖与 `[tool.fastapi] entrypoint`

## Learn More

- [FastAPI Documentation](https://fastapi.tiangolo.com)
- [FastAPI Cloud](https://fastapicloud.com)
