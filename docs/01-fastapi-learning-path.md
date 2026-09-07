# FastAPI 学习流程

面向已经会 NestJS 的人。终点是**一个能交付给别人在生产跑的服务**，路径是每一步都能在 `/docs` 里点通、并且有一个测试盯着，再进入下一步。

原则：

- 先有能跑的接口，再补横切能力。
- 先挖缝（seam），再换实现。JWT、日志、真登录都是替换，不是推翻。
- 生产启动顺序是 JWT → 用户 → 守卫 → 业务。学习顺序相反：业务 → 信封 → 用户缝 → 守卫 → 再把 JWT 插进缝里。
- 生产化不是最后一天补的。前面每一步都不许留「以后再改就好」的东西：迁移、时区、约束命名、测试库，都在第一次碰到时就按生产的写法定死。

技术选型（学习阶段固定，避免来回换）：

| 用途 | 选择 | 原因 |
|---|---|---|
| Web | FastAPI | 当前项目 |
| DTO / 校验 | Pydantic v2 | 对应 Nest DTO + class-validator |
| ORM | SQLAlchemy 2.0 | Entity 和 DTO 分开，接近 TypeORM |
| 迁移 | Alembic | 没有迁移就没有模型版本 |
| 配置 | pydantic-settings | 对应 ConfigModule |
| 数据库 | PostgreSQL | 生产就是它，本地也用它 |
| 测试 | pytest + httpx | 对应 Jest + supertest |
| 授权 | Casbin（先文件策略） | 先学「怎么问策略」，后学「策略怎么存」 |
| Lint / 类型 | Ruff + mypy | 对应 ESLint + tsc |

不要一上来用 SQLModel。它把 Entity 和 DTO 糊在一起，和 Nest 里养成的分层是反的。（官方 FastAPI skill 会推荐 SQLModel，本项目忽略这条。）

---

## 开工前必须定死的六件事

这些改起来最贵：一旦写了十个文件再回头改，等于重写。第 0–1 步就定，之后不再讨论。

| 决策 | 本项目定为 | 为什么现在定 |
|---|---|---|
| 同步还是异步 | **同步 `Session` + `def` 路由** | 换 async 要动每个 service 签名、session 依赖、Alembic env、全部测试 fixture。FastAPI 把 `def` 路由丢线程池，不阻塞事件循环，够用到很后面。真出现高并发外部 IO，再整体切一次，而不是两种混着写 |
| 数据库 | **PostgreSQL，本地用 docker compose 起** | 在 SQLite 上练，到 Postgres 会连着踩 UUID 类型、JSONB、约束名、大小写、`ILIKE`、并发锁。省下的两小时会在上线前还回去 |
| 主键 | **UUID（`uuid.uuid4`，列类型用 PG `UUID`）** | 对外不泄露自增顺序、跨租户导数据不撞。代价是随机 UUID 主键的索引局部性差，单表上亿再考虑换 uuid7 或 bigint |
| 时间 | **列一律 `DateTime(timezone=True)`，应用内只传 UTC aware datetime** | 库里混进 naive 本地时间之后基本救不回来。禁止 `datetime.utcnow()`（它返回 naive），用 `datetime.now(UTC)` |
| 表结构变更 | **只走 Alembic，永远不调 `create_all()`**（测试库也一样） | `create_all` 一旦用上，模型和迁移会悄悄漂移，某天生产迁移就跑不过去 |
| 错误怎么回 | **真 HTTP 状态码 + 信封里的业务 code** | 一律返回 200 再让前端读 code，会让网关、监控、重试、Swagger 全部失效 |

第 0 步就在 `pyproject.toml` 里声明入口，之后 `uv run fastapi dev` 不用带路径：

```toml
[tool.fastapi]
entrypoint = "app.main:app"
```

同时删掉仓库根的示例 `main.py`，否则 `fastapi dev` 会去发现它而不是 `app/main.py`。

---

## 总览

```text
0   骨架：create_app / settings / health
1   Postgres + SQLAlchemy session + Alembic + 真探活
2   第一个资源 CRUD + 软删除
3   测试地基：pytest + httpx + 独立测试库
4   统一信封 + 统一错误 + 序列化脱敏
5   列表：分页 + 白名单 filter/sort
6   CurrentUser 缝（header 假用户）
7   租户落在查询上
8   操作审计日志
9   角色 + Casbin 守卫（文件策略）
10  用户资源 + /me + 真 seed
11  文件上传
12  跨表事务
13  JWT 换掉 CurrentUser + 登录
14  应用日志
15  上线前收口：CORS / 安全头 / 限流 / 连接池 / 探活分层
16  交付：Dockerfile / compose / 迁移执行 / CI
```

第 0–2 步是「让一条竖线通到底」，第 3 步开始每一步都要留下一个测试，第 15–16 步把它变成能交给别人跑的东西。

每一步都写六件事：**做什么、装什么、写到哪些文件、对应 Nest 什么、过关标准、这一步刻意不做**。

