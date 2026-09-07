# 项目结构

参考仓库在 [full-stack-fastapi-template](./full-stack-fastapi-template)（官方 FastAPI 全栈模板的克隆）。本文只分析它的 **backend/app**，再给出本项目要用的结构。

和另外两份文档的分工：

- [01-fastapi-learning-path.md](./01-fastapi-learning-path.md)：按什么顺序写代码
- [02-full-project-features.md](./02-full-project-features.md)：完整项目有哪些功能
- 本文件：文件放哪、什么东西进哪个目录

---

## 1. 官方模板实际长什么样

```text
backend/app/
  main.py                 # 创建 FastAPI、CORS、挂路由
  models.py               # 所有表 + 所有 DTO（SQLModel）
  crud.py                 # 所有增删改查函数
  utils.py                # 发邮件等杂项
  initial_data.py         # 跑一遍 seed
  core/
    config.py             # pydantic-settings
    db.py                 # engine、init_db
    security.py           # JWT、密码哈希
  api/
    main.py               # 把各 router 汇总
    deps.py               # get_db、get_current_user、superuser
    routes/
      login.py
      users.py
      items.py
      private.py
      utils.py            # health / 测试邮件
  alembic/                # 迁移
```

请求怎么走：

```text
main.py
  → api/main.py（选 router）
    → api/routes/items.py（handler 里直接 session.add / commit）
      → api/deps.py（Session、CurrentUser）
      → models.py（表和入出参）
      → 少数操作再进 crud.py
```

它做对了三件对本项目仍有用的事：

1. **`core/` 只放和业务无关的底座**：配置、数据库引擎、密码和 JWT。
2. **`api/deps.py` 是注入缝**。`CurrentUser = Annotated[User, Depends(get_current_user)]` 就是 Nest 里 Guard + `@Req().user` 的 FastAPI 写法。下层拿用户，不解析 header。
3. **测试目录镜像路由**：`tests/api/routes/test_items.py` 对 `app/api/routes/items.py`。

它不适合直接当标注后台骨架，原因也很具体：

| 官方做法 | 问题 |
|---|---|
| 一个 `models.py` 装下 User、Item 和全部 DTO | 资源一多，文件不可读；SQLModel 还把表和 DTO 糊在一起 |
| 一个 `crud.py` | 标注域会有项目、数据集、任务、质检……函数会堆成一坨 |
| 业务写在 route 里 | `items.py` 自己查库、自己判断 owner、自己 commit。路由既当 Controller 又当 Service |
| 权限是 `is_superuser` 布尔 | 没有 Casbin，没有租户，没有资源级权限 |
| 没有统一错误信封 | 直接 `HTTPException(detail="...")` |
| 没有 service 层 | 跨表事务、审计、状态机没有落脚点 |

结论：学它的 **core + deps + 路由汇总**，不要学它的 **单文件 models/crud + 路由里写业务**。

---

## 2. 为什么不按 NestJS 1:1 建目录

Nest 的模块能成立，是因为有 DI 容器：`Module` 声明 providers，框架负责实例化和作用域。FastAPI 没有这套。

| Nest | FastAPI 里真实对应物 | 不要做的事 |
|---|---|---|
| `xxx.module.ts` | 一个目录 + 在总路由里 `include_router` | 不要写假 `Module` 类、不要自造容器 |
| `xxx.controller.ts` | `router.py` 里的 handler | 路由保持薄 |
| `xxx.service.ts` | `service.py` 里的函数或 class | 可以有，自己 new 或 `Depends` 组装 |
| `xxx.entity.ts` | `models.py`（SQLAlchemy） | 和 DTO 分开 |
| `dto/` | `schemas.py`（Pydantic） | 不要用 SQLModel 兼两职 |
| `Guard` | 会 `raise` 的 `Depends` | 不要返回 boolean |
| 请求作用域 provider | `yield` 的 `get_db()` | 不要每层自己 `Session()` |
| `APP_FILTER` | `exception_handler` | 挂在 `create_app()` |

可以借 Nest 的 **按业务分目录、路由薄、Entity ≠ DTO**。不要借它的模块元数据和装饰器体系。

---

## 3. 本项目采用的结构

按 **业务切片（module）** 分目录，按 **共享底座（core / db / deps）** 放横切能力。学习路径每一步往对应目录填文件，不要提前建空包。

