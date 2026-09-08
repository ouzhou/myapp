# 项目结构

参考仓库在 [full-stack-fastapi-template](./full-stack-fastapi-template)（官方 FastAPI 全栈模板的克隆，只作参考，不进版本控制）。本文先分析它的 **backend/app**，再给出本项目要用的结构。

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

它做对了四件对本项目仍有用的事：

1. **`core/` 只放和业务无关的底座**：配置、数据库引擎、密码和 JWT。
2. **`api/deps.py` 是注入缝**。`CurrentUser = Annotated[User, Depends(get_current_user)]` 就是 Nest 里 Guard + `@Req().user` 的 FastAPI 写法。下层拿用户，不解析 header。
3. **测试目录镜像路由**：`tests/api/routes/test_items.py` 对 `app/api/routes/items.py`。
4. **仓库根有完整的交付物**：`Dockerfile`、`compose.yml`、`scripts/`、CI。这部分值得照抄结构。

它不适合直接当标注后台骨架，原因也很具体：

| 官方做法 | 问题 |
|---|---|
| 一个 `models.py` 装下 User、Item 和全部 DTO | 资源一多，文件不可读；SQLModel 还把表和 DTO 糊在一起 |
| 一个 `crud.py` | 标注域会有项目、数据集、任务、质检……函数会堆成一坨 |
| 业务写在 route 里 | `items.py` 自己查库、自己判断 owner、自己 commit。路由既当 Controller 又当 Service |
| 权限是 `is_superuser` 布尔 | 没有角色、没有租户、没有资源级权限 |
| 没有统一错误信封 | 直接 `HTTPException(detail="...")` |
| 没有 service 层 | 跨表事务、审计、状态机没有落脚点 |
| `init_db` 里 `create_all` 兜底 | 模型和迁移会漂移。本项目只走 Alembic |

结论：学它的 **core + deps + 路由汇总 + 交付物布局**，不要学它的 **单文件 models/crud + 路由里写业务**。

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
| `APP_INTERCEPTOR` | 中间件或返回类型注解 | 不要自造拦截器链 |

可以借 Nest 的 **按业务分目录、路由薄、Entity ≠ DTO**。不要借它的模块元数据和装饰器体系。

---

## 3. 本项目采用的结构

按 **业务切片（module）** 分目录，按 **共享底座（core / db / deps）** 放横切能力。学习路径每一步往对应目录填文件，不要提前建空包。

```text
myapp/
  pyproject.toml               # 依赖 + [tool.fastapi] entrypoint + ruff/mypy/pytest 配置
  compose.yml                  # 第 1 步只有 postgres，第 16 步补 api
  Dockerfile                   # 第 16 步
  .dockerignore
  .env.example                 # 只有键名和假值，真值在 gitignore 掉的 .env
  alembic.ini
  alembic/
    env.py                     # 从 Settings 读连接串，import 所有 model
    versions/
  scripts/
    seed.py                    # 幂等，可重复跑
  tests/
    conftest.py                # engine / db_session / client / auth_client
    api/
      test_health.py
      test_projects.py
      test_tenant_isolation.py
      test_me.py               # 第 9 步：多租户、切租户、非成员 403
      test_permissions.py      # 第 10 步：401 / 403 / 自定义角色即时生效
  app/
    main.py                    # create_app()，只组装，不写业务
    deps.py                    # 全局 Depends：DbSession、CurrentUserDep（人 + 租户 + 权限）
    core/                      # 与「项目/任务」无关的协议和工具
      config.py
      exceptions.py            # AppError、业务码编码规则、通用码、handler
      response.py              # Envelope[T]、PageResult[T]
      middleware.py            # request_id、安全头、限流
      security.py              # 验 Logto 的 token（JWKS）；第 14 步才有内容
      permissions.py           # 权限点枚举 + require_perm 依赖
      context.py               # CurrentUser 数据类型 + ContextVar
      logging.py
    db/
      session.py               # engine、sessionmaker、get_db
      base.py                  # DeclarativeBase + naming_convention、TimestampMixin、SoftDeleteMixin
    api/
      router.py                # 只负责 include 各模块 router
    modules/
      health/
        router.py
      projects/                # 第 2 步的第一个资源
        router.py
        schemas.py
        models.py
        service.py
      audit/                   # 第 8 步，只有 model + 写入函数
        models.py
        service.py
      tenants/                 # 第 9 步；tenants 表
        router.py
        schemas.py
        models.py
        service.py
      users/                   # 第 9 步；users + memberships 表，/me 也在这里
        router.py
        schemas.py
        models.py
        service.py
      iam/                     # 第 10 步；roles / role_permissions / membership_roles
        router.py              #   + 成员管理和授角色的接口
        schemas.py
        models.py
        service.py
      files/                   # 第 11 步
        router.py
        schemas.py
        models.py
        service.py
    infra/                     # 对外适配，业务模块只依赖它的接口
      storage/
        local.py               # 第 11 步
  .github/
    workflows/
      ci.yml                   # 第 16 步
```