文件路径以 [03-project-structure.md](./03-project-structure.md) 为准。本文件管顺序，那份管目录。按步建文件，不要提前建空包。

FastAPI 没有 Nest 那种模块化 DI 容器。不要复刻 `providers` / `Module`。按「路由 → 服务 → ORM」三层即可。Guards、当前用户、DB Session、Casbin、JWT，全部是 `Depends`。

---

## 第 0 步：能启动的骨架

**做什么**

- 用工厂函数创建 app，挂 `lifespan`（启动/销毁）。
- 用 `pydantic-settings` 读环境变量：应用名、`ENVIRONMENT`（local/staging/prod）、后面要用的 `DATABASE_URL`。
- Settings 用单例（`@lru_cache` 或模块级实例），不要在每个请求里重新读环境变量。
- 用 `APIRouter` 按模块挂载，前缀统一 `/api/v1`。
- 留一个 `GET /health`，先返回静态 `{ "status": "ok" }`。
- 同时建 `.env.example`（只放键名和假值）和 `.env`（真值，已被 gitignore）。

**装什么**

```bash
uv add pydantic-settings
```

**写到哪些文件**

- `app/main.py`：`create_app()`、`lifespan`、模块级 `app = create_app()`
- `app/core/config.py`：Settings
- `app/api/router.py`：只 `include_router`
- `app/modules/health/router.py`：health 接口
- `pyproject.toml`：`[tool.fastapi] entrypoint`
- 删掉仓库根的 `main.py`

**对应 Nest**

`main.ts` + `ConfigModule.forRoot`（`isGlobal` + validation schema）+ 根模块里 `imports` 各个 Controller。

**过关标准**

`uv run fastapi dev` 能起来，打开 `/docs`，health 能点通。故意删掉 `.env` 里一个必填项，启动时应当直接报错退出，而不是跑起来之后才在某个请求里炸。

**这一步不做**

业务路由、数据库、统一返回信封。

---

## 第 1 步：Postgres + Session + 迁移 + 真探活

**做什么**

- 用 docker compose 起一个本地 Postgres（就一个 `compose.yml`，api 还不进容器，第 16 步再说）。
- 配置 SQLAlchemy engine 和 `sessionmaker`。
- 写 `get_db()`：`yield` session，请求结束自动关闭。这是 FastAPI 版的「请求作用域 provider」。
- `DeclarativeBase` 上给 `MetaData` 配 **约束命名规范**。不配这个，Alembic 之后想改/删一个约束会生成不出名字，只能手写迁移：