```text
myapp/
  pyproject.toml
  alembic.ini
  alembic/
    env.py
    versions/
  tests/
    conftest.py
    api/
      test_health.py
      test_projects.py
  app/
    main.py                      # create_app()，只组装，不写业务
    deps.py                      # 全局 Depends：db、CurrentUser
    core/                        # 与「项目/任务」无关的协议和工具
      config.py
      exceptions.py
      response.py
      security.py                # JWT、密码；第 5 步先 stub
      permissions.py             # Casbin 封装
      context.py                 # CurrentUser 数据类型，可选 ContextVar
      logging.py
    db/
      session.py                 # engine、get_db
      base.py                    # DeclarativeBase、TimestampMixin、SoftDeleteMixin
    api/
      router.py                  # 只负责 include 各模块 router
    modules/
      health/
        router.py
      auth/                      # 登录，第 9 步才出现
        router.py
        schemas.py
        service.py
      users/
        router.py
        schemas.py
        models.py
        service.py
      projects/                  # 第 2 步的第一个资源
        router.py
        schemas.py
        models.py
        service.py
    infra/                       # 对外适配，业务模块只依赖它的接口
      casbin/
        enforcer.py
        model.conf
        policy.csv
      storage/
        local.py                 # 第 8 步
```

以后每加一个业务（数据集、任务、质检），只在 `modules/` 下加一个目录，四件套：`router / schemas / models / service`。不必再往 `core/` 里堆。

---

## 4. 每个目录放什么

### `app/main.py`

只做组装：

- `create_app()`
- `lifespan`（启动连库探活、关闭释放）
- 注册异常处理、CORS、以后的日志中间件
- `include_router(api_router)`

不写具体业务 handler。

### `app/core/`

放 **协议和机制**，不放「项目叫什么、任务怎么分配」。判断标准：删掉某个业务模块，这个文件仍然有意义。

| 文件 | 放什么 | 学习步骤 |
|---|---|---|
| `config.py` | 环境变量、Settings | 0 |
| `exceptions.py` | `AppError`、handler、409 映射 | 3 |
| `response.py` | 统一信封、`PageResult` | 3、4 |
| `security.py` | 密码、JWT；前期可先空着 | 5 → 9 |
| `permissions.py` | `require_perm("project", "write")` | 7 |
| `context.py` | `CurrentUser` 的数据结构 | 5 |
| `logging.py` | 结构化日志配置 | 10 |

### `app/db/`

和 SQLAlchemy 生命周期有关，和具体表无关。

| 文件 | 放什么 |
|---|---|
| `session.py` | engine、`get_db()` |
| `base.py` | `DeclarativeBase`、时间戳 mixin、软删 mixin |

具体表定义 **不进这里**，进各模块的 `models.py`。Alembic 的 `env.py` 再把用到的 model 导入一遍，否则自动生成迁移会漏表。

### `app/deps.py`

全局注入缝，对应官方模板的 `api/deps.py`，也对应 Nest 里你会挂到全局的 Guard / 请求对象。

这里只放跨模块都要用的：

- `DbSession`（`Annotated[Session, Depends(get_db)]`）
- `CurrentUserDep`（第 5 步读 header，第 9 步改成读 JWT）
- 可选：`RequestIdDep`

某个模块自己的依赖（例如「必须是项目成员」）写在该模块里，例如 `modules/projects/deps.py`，不要塞进全局。

### `app/api/router.py`

对应官方 `api/main.py`。只做：

```text
api_router.include_router(health.router)
api_router.include_router(projects.router)
...
```

不写 handler。URL 前缀、tags 由各模块自己的 `APIRouter` 声明。

### `app/modules/<name>/`

一个业务切片。文件职责固定：

| 文件 | 职责 | 可以依赖 | 不可以做 |
|---|---|---|---|
| `router.py` | 路径、入参、调 service、返回信封 | schemas、service、deps | 写 SQL、开事务细节、拼 Casbin 策略 |
| `schemas.py` | Pydantic DTO：Create / Update / Read / Query | 无业务、无 ORM | 继承 SQLAlchemy model |
| `models.py` | SQLAlchemy 表 | `db.base` 的 mixin | 被 router 直接返回 |
| `service.py` | 业务规则、事务、调审计/权限 | models、DbSession、CurrentUser | 解析 JWT、读原始 header |
| `deps.py`（可选） | 本模块守卫，如「项目成员」 | 全局 deps | 变成第二个 service |

没有 `repository.py` 也可以。查询先写在 service 里。等同一个表的查询出现三处以上、或租户条件开始复制，再抽 `repository.py`。不要为了「像 Nest」提前加一层空转发。

### `app/infra/`

外部系统的适配：Casbin 文件、本地磁盘、以后的 S3、邮件。  
模块的 service 可以调用 `infra`，`infra` 不准反向 import `modules`。

Seed 数据（管理员、策略）可以放 `app/db/seeds.py` 或 `scripts/seed.py`，由第 7 步的命令触发，不要写在 `main.py` 里每次启动都隐式跑复杂逻辑（官方模板在 `init_db` 里只确保有一个超管，这种「最小保证」可以留）。

### `alembic/` 和 `tests/`

- 迁移放仓库根下的 `alembic/`，不要学官方塞进 `app/alembic/`。根目录更常见，和 `alembic.ini` 好找。
- 测试按接口镜像：`tests/api/test_projects.py`。测的是「HTTP 契约 + 租户隔离」，不要去单测每个 SQL 细节。