授权没有 `infra/` 下的目录，因为它不是外部系统：权限就是 `modules/iam/` 里的几张表，`core/permissions.py` 只放权限点枚举和那个依赖。

以后每加一个业务（数据集、任务、质检），只在 `modules/` 下加一个目录，四件套：`router / schemas / models / service`。不必再往 `core/` 里堆。

---

## 4. 每个目录放什么

### 仓库根

`Dockerfile`、`compose.yml`、`.env.example`、`alembic.ini`、`pyproject.toml` 都在根，不要塞进 `app/`。`app/` 是 Python 包，运维文件不是包的一部分。

`pyproject.toml` 里除了依赖，还统一放工具配置：

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

有了它，`uv run fastapi dev` 不用带路径。同时**不要**在仓库根留一个示例 `main.py`，否则 CLI 会去发现它。

### `app/main.py`

只做组装：

- `create_app()`
- 模块级 `app = create_app()`（CLI 和 uvicorn 需要一个可导入的对象）
- `lifespan`：启动时初始化日志，关闭时 `engine.dispose()`
- 注册异常处理、CORS、中间件
- `include_router(api_router, prefix="/api/v1")`

不写具体业务 handler。

### `app/core/`

放 **协议和机制**，不放「项目叫什么、任务怎么分配」。判断标准：删掉某个业务模块，这个文件仍然有意义。

| 文件 | 放什么 | 学习步骤 |
|---|---|---|
| `config.py` | 环境变量、Settings、prod 启动断言 | 0、15 |
| `exceptions.py` | `AppError`、业务码编码规则、通用码枚举、handler、约束名注册表 | 4 |
| `response.py` | `Envelope[T]`、`PageResult[T]`、分页参数依赖 | 4、5 |
| `middleware.py` | request_id、安全头、限流 | 4、15 |
| `context.py` | `CurrentUser` 的数据结构 + ContextVar | 6 |
| `permissions.py` | 权限点枚举 + `require_perm(Perm.PROJECT_WRITE)` | 10 |
| `logging.py` | 结构化日志配置 | 13 |
| `security.py` | JWKS 客户端、校验 Logto 发的 token（**不含**密码哈希，也不含签发 token） | 14 |

`security.py` 在第 14 步之前**不要提前建空文件**。它是「验别人发的证」，不是「自己发证」：本项目认证走 Logto，仓库里没有密码列、没有登录接口，也就没有 `modules/auth/` 这个目录。`/me` 归 `modules/users/`。

业务码分两层，别让它变成一个所有模块都要来改一笔的 god enum：

- `core/exceptions.py` 定**编码规则**（`http_status_of` / `biz_code_of` 互为逆运算）和 core 自己抛的通用码（校验 422、未知 500）
- **模块专属码定义在该模块的 `service.py`**，例如 `ProjectCode.NOT_FOUND = 40401`（资源序号 01）
- 唯一约束冲突的 409 文案由模块调 `register_constraint_error(约束名, 码, 文案)` 登记；core 不认识「项目名称」这种业务词

判断标准还是那句：删掉 projects 模块，`core/exceptions.py` 应该照样编译得过。

### `app/db/`

和 SQLAlchemy 生命周期有关，和具体表无关。

| 文件 | 放什么 |
|---|---|
| `session.py` | engine（含连接池参数）、`sessionmaker`、`get_db()` |
| `base.py` | `DeclarativeBase` + `MetaData(naming_convention=...)`、时间戳 mixin、软删 mixin |

具体表定义 **不进这里**，进各模块的 `models.py`。

`alembic/env.py` 要把所有用到的 model 导入一遍，否则 autogenerate 会漏表、甚至生成 `drop_table`。最省事的做法是在 `env.py` 里显式 import 每个模块的 `models`（加新模块时记得加一行），不要依赖「反正某处 import 过」。

### `app/deps.py`

全局注入缝，对应官方模板的 `api/deps.py`，也对应 Nest 里你会挂到全局的 Guard / 请求对象。