```python
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

- 做 `TimestampMixin`（`created_at` / `updated_at`，都是 `DateTime(timezone=True)`）和 `SoftDeleteMixin`（`deleted_at`）。
- 接入 Alembic：`env.py` 从 Settings 读 `DATABASE_URL`（不要在 `alembic.ini` 里硬编码），`target_metadata` 指向 `Base.metadata`。
- 把 `/health` 改成真探活：跑一句 `SELECT 1` 才算健康。

**装什么**

```bash
uv add sqlalchemy alembic "psycopg[binary]"
uv run alembic init alembic
```

（`alembic init -t async` 是给异步用的模板，本项目走同步，用默认模板。）

**写到哪些文件**

- `compose.yml`：只有 postgres 一个服务
- `app/db/session.py`：engine、`sessionmaker`、`get_db()`
- `app/db/base.py`：`DeclarativeBase` + naming convention、`TimestampMixin`、`SoftDeleteMixin`
- `alembic.ini`、`alembic/env.py`、`alembic/versions/`
- 改 `app/modules/health/router.py`：探数据库
- 这一步还没有 `app/deps.py`。health 先直接依赖 `get_db`，第 6 步再包成 `DbSession`

**对应 Nest**

`TypeOrmModule.forRootAsync`（从 ConfigService 读连接串）+ 请求作用域 provider + TypeORM migration + `TerminusModule` 的 `TypeOrmHealthIndicator`。

**过关标准**

空库跑一次 `alembic upgrade head` 成功，再跑一次 `alembic downgrade base` 也成功（能降级的迁移才算写对了）。停掉 postgres 容器，health 返回失败；起回来，health 恢复。

**这一步不做**

业务表可以还没有。先让「连库 + 迁移 + 探活」这条管子通。连接池调参放到第 15 步。

---

## 第 2 步：第一个资源的 CRUD + 软删除

**做什么**

只做一个资源，例如「标注项目」。四个 DTO 分开：

- `ProjectCreate`
- `ProjectUpdate`（字段全可选，用 `model_dump(exclude_unset=True)` 做部分更新）
- `ProjectRead`（`model_config = ConfigDict(from_attributes=True)`）
- `ProjectQuery`（列表查询参数，这一步可以很薄）

分层：

- 路由：校验入参、调 service、返回。
- Service：业务。
- Model：只描述表。

模型带 `deleted_at`，删除走软删。列表默认过滤掉软删的行。

**软删和唯一约束会打架，现在就处理**：如果项目名要唯一，普通唯一索引会让「删掉再建同名」失败。用部分唯一索引，Alembic 里手写 `postgresql_where`：

```python
Index(
    "uq_projects_name_active",
    "name",
    unique=True,
    postgresql_where=text("deleted_at IS NULL"),
)
```

这条索引第 7 步加租户时还要改一次（变成 `tenant_id, name`）。那是正常的模型演进，不是设计失误——顺手练一次「改约束」的迁移。

**写到哪些文件**

- `app/modules/projects/router.py`
- `app/modules/projects/schemas.py`
- `app/modules/projects/models.py`
- `app/modules/projects/service.py`
- 改 `app/api/router.py`：挂上 projects
- 软删字段用 `app/db/base.py` 的 mixin，不要每个表手写一遍
- 查询先写在 service 里，不要新建 `repository.py`

**对应 Nest**

Controller + Service + Entity + DTO；软删除对应 TypeORM `@DeleteDateColumn`；`PartialType(CreateDto)` 对应这里的 Update DTO。

**过关标准**

增删改查在 Swagger 里都能走通；删除后普通列表看不到，`SELECT` 数据库能看到行还在；删掉一个项目后能再建同名项目。

**这一步不做**

统一信封、权限、JWT、完美的通用查询器。返回值先是 Pydantic 对象就行。

---

## 第 3 步：测试地基

放在这里，是因为**第 4 步之后每一步的「过关标准」都该是一个测试，而不是手点 Swagger**。租户隔离、403、事务回滚、JWT 换缝这些东西，手点根本盖不住，而它们恰好是上线前最容易出事的。

**做什么**

- 一个独立测试库（`myapp_test`），用 `alembic upgrade head` 建表，不用 `create_all`。
- `conftest.py` 三个 fixture：
  - `engine`：session 级，指向测试库。
  - `db_session`：函数级。开一个外层事务，把 session 绑上去，测试结束 **rollback**。每个测试都在干净数据上跑，且不用反复建表。
  - `client`：`TestClient`，用 `app.dependency_overrides[get_db]` 把上面的 `db_session` 塞进去，让请求和测试共用同一个事务。
- 把第 2 步的 CRUD 补两个测试：建了能查到、软删后列表里没有。
- 测的是 **HTTP 契约**：状态码、响应体形状、能不能看见别人的数据。不要去单测每条 SQL。

**装什么**

```bash
uv add --dev pytest httpx
```

**写到哪些文件**

- `tests/conftest.py`
- `tests/api/test_health.py`
- `tests/api/test_projects.py`
- `pyproject.toml`：`[tool.pytest.ini_options]`（`testpaths`、测试库连接串走单独环境变量）

**对应 Nest**

Jest + `Test.createTestingModule` + supertest；`dependency_overrides` 对应 `overrideProvider`。

**过关标准**

`uv run pytest` 全绿，并且**连续跑两次结果一样**（第二次不因为上一次留下的数据而失败）。

**这一步不做**

覆盖率门槛、factory 库、mock 掉数据库。真库 + 事务回滚比 mock 有用得多。

---

## 第 4 步：统一返回 + 统一错误 + 序列化脱敏

**做什么**

约定一种信封，成功和失败同一张皮：

```json
{ "code": 0, "message": "ok", "data": {} }
```

```json
{ "code": 40401, "message": "项目不存在", "data": null, "details": [], "request_id": "..." }
```

**先知道信封的代价，再决定要不要它。** 包一层之后，如果只是随手 `return {"code": 0, ...}`，`/docs` 里所有接口的响应 schema 都会退化成一个空对象，等于扔掉了 FastAPI 最值钱的部分。要留住它，信封必须是泛型模型：

```python
T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    code: int = 0
    message: str = "ok"
    data: T | None = None