---

## 5. 一个请求在本结构里怎么走

以「更新标注项目」为例，对应学习路径第 5 步之后：

```text
HTTP PUT /api/v1/projects/{id}
  app/main.py                         组装好的 app
  app/api/router.py                   转到 projects.router
  modules/projects/router.py          校验 Update DTO，注入 CurrentUser / DbSession
  modules/projects/service.py         租户条件查行、改字段、写审计、commit
  modules/projects/models.py          表结构
  modules/projects/schemas.py         返回 Read DTO，不返回 Entity
  core/response.py                    包成信封
```

失败时：

```text
service 抛 AppError
  → core/exceptions.py 的 handler
    → 同一张信封，带 request_id
```

权限（第 7 步之后）：

```text
router 上 Depends(require_perm("project", "write"))
  → core/permissions.py
    → infra/casbin
```

JWT（第 9 步）只改 `app/deps.py` 里 CurrentUser 的实现。上面这条链不用动。

---

## 6. 新代码往哪放（决策表）

拿不准时按这一张表，不要开新的顶层目录。

| 你要写的东西 | 放这里 |
|---|---|
| 环境变量、开关 | `core/config.py` |
| 成功/失败的 JSON 形状 | `core/response.py` |
| 业务错误类型、HTTP 映射 | `core/exceptions.py` |
| 当前用户长什么样 | `core/context.py` |
| 解析 JWT / 读假 header | `app/deps.py` + `core/security.py` |
| Casbin 怎么问 | `core/permissions.py` + `infra/casbin/` |
| 时间戳、软删字段 | `db/base.py` 的 mixin |
| 一张新表 | `modules/<领域>/models.py` |
| 这张表的入出参 | 同模块 `schemas.py` |
| 状态机、跨表写、审计调用 | 同模块 `service.py` |
| HTTP 路径 | 同模块 `router.py` |
| 「必须是项目成员」 | 同模块 `deps.py` |
| 磁盘 / S3 / 邮件 | `infra/` |
| 数据库版本 | `alembic/versions/` |
| 接口契约测试 | `tests/api/` |

出现这些信号再拆，而不是提前拆：

- `service.py` 超过一个屏幕且有两坨不相干规则 → 拆函数或拆子模块，不要先加 repository
- 三个模块都在复制「按 tenant_id 过滤」→ 抽到 `db/` 的查询辅助，仍不要建空泛型 Repository 框架
- 上传既被项目用又被数据集用 → 独立 `modules/files/`，不要继续塞在 projects 里

---

## 7. 和官方模板、Nest 的对照（最终选型）

| 能力 | 官方模板 | Nest 常见 | 本项目 |
|---|---|---|---|
| 组织方式 | 按技术层，全局单文件 | 按模块 | **按模块目录，但无 Module 类** |
| DTO | SQLModel，和表继承同一套 | class-validator DTO | **Pydantic，独立 schemas.py** |
| 表 | SQLModel `table=True` | TypeORM Entity | **SQLAlchemy 2.0 models.py** |
| 业务 | 写在 route / crud | Service | **service.py** |
| 注入 | `deps.py` | 容器 + Guard | **deps.py + Depends** |
| 权限 | `is_superuser` | Guard / Casbin | **Depends + Casbin（后做）** |
| 返回 | 模型或 `Message` | Interceptor 信封 | **core/response.py** |
| 错误 | `HTTPException` | ExceptionFilter | **core/exceptions.py** |

一句话：官方模板教你 FastAPI 的组装方式；Nest 教你按业务切开；本项目把两样合在「模块目录 + 全局 deps/core」，不引入第三套框架。

---

## 8. 按学习路径长出来的顺序

不要第一天把上面的树建满。空目录没有教学价值。

| 步骤 | 新建或改动 |
|---|---|
| 0 | `app/main.py`、`core/config.py`、`modules/health/router.py`、`api/router.py` |
| 1 | `db/session.py`、`db/base.py`、`alembic/` |
| 2 | `modules/projects/{router,schemas,models,service}.py` |
| 3 | `core/exceptions.py`、`core/response.py` |
| 4 | `PageResult` 放进 `core/response.py`，Query DTO 放进模块 schemas |
| 5 | `core/context.py`、`app/deps.py` |
| 6 | 项目 model 加 `tenant_id`，过滤写进 service |
| 6.5 | `modules/audit/`（只要 model + 一个写入函数即可） |
| 7 | `infra/casbin/`、`core/permissions.py`、seed |
| 7.5 | `modules/users/` |
| 8 | `infra/storage/`、`modules/files/` |
| 8.5 | 仍在已有 service 里开事务，不新目录 |
| 9 | `modules/auth/`，改 `deps.py` |
| 10 | `core/logging.py` |

这样目录是学出来的，不是抄出来的。