这里只放跨模块都要用的：

- `DbSession = Annotated[Session, Depends(get_db)]`
- `CurrentUserDep`：装配 `CurrentUser`，一共三件事
  1. **认到人**：第 6 步读 `X-User-Id`，第 14 步改成「验 Bearer token + 查 `users.idp_subject` 映射」
  2. **定租户**：`X-Tenant-Id` → `last_selected_tenant_id` → 最早的 membership，每一级都要校验成员关系（第 9 步）
  3. **算权限**：按 `membership_id` join 出权限点集合（第 10 步）
- 可选：`RequestIdDep`

**这三件事必须都在这一个文件里**，别让业务模块自己去查成员关系或权限——那样每加一个模块就多一处可能漏 `tenant_id` 的地方，而那正是多租户系统最常见的越权 bug。

某个模块自己的依赖（例如「必须是项目成员」）写在该模块里，例如 `modules/projects/deps.py`，不要塞进全局。

### `app/api/router.py`

对应官方 `api/main.py`。只做：

```text
api_router.include_router(health.router)
api_router.include_router(projects.router)
...
```

不写 handler。URL 前缀、tags、路由级 `dependencies` 由各模块自己的 `APIRouter` 声明；只有 `/api/v1` 这个全局前缀在 `main.py` 上加。

### `app/modules/<name>/`

一个业务切片。文件职责固定：

| 文件 | 职责 | 可以依赖 | 不可以做 |
|---|---|---|---|
| `router.py` | 路径、入参、调 service、声明 `Envelope[...]` 返回类型 | schemas、service、deps | 写 SQL、`commit`、自己查权限表 |
| `schemas.py` | Pydantic DTO：Create / Update / Read / Query | 无业务、无 ORM | 继承 SQLAlchemy model |
| `models.py` | SQLAlchemy 表 | `db.base` 的 mixin | 被 router 直接返回 |
| `service.py` | 业务规则、租户条件、事务、本模块业务码、调审计/权限 | models、DbSession、CurrentUser | 解析 JWT、读原始 header、各自 `commit` |
| `deps.py`（可选） | 本模块守卫，如「项目成员」 | 全局 deps | 变成第二个 service |

没有 `repository.py` 也可以。查询先写在 service 里。等同一个表的查询出现三处以上、或租户条件开始复制，再抽 `repository.py`。不要为了「像 Nest」提前加一层空转发。

`commit` 只在一个地方发生（`get_db` 依赖的收尾或 service 入口函数）。service 内部只 `flush`。这一条比目录结构重要——到处 `commit` 会让第 12 步的事务直接失效。

### `app/infra/`

外部系统的适配：本地磁盘、以后的 S3、邮件。
模块的 service 可以调用 `infra`，`infra` 不准反向 import `modules`。

`storage/local.py` 先把接口定成 `save / open / delete` 三个函数。第 11 步只有本地实现，以后加 S3 时业务代码不用改。

**权限不进 `infra/`。** 它不是外部系统，就是 `modules/iam/` 里的几张自己的表。

### `scripts/` 和 seed

Seed（租户、用户、成员、系统角色）放 `scripts/seed.py`，由命令触发，不要写在 `main.py` 里每次启动隐式跑。

Seed 必须**幂等**：跑两次不报错、不产生重复数据。用「查不到才建」而不是无条件 insert。

### `alembic/` 和 `tests/`

- 迁移放仓库根下的 `alembic/`，不要学官方塞进 `app/alembic/`。根目录更常见，和 `alembic.ini` 好找。
- 测试按接口镜像：`tests/api/test_projects.py`。测的是「HTTP 契约 + 租户隔离 + 权限 + 事务」，不要去单测每个 SQL 细节。

`tests/conftest.py` 的四个 fixture 是整个测试体系的地基：

| fixture | 作用域 | 做什么 |
|---|---|---|
| `engine` | session | 指向独立测试库，跑一次 `alembic upgrade head` |
| `db_session` | function | 开外层事务并绑 session，测完 `rollback`，保证测试间干净 |
| `client` | function | `TestClient` + `app.dependency_overrides[get_db]` 指向 `db_session` |
| `auth_client` | function | 造身份。第 6 步只塞 header；第 9 步起要先造出真的 `users` / `tenants` / `memberships` 行（第 10 步再加角色和权限），再塞 header；第 14 步改成用自签 RSA 密钥造一个「长得像 Logto」的 token 并把取公钥那一处 override 掉——**接 Logto 时只改这一个 fixture，测试不连真 Logto** |