```

（`requires-python = ">=3.11"`，所以用 `Generic[T]` 写法；升到 3.12 之后才能用 `class Envelope[T](BaseModel)`。）

路由声明 `-> Envelope[ProjectRead]`，列表声明 `-> Envelope[PageResult[ProjectRead]]`。错误响应是 handler 里返回的 `JSONResponse`，OpenAPI 看不见，得在路由或 `create_app()` 上用 `responses={404: {"model": Envelope[None]}}` 补声明。

如果不想背这个成本，另一条同样正经的路是：成功直接返回 DTO（不包信封），失败用 RFC 9457 problem details。本项目选信封，因为前端和 Nest 时期的约定一致；但这是一次有代价的选择，不是默认最优。

四处错误收进同一套 handler：

| 来源 | 处理 | HTTP 状态 |
|---|---|---|
| 参数校验失败 | 捕获 `RequestValidationError`，把 Pydantic 的错误列表塞进 `details` | 422 |
| 业务错误 | 自定义 `AppError`（带业务 code 和 http_status）+ `exception_handler` | 400 / 404 / 409 … |
| 唯一索引冲突 | 捕获 `IntegrityError`，转成业务语义 | 409 |
| 未处理异常 | 捕获 `Exception`，对外只给通用信息和 `request_id`，细节只进日志 | 500 |

业务 code 现在就定编码规则（例如 `40401` = HTTP 404 + 资源序号 01），并集中在一个枚举里。散着写魔法数字，前端就没法映射，i18n 也没有挂点。

同时做两件小事：

- `request_id`：中间件从 header 读或生成，放进 `request.state`、响应 header 和错误体。这是协议字段，不是日志系统。
- 序列化脱敏：读库结果必须变成 `XxxRead`，禁止直接 `return entity`。密码、内部字段、软删标记默认不出站。

**写到哪些文件**

- `app/core/exceptions.py`：`AppError`、业务 code 枚举、各类 handler
- `app/core/response.py`：`Envelope`
- `app/core/middleware.py`：`request_id` 中间件
- 改 `app/main.py`：注册 handler 和中间件
- 改 `app/modules/projects/service.py`：业务失败抛 `AppError`
- 改 `app/modules/projects/router.py`：声明 `Envelope[...]` 返回类型
- 加 `tests/api/test_errors.py`

**对应 Nest**

全局 `ExceptionFilter` + 包装返回的 Interceptor + `ClassSerializerInterceptor` + 把 `QueryFailedError` 转 409。

**过关标准**

测试覆盖三件事：传错参数、查不存在的 id、创建重名项目——三种响应形状和成功时一样，状态码分别是 422 / 404 / 409，响应里看不到实体内部字段。`/docs` 里 `ProjectRead` 的字段仍然是展开的，不是 `{}`。

**这一步不做**

结构化日志框架、i18n 文案表。`request_id` 先挂在信封上即可。

---

## 第 5 步：列表查询（分页 + 白名单 filter/sort）

**做什么**

后台第一个真实痛点通常是列表，不是单条 CRUD。做成通用能力：

- `PageResult[T]`：`items`、`total`、`page`、`page_size`
- `pagination_params` 依赖，`page_size` 必须有上限（例如 100），否则一个 `page_size=100000` 就能把进程打满
- 过滤、排序走白名单：Query DTO 里用 `Literal["created_at", "name"]` 声明允许的排序字段，非法值由 Pydantic 直接 422，不要把前端字符串拼进 SQL
- 默认过滤已软删数据
- `total` 用单独的 `select(func.count())`，不要把全表拉进内存再 `len()`

不要复刻完整的 `@nestjsx/crud`。只要 filter / sort / page 三件套，每个资源声明自己允许哪些字段。

**写到哪些文件**

- `PageResult`、分页参数放进 `app/core/response.py`（或同目录一个小文件，不要新开顶层包）
- 过滤/排序白名单写在 `app/modules/projects/schemas.py` 的 Query DTO
- 拼查询仍在 `app/modules/projects/service.py`
- 改 `tests/api/test_projects.py`：加分页和非法排序的用例

**对应 Nest**

`@nestjsx/crud` 的 query 协议（filter、sort、page），但只取其受控的那一部分。

**过关标准**

列表返回 `items + total + page`；非法排序字段返回 422；`page_size` 超上限被拒；软删数据默认不出现。

**这一步不做**

任意 join、任意 select、游标分页、把查询语言做成前端万能协议。

---

## 第 6 步：CurrentUser 缝（先不解析 JWT）

**做什么**

先定义接口，再写假实现：

```text
CurrentUser = { user_id, tenant_id, roles[] }
```

第一版从 header 读，例如 `X-User-Id`、`X-Tenant-Id`、`X-Roles`。
Service 只依赖 `CurrentUser`，不依赖 header，更不依赖 JWT。

**这个假实现必须能关掉。** 加一个 `settings.allow_header_auth`，默认只在 `ENVIRONMENT == "local"` 为真；非 local 环境读到 header 假用户直接 401。否则第 13 步上了 JWT，这个后门还留在生产里，等于没有认证。

这是整条学习路径里最重要的缝。后面的租户、审计、Casbin、JWT 都插在这里。

**写到哪些文件**

- `app/core/context.py`：`CurrentUser` 数据结构（Pydantic model 或 dataclass，不是 ORM 实体）
- `app/deps.py`：从 header 组装 `CurrentUser`，并把 `get_db` 包成 `DbSession`
- 改 `app/core/config.py`：加 `allow_header_auth`
- 改 `app/modules/projects/router.py`：注入 `CurrentUserDep`
- 改 `app/modules/projects/service.py`：接收 `CurrentUser`，不要自己读 header
- 改 `tests/conftest.py`：加一个能造任意用户 header 的 `auth_client` fixture

**对应 Nest**

先挂一个占位 Guard / `@Req()` 上的 user，再换 Passport 策略。FastAPI 里就是换一个 `Depends`。

**过关标准**

Service 里能用到 `user_id`、`tenant_id`；换一组 header，数据跟着变；把 `ENVIRONMENT` 改成 `prod` 后，header 假用户失效返回 401。

**这一步不做**

解析 Bearer Token、登录接口、密码校验。

---

## 第 7 步：租户落在查询上

**做什么**

只在下层「拿得到 tenant_id」还不够。规则尽早定死：

- 所有业务表带 `tenant_id`，并建 `(tenant_id, ...)` 复合索引——租户条件在每个查询里，索引不带它等于白建
- 查询默认带租户条件
- 创建时自动写入当前租户，**忽略请求体里的 `tenant_id`**（不然任何人都能往别人租户里塞数据）
- 跨租户直接 404，不要 403（避免探测别人有没有这条数据）

这一步的迁移是重点练习：给已有表加非空 `tenant_id`，正确写法是「加可空列 → 回填 → 改成非空」三步，而不是直接加 `nullable=False`（有数据的表会直接失败）。同时把第 2 步的部分唯一索引改成 `(tenant_id, name) WHERE deleted_at IS NULL`。

仍然不需要 JWT。Header 里的假用户就够练。

**写到哪些文件**

- 改 `app/modules/projects/models.py`：加 `tenant_id` + 复合索引
- 新的 Alembic 迁移：加列、回填、加非空、换唯一索引
- 改 `app/modules/projects/service.py`：查、改、删都带租户条件
- 加 `tests/api/test_tenant_isolation.py`
- 不要新建 repository；租户条件先集中在这一个 service 里

**对应 Nest**

多租户中间件 / CLS + 在 repository 里默认加 tenant 条件。本项目没有 repository，条件写在 service。

**过关标准**

一个测试：租户 A 建的数据，用租户 B 的身份 **查不到（404）、改不了（404）、删不了（404）**，列表里也不出现。请求体里伪造 `tenant_id` 无效。

**这一步不做**

每租户一个数据库、动态切连接串、行级安全策略（RLS）。

---

## 第 8 步：操作审计日志

**做什么**

这不是 access log。记的是业务动作：

- 谁（user_id）
- 在哪个租户
- 对哪个资源、哪条 id
- 做了 create / update / delete
- 改前 / 改后（可以先做精简字段）
- request_id、IP（有就记）

第一版在 service 里写库。写审计和主流程**放在同一个事务**里最简单也最不会丢：主流程回滚，审计也回滚。等审计量大了再考虑异步，但那时候要接受「可能丢」。开发期不要静默吞掉审计的异常。

审计表只增不改，`updated_at` 没意义，别套 `TimestampMixin` 里的全部字段。

**写到哪些文件**

- `app/modules/audit/models.py`：审计表
- `app/modules/audit/service.py`：一个写入函数即可，不必先做完整 CRUD
- 改 `app/modules/projects/service.py`：写操作后调用审计
- 加 `tests/api/test_audit.py`
- 审计还没有对外路由，不要挂到 `api/router.py`

**对应 Nest**

Audit Interceptor + 一张 audit 表。它依赖当前用户，不依赖日志框架。

**过关标准**

改一条项目，审计表多一行，能对上 user_id、tenant_id 和资源 id。让主流程在写审计之后失败，审计行不该留下来。

**这一步不做**

回滚到历史版本、完整 diff UI、事件总线、把审计和 stdout 日志混成一套。

---

## 第 9 步：角色 + Casbin 守卫

**做什么**

先有策略，再写守卫，否则你在测空气。这一步的 seed 只放**角色和策略**（还没有用户表，用户第 10 步才建）：

- `rbac_model.conf` + `policy.csv`
- 角色：`admin`、`member`
- 策略：`admin` 能 `project:write`，`member` 只能 `project:read`

守卫分两层，不要一上来全塞进 Casbin：

1. 认证依赖：拿不到 `CurrentUser` 就 401（现在检查 header，第 13 步检查 JWT）
2. 授权依赖：`require_perm("project", "write")`，内部问 Casbin

**租户不进 Casbin 策略。** 租户是「你只能看见自己租户的行」，由第 7 步的查询条件保证；Casbin 回答的是「这个角色能不能做这个动作」。两件事混进 `rbac_with_domains` 会让策略数量随租户数膨胀，而且租户隔离一旦漏在策略里就是数据泄露。等真出现「A 租户的自定义角色」再谈 domain。

Enforcer 在 lifespan 里建一次，存在 app state 里，不要每个请求读一遍 csv。

**装什么**

```bash
uv add casbin
```

**写到哪些文件**

- `app/infra/casbin/model.conf`、`policy.csv`、`enforcer.py`
- `app/core/permissions.py`：`require_perm(...)`
- 改 `app/main.py`：lifespan 里初始化 enforcer
- 改 `app/modules/projects/router.py`：路由上挂认证/授权 Depends
- 加 `tests/api/test_permissions.py`

**对应 Nest**

`Guard` + `@Roles()` 装饰器 + Casbin/RBAC module。FastAPI 的 Guard 是「依赖失败就 `raise`」，不是返回 boolean。

**过关标准**

同一个接口，`X-Roles: admin` 得 200，`X-Roles: member` 得 403；没有身份得 401。改一行 `policy.csv`，测试结果跟着变。

**这一步不做**

策略存数据库、权限管理后台、动态菜单树、数据范围（本人/本项目）。

---

## 第 10 步：用户资源 + `/me` + 真 seed

**做什么**

补上「用户」这个资源，仍然可以不解 JWT：

- 用户表：归属租户、角色、状态、`password_hash`（这一步先留空或存一个哈希占位，**永远不留明文列**）
- 邮箱唯一性按租户来：`(tenant_id, email)` 唯一，配合软删还是部分索引
- 管理员对用户的 CRUD（受第 9 步的 Casbin 保护）
- `GET /me`：返回当前 `CurrentUser` 对应的资料
- seed 脚本从「只写策略」升级为「写一个管理员 + 一个普通用户」，header 里的 user id 要对得上

`/me` 放在 users 模块，此时还没有 auth 模块。

**写到哪些文件**

- `app/modules/users/{router,schemas,models,service}.py`
- 改 `app/api/router.py`：挂上 users
- `app/db/seeds.py` 或 `scripts/seed.py`：可重复执行（幂等），跑两次不报错、不产生重复数据
- 加 `tests/api/test_users.py`

**对应 Nest**

User module + 当前用户接口。它是 Casbin 的数据来源，不是 JWT 的附属品。

**过关标准**

管理员身份能建用户，普通角色建用户得 403；`/me` 能返回当前假用户；seed 连跑两次结果一致；`UserRead` 里绝对没有 `password_hash`。

**这一步不做**

登录、密码校验流程、刷新令牌、用户-角色多对多（先一人一角色字段）。

---

## 第 11 步：文件上传

**做什么**

做一个最小可用的上传切片，服务标注业务：

- 接收 multipart 文件
- 校验类型和大小：**别信客户端给的 `content_type` 和扩展名**，按实际字节判断；大小限制要边读边计数，不能先 `await file.read()` 把整个文件读进内存再判断
- 生成服务端自己的存储文件名（UUID），原始文件名只作为展示字段存库。直接用用户给的名字拼路径 = 目录穿越漏洞
- 先落到本地磁盘（对象存储以后再换），路径按 `tenant_id` 分目录
- 落一条文件记录：原名、存储路径、大小、mime、uploader、tenant_id、资源关联（可选）

这是第二个垂直切片。有了它，后面的数据集导入才有地方放。

**装什么**

```bash
uv add python-multipart
```

（`fastapi[standard]` 已经带上了，确认一下即可。）

**写到哪些文件**

- `app/infra/storage/local.py`：落盘，以后换 S3 只改这里（先把接口定成 `save/open/delete` 三个函数）
- `app/modules/files/{router,schemas,models,service}.py`
- 改 `app/api/router.py`：挂上 files
- 加 `tests/api/test_files.py`（用 `tmp_path` 当存储根，别往仓库里写文件）

**对应 Nest**

`FileInterceptor` / Multer；boilerplate 里常见的 local + S3 双驱动，学习期只做 local。

**过关标准**

能上传一张图；超大文件被拒且没有把内存吃掉；伪造扩展名的文件被拒；用别的租户身份看不到这条文件记录。

**这一步不做**

S3、图片转码、断点续传、直传签名、病毒扫描。

---

## 第 12 步：跨表事务

**做什么**

选一个真实的跨表写：例如「创建项目 + 写入默认标签集」，或「上传文件 + 创建文件记录 + 挂到项目」。

整段放进同一个 session/事务。这一步的关键是**把事务边界定在一个地方**：

- 事务由 `get_db` 依赖或 service 的入口统一 `commit` / `rollback`
- service 内部的函数只 `flush`，不各自 `commit`。到处 `commit` 是这条路上最常见的坑，一旦出现，回滚就失效了
- 副作用（写文件、发邮件）不能放在事务里当作会回滚——磁盘不会跟着 rollback。要么放到 commit 之后，要么接受可能产生孤儿文件并配清理

**写到哪些文件**

- 不新开目录。改已有 `modules/projects/service.py`（或 files 的 service）
- 默认标签如果只是项目附属，表可以先放在 `modules/projects/models.py`
- 加 `tests/api/test_transaction.py`

**对应 Nest**

`@Transactional` / `QueryRunner` / `dataSource.transaction()`。

**过关标准**

一个测试：人为让第二步失败（重复标签名等），项目行不会留下半成品，审计也没有留下那一行。

**这一步不做**

分布式事务、跨服务 saga、Saga 补偿。

---

## 第 13 步：JWT 换掉 CurrentUser + 登录

**做什么**

只改 CurrentUser 这一个依赖。Router / service / Casbin / 审计尽量一行不改。

- JWT 里读出 `sub`、`tenant_id`、`roles`，填进现有的 `CurrentUser`
- `POST /auth/login`：校验用户表密码，签发 token
- 密码哈希用 argon2 或 bcrypt。这一步不是「以后再补」的，登录出现的同时它就必须在
- 登录失败的响应不要区分「用户不存在」和「密码错误」，统一一句话（避免账号枚举）
- `SECRET_KEY` 从 Settings 来，prod 环境校验它不是默认值（第 15 步会把这条做成启动断言）
- token 里放 `exp`、`iat`、`jti`；`tenant_id` 和 `roles` 放进 token 是为了少查一次库，代价是改权限要等 token 过期——access token 就得短（15–30 分钟）
- Swagger 的 Bearer 安全方案配上，`/docs` 里能直接点 Authorize
- 第 6 步的 header 假实现留作 local 开发开关

刷新令牌、登出黑名单这一步可以不做（见 [02](./02-full-project-features.md) 的登录产品化）。

**装什么**

```bash
uv add pyjwt "pwdlib[argon2]"
```

**写到哪些文件**

- `app/modules/auth/{router,schemas,service}.py`：登录
- `app/core/security.py`：签发/校验 JWT、密码哈希与校验
- 改 `app/deps.py`：CurrentUser 改为读 Bearer，header 假实现留作 local 开关
- 改 `app/api/router.py`、`app/main.py`：挂登录、Swagger Bearer
- 改 `tests/conftest.py`：`auth_client` 改成签真 token（这一步之后测试也走真链路）
- `modules/projects`、`modules/users` 的 service **不改**

**对应 Nest**

Passport JWT 策略 + `JwtModule` 替换占位 Guard。业务代码无感知。

**过关标准**

第 3–12 步的测试**只改 conftest 里造身份的那一个 fixture** 就全部通过。过期 token 得 401，签名被改的 token 得 401，别的租户的 token 看不到数据。

**这一步不做**

社交登录、2FA、SSO、完整刷新令牌体系、登出黑名单。

---

## 第 14 步：应用日志

**做什么**

现在才上结构化日志。此时已经有 `request_id`、`user_id`、`tenant_id`，日志终于有东西可绑。

只做这些：

- JSON 输出（标准 `logging` 的 `dictConfig` 或 structlog），本地可以人类可读、prod 走 JSON
- 请求开始/结束：方法、路径、状态码、耗时
- 业务异常 `warning`，未知异常 `exception`（带 traceback）
- 用 `ContextVar` 自动带上 `request_id` / `user_id` / `tenant_id`，不要每行手传
- 日志只写 stdout，交给容器收集。不要在应用里写日志文件、切割文件
- 明确不许进日志的字段：password、token、Authorization header、上传文件内容

**装什么**

```bash
uv add structlog   # 或者只用标准库 logging，不装
```

**写到哪些文件**

- `app/core/logging.py`：配置 + ContextVar
- 改 `app/main.py`：lifespan 里初始化，中间件里绑上下文
- 改 `app/core/exceptions.py`：handler 里记日志
- 不要和 `modules/audit` 混进同一个文件

**对应 Nest**

Pino / Winston + 请求日志中间件。和操作审计仍然分开：一个给开发排障，一个给后台追责。

**过关标准**

一次失败请求的日志能对上响应里的 `request_id`；日志里搜不到任何密码或 token。

**这一步不做**

完整可观测平台、链路采样、ELK、指标大盘、APM。

---

## 第 15 步：上线前收口

到这里功能齐了，但还不能对外。这一步专门补「不做就会出事」的东西，都很小：

**做什么**

- **CORS**：显式 origin 白名单。带 `allow_credentials=True` 时不能配 `allow_origins=["*"]`（浏览器会拒，且本身不安全）
- **安全头**：一个小中间件加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy`、HTTPS 环境下的 HSTS。对应 Nest 的 helmet
- **请求体上限 / 超时**：上传接口以外的请求体限死；这两件更适合在网关（nginx / ingress）做，应用里至少兜一层
- **限流**：登录和其它公开接口按 IP + 账号限流，防爆破
- **连接池调参**：`pool_size`、`max_overflow`、`pool_pre_ping=True`、`pool_recycle`。算一下 `worker 数 × pool_size` 有没有超过 Postgres 的 `max_connections`
- **探活分层**：`/health/live` 只回自己活着，不碰数据库（数据库抖一下不该让编排系统把进程杀了重启）；`/health/ready` 探数据库，决定要不要往这个实例打流量
- **优雅关闭**：lifespan 关闭时 `engine.dispose()`；确认收到 SIGTERM 后是把在途请求做完再退
- **配置的启动断言**：prod 环境下 `SECRET_KEY` 不能是默认值、`DEBUG` 必须 false、`allow_header_auth` 必须 false、`DATABASE_URL` 不能指向 localhost。用 Pydantic 的 `model_validator` 在启动时炸，而不是上线后才发现
- **`/docs` 的暴露**：内网后台可以留；公网建议 prod 关掉或加保护

**写到哪些文件**

- 改 `app/main.py`：CORS、安全头中间件
- `app/core/middleware.py`：安全头、限流（或用 slowapi）
- 改 `app/core/config.py`：prod 断言
- 改 `app/db/session.py`：连接池参数
- 改 `app/modules/health/router.py`：拆 live / ready
- `.env.example` 补齐所有键

**对应 Nest**

`app.enableCors()` + helmet + `ThrottlerModule` + `app.enableShutdownHooks()` + Terminus 的 liveness/readiness 分组。

**过关标准**

把 `ENVIRONMENT=prod` 且用默认 `SECRET_KEY` 启动，应用**拒绝启动**。停掉数据库，`/health/live` 仍 200、`/health/ready` 变 503。跨域请求从未授权 origin 被拒。

**这一步不做**

WAF、DDoS 防护、密钥托管系统（Vault / KMS）——那些是基础设施的事。

---

## 第 16 步：交付

**做什么**

- **Dockerfile**：多阶段构建，`uv sync --frozen --no-dev`，非 root 用户运行，`fastapi run` 起服务。别把 `.env`、`.venv`、测试打进镜像（写 `.dockerignore`）
- **compose.yml**：api + postgres（+ 以后的 redis）。第 1 步只有 postgres，现在补上 api
- **迁移怎么执行**：`alembic upgrade head` 作为独立的一次性任务/init container 跑，**不要放在应用启动里**——多个 worker 同时跑迁移会互相锁死
- **迁移向前兼容**：滚动发布时新旧代码会同时在跑。加列必须可空或带默认值；删列分两次发布（先让代码不再用它，再删）。这条规矩现在写进文档，比出事后再学便宜
- **CI**：`ruff check` + `ruff format --check` + `mypy` + `pytest`（CI 里挂一个 postgres service）。跑不过不许合
- **README**：怎么起、怎么跑迁移、怎么跑测试、环境变量表