测试库和开发库分开，用单独的环境变量（例如 `TEST_DATABASE_URL`）。绝对不要让测试跑在开发库上。

---

## 5. 一个请求在本结构里怎么走

以「更新标注项目」为例，对应学习路径第 10 步之后：

```text
HTTP PATCH /api/v1/projects/{id}
  app/main.py                         组装好的 app、中间件（request_id）
  app/api/router.py                   转到 projects.router
  modules/projects/router.py          校验 Update DTO，注入 CurrentUser / DbSession
                                      路由上 Depends(require_perm(Perm.PROJECT_WRITE))
  modules/projects/service.py         租户条件查行、改字段、写审计
  modules/projects/models.py          表结构
  modules/projects/schemas.py         转成 Read DTO，不返回 Entity
  core/response.py                    包成 Envelope[ProjectRead]
  get_db 收尾                          commit
```

失败时：

```text
service 抛 AppError
  → core/exceptions.py 的 handler
    → 同一张信封 + 真 HTTP 状态码，带 request_id
  → get_db 收尾 rollback
```

身份、租户、权限都在进 router 之前就定好了（第 9–10 步之后）：

```text
Depends(CurrentUserDep) → app/deps.py
  1 认到人      X-User-Id（第 6 步）或 Bearer token → users.idp_subject（第 14 步）
  2 定租户      X-Tenant-Id → last_selected_tenant_id → 最早的 membership
                每一级都查 memberships 校验，非成员 403
  3 算权限      membership_roles ⋈ role_permissions → permissions 集合（一次 join）

router 上 Depends(require_perm(Perm.PROJECT_WRITE))
  → core/permissions.py            权限点是这里的枚举，不是字符串
    → 判断它在不在 CurrentUser.permissions 里，不在就 403
```

第 3 步的 join 是**每个请求一次、只查这一个人在这一个租户的权限**，几十行。所以改一个人的角色、改一个角色的权限，下一个请求就生效——没有进程内缓存要刷新，也没有多 worker 不一致的问题。

租户在这条链上只负责「你是不是成员」；「你能不能看见这一行数据」是另一件事，在 service 的查询条件里，跨租户查不到就是 404。两个 403/404 的分工：**非成员 403（你进不来这个租户），跨租户 404（这个租户里没这条数据）**。

接 Logto（第 14 步）只改上面第 1 步。第 2、3 步和整条业务链一行不动。

---

## 6. 新代码往哪放（决策表）

拿不准时按这一张表，不要开新的顶层目录。

| 你要写的东西 | 放这里 |
|---|---|
| 环境变量、开关、prod 启动断言 | `core/config.py` |
| 成功/失败的 JSON 形状、分页壳 | `core/response.py` |
| `AppError`、业务码编码规则、通用码 | `core/exceptions.py` |
| 某个模块专属的业务码和 409 文案 | 该模块的 `service.py` |
| request_id / 安全头 / 限流 | `core/middleware.py` |
| 当前用户长什么样 | `core/context.py` |
| 验 Logto 的 token / 读假 header | `app/deps.py` + `core/security.py` |
| IdP 用户 → 本地用户的映射和建人 | `modules/users/service.py` |
| 「当前租户是哪个」的解析和成员校验 | `app/deps.py`（只有这一处） |
| 权限点清单、`require_perm` | `core/permissions.py` |
| 角色、角色的权限、给谁授了什么角色 | `modules/iam/`（表 + 管理接口） |
| 日志格式和上下文绑定 | `core/logging.py` |
| 时间戳、软删字段、约束命名 | `db/base.py` |
| engine、连接池、`get_db` | `db/session.py` |
| 一张新表 | `modules/<领域>/models.py` |
| 这张表的入出参 | 同模块 `schemas.py` |
| 状态机、跨表写、租户条件、审计调用 | 同模块 `service.py` |
| HTTP 路径 | 同模块 `router.py` |
| 「必须是项目成员」 | 同模块 `deps.py` |
| 磁盘 / S3 / 邮件 | `infra/` |
| 数据库版本 | `alembic/versions/` |
| 初始数据 | `scripts/seed.py` |
| 接口契约测试 | `tests/api/` |
| 镜像、编排、CI | 仓库根 + `.github/workflows/` |

出现这些信号再拆，而不是提前拆：

- `service.py` 超过一个屏幕且有两坨不相干规则 → 拆函数或拆子模块，不要先加 repository
- 三个模块都在复制「按 tenant_id 过滤」→ 抽到 `db/` 的查询辅助，仍不要建空泛型 Repository 框架
- 上传既被项目用又被数据集用 → 独立 `modules/files/`，不要继续塞在 projects 里
- 同一个权限判断在五个路由上重复 → 抽成模块 `deps.py` 里的一个依赖
- 权限开始跟「关系」有关（只有项目成员能看它的任务）→ 那才是引入策略引擎的时机，换 `core/permissions.py` 背后的实现，路由不动

---

## 7. 和官方模板、Nest 的对照（最终选型）

| 能力 | 官方模板 | Nest 常见 | 本项目 |
|---|---|---|---|
| 组织方式 | 按技术层，全局单文件 | 按模块 | **按模块目录，但无 Module 类** |
| DTO | SQLModel，和表继承同一套 | class-validator DTO | **Pydantic，独立 schemas.py** |
| 表 | SQLModel `table=True` | TypeORM Entity | **SQLAlchemy 2.0 models.py** |
| 业务 | 写在 route / crud | Service | **service.py** |
| 注入 | `deps.py` | 容器 + Guard | **deps.py + Depends** |
| 权限 | `is_superuser` | Guard / Casbin | **`Depends(require_perm)` + 自己的 RBAC 表，租户内可自定义角色（第 10 步）** |
| 认证 | 自签 JWT + 密码哈希 | Passport JWT / 自建登录 | **Logto 发 token，只验签 + 查本地映射，无登录接口** |
| 租户 | 无 | 中间件 / CLS | **`X-Tenant-Id` + `memberships` 校验（第 9 步）+ service 查询条件 + 复合索引** |
| 用户与租户的关系 | 无 | 常见一对一 | **多对多 `memberships`，一个人能加入多个租户** |
| 返回 | 模型或 `Message` | Interceptor 信封 | **`Envelope[T]` in core/response.py** |
| 错误 | `HTTPException` | ExceptionFilter | **core/exceptions.py + 错误码枚举** |
| 建表 | `create_all` 兜底 | migration | **只走 Alembic** |
| 测试 | TestClient + 真库 | Jest + supertest | **pytest + TestClient + 事务回滚** |

一句话：官方模板教你 FastAPI 的组装方式；Nest 教你按业务切开；本项目把两样合在「模块目录 + 全局 deps/core」，不引入第三套框架。

---

## 8. 按学习路径长出来的顺序

不要第一天把上面的树建满。空目录没有教学价值。

| 步骤 | 新建或改动 |
|---|---|
| 0 | `app/main.py`、`core/config.py`、`modules/health/router.py`、`api/router.py`、`.env.example`、`pyproject.toml` 加 entrypoint，删根 `main.py` |
| 1 | `compose.yml`（postgres）、`db/session.py`、`db/base.py`、`alembic/` |
| 2 | `modules/projects/{router,schemas,models,service}.py` |
| 3 | `tests/conftest.py`、`tests/api/test_health.py`、`tests/api/test_projects.py` |
| 4 | `core/exceptions.py`、`core/response.py`、`core/middleware.py`、`tests/api/test_errors.py` |
| 5 | `PageResult` 进 `core/response.py`，Query DTO 进模块 schemas |
| 6 | `core/context.py`、`app/deps.py`、conftest 加 `auth_client` |
| 7 | 项目 model 加 `tenant_id` + 复合索引，迁移改约束，`tests/api/test_tenant_isolation.py` |
| 8 | `modules/audit/`（只要 model + 一个写入函数） |
| 9 | `modules/tenants/`、`modules/users/`（含 `memberships`、`idp_subject`、`/me`），改 `deps.py` 做租户解析和成员校验，给 `projects.tenant_id` 补外键，`scripts/seed.py` 写真数据 |
| 10 | `core/permissions.py`、`modules/iam/`（三张表 + 角色和成员的管理接口），`deps.py` 里补权限集合的 join，路由挂 `require_perm` |
| 11 | `infra/storage/local.py`、`modules/files/` |
| 12 | 仍在已有 service 里开事务，不新目录 |
| 13 | `core/logging.py` |
| 14 | `core/security.py`（验 Logto token），改 `deps.py`、`core/config.py` 和 conftest 的 `auth_client`。**不建 `modules/auth/`** |
| 15 | 改 `core/middleware.py`、`core/config.py`、`db/session.py`、health 拆 live/ready |
| 16 | `Dockerfile`、`.dockerignore`、compose 补 api、`.github/workflows/ci.yml`、`README.md` |

这样目录是学出来的，不是抄出来的。