**装什么**

```bash
uv add --dev ruff mypy
```

**写到哪些文件**

- `Dockerfile`、`.dockerignore`
- 改 `compose.yml`
- `.github/workflows/ci.yml`
- `pyproject.toml`：`[tool.ruff]`、`[tool.mypy]`
- `README.md`

**对应 Nest**

`nest build` + Dockerfile + `typeorm migration:run` 作为 release 命令 + GitHub Actions。

**过关标准**

在一台干净机器上 `docker compose up`，服务起来、迁移跑过、`/health/ready` 是 200、seed 能跑、Swagger 能点。CI 在 PR 上全绿。

**这一步不做**

k8s manifest、Helm、蓝绿/金丝雀、多环境流水线。先有一个能跑的镜像。

---

## 学习阶段明确不做

这些会把「先跑起来」拖死，放到 [02-full-project-features.md](./02-full-project-features.md) 里：

- Redis / 缓存
- Celery / ARQ / 后台任务 / 定时任务
- Casbin 策略存库和权限管理后台
- 刷新令牌、SSO、完整注册登录产品化
- 对象存储、WebSocket 协同
- 邮件、i18n
- k8s、多环境流水线、全量测试金字塔

标注业务本身（数据集、预标注、质检流）当作第 2 步之后的「下一个资源」往上叠，不要和第 0–5 步的框架学习缠在一起。

---

## NestJS → FastAPI 对照

| NestJS | FastAPI |
|---|---|
| `Module` | 包 + `APIRouter` |
| `Controller` | `APIRouter` 上的函数 |
| `Injectable` Service | 普通 class / 函数，用 `Depends` 组装 |
| DTO + `class-validator` | Pydantic v2 |
| `ValidationPipe` | 自动，来自类型注解 |
| `PartialType(CreateDto)` | 单独写一个字段全可选的 Update DTO |
| Entity + TypeORM | SQLAlchemy 2.0 model |
| `ExceptionFilter` | `exception_handler` |
| Interceptor（包装返回） | 泛型 `Envelope[T]` 返回模型 |
| `ClassSerializerInterceptor` | 强制走 Read DTO / 返回类型注解 |
| `Guard` | 会 `raise` 的 `Depends` |
| `@Roles()` + RolesGuard | `Depends(require_perm(...))` |
| `@Req()` / CLS | `Depends` + `ContextVar` |
| `ConfigModule` + validation schema | `pydantic-settings` + `model_validator` |
| Passport JWT | 一个 `Depends`，替换 CurrentUser |
| `TerminusModule` | health 里探数据库，拆 live / ready |
| Multer | `UploadFile` |
| `@Transactional` | 同一个 session，入口处统一 commit |
| Audit Interceptor | service 写审计表，后期可改事件 |
| `ThrottlerModule` | slowapi 或网关限流 |
| helmet | 自己写的安全头中间件 |
| Jest + supertest | pytest + `TestClient` |
| `overrideProvider` | `app.dependency_overrides` |
| `enableShutdownHooks` | `lifespan` 的关闭段 |

---

## 怎么用这份文档

一次只做一步。做完看「过关标准」，通过再往下。第 3 步之后，「过关标准」优先落成测试而不是手点 Swagger。不要跳步去写 JWT 或日志。

文件不知道放哪时查 [03-project-structure.md](./03-project-structure.md)，不要另开一套目录。完整系统还要哪些能力，看 [02-full-project-features.md](./02-full-project-features.md)——那份清单里标了「学习路径已覆盖」和「完整项目再做」。

走完 16 步，你手里是一个**能上线但功能只有一个资源**的服务：底座是生产级的，业务是最小的。之后按 02 的第 9 节往上长业务，底座不用重做。
