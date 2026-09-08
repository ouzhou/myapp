# FastAPI 学习流程

面向已经会 NestJS 的人。终点是**一个能交付给别人在生产跑的服务**，路径是每一步都能在 `/docs` 里点通、并且有一个测试盯着，再进入下一步。

原则：

- 先有能跑的接口，再补横切能力。
- 先挖缝（seam），再换实现。认证、日志都是替换，不是推翻。
- **认证自己不写。** 密码、找回密码、验证码、社交登录、MFA 全部交给 Logto。本项目只负责两件事：把 Logto 的用户认到本地 `users` 表的一行上（认证），以及这一行能做什么（授权）。
- 生产启动顺序是 认证 → 用户 → 守卫 → 业务。学习顺序相反：业务 → 信封 → 用户缝 → 守卫 → 再把 Logto 插进缝里。
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
| 认证 / 账号体系 | Logto（自建或云，OIDC） | 密码存储、找回密码、MFA、社交登录、后台账号管理都不自己写。后端库里没有密码列，也就泄不了密码 |
| Token 校验 | PyJWT + JWKS | Logto 给 API resource 发 RS256 JWT，公钥从它的 `/oidc/jwks` 拉。验签在本地做，不用每个请求回问 IdP |
| 授权 | Casbin（第 9 步文件策略 → 第 11 步搬进库） | 「你能做什么」留在自己库里。先学「怎么问策略」，后学「策略怎么存」 |
| Lint / 类型 | Ruff + mypy | 对应 ESLint + tsc |

不要一上来用 SQLModel。它把 Entity 和 DTO 糊在一起，和 Nest 里养成的分层是反的。（官方 FastAPI skill 会推荐 SQLModel，本项目忽略这条。）

---

## 开工前必须定死的七件事

这些改起来最贵：一旦写了十个文件再回头改，等于重写。第 0–1 步就定，之后不再讨论。

| 决策 | 本项目定为 | 为什么现在定 |
|---|---|---|
| 身份从哪来 | **Logto 发 token，本地 `users` 表只存 `logto_user_id` 映射** | 这条直接决定有没有 `password_hash` 列、有没有 `POST /auth/login`、测试怎么造身份。定晚了要删列、删接口、重写全部测试 fixture。注意「不自己管密码」不等于「不要自己的用户表」：租户、角色、审计、项目成员的外键都得挂在自己的 UUID 主键上，不能挂在别人系统的字符串 id 上 |
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
10  用户资源（Logto 映射）+ /me + 真 seed
11  策略搬进库 + 权限管理接口 + 多实例刷新
12  文件上传
13  跨表事务
14  接入 Logto：验真 token 换掉假 header
15  应用日志
16  上线前收口：CORS / 安全头 / 限流 / 连接池 / 探活分层
17  交付：Dockerfile / compose / 迁移执行 / CI
```

第 0–2 步是「让一条竖线通到底」，第 3 步开始每一步都要留下一个测试，第 16–17 步把它变成能交给别人跑的东西。

每一步都写六件事：**做什么、装什么、写到哪些文件、对应 Nest 什么、过关标准、这一步刻意不做**。

文件路径以 [03-project-structure.md](./03-project-structure.md) 为准。本文件管顺序，那份管目录。按步建文件，不要提前建空包。

FastAPI 没有 Nest 那种模块化 DI 容器。不要复刻 `providers` / `Module`。按「路由 → 服务 → ORM」三层即可。Guards、当前用户、DB Session、Casbin、token 校验，全部是 `Depends`。

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

- 用 docker compose 起一个本地 Postgres（就一个 `compose.yml`，api 还不进容器，第 17 步再说）。
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

业务表可以还没有。先让「连库 + 迁移 + 探活」这条管子通。连接池调参放到第 16 步。

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

统一信封、权限、认证、完美的通用查询器。返回值先是 Pydantic 对象就行。

---

## 第 3 步：测试地基

放在这里，是因为**第 4 步之后每一步的「过关标准」都该是一个测试，而不是手点 Swagger**。租户隔离、403、事务回滚、把假身份换成真 token 这些东西，手点根本盖不住，而它们恰好是上线前最容易出事的。

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
- 序列化脱敏：读库结果必须变成 `XxxRead`，禁止直接 `return entity`。内部字段（软删标记、以后的 `logto_user_id`）默认不出站。

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

## 第 6 步：CurrentUser 缝（先不接 Logto）

**做什么**

先定义接口，再写假实现：

```text
CurrentUser = { user_id, tenant_id, roles[] }
```

第一版从 header 读，例如 `X-User-Id`、`X-Tenant-Id`、`X-Roles`。
Service 只依赖 `CurrentUser`，不依赖 header，更不依赖 token。

**`user_id` 是本地 `users` 表的 UUID 主键**（那张表第 10 步才建），不是 Logto 的 `sub`。Logto 的 id 只出现在第 14 步的映射查询里，绝不进 `CurrentUser`、不进审计表、不进任何外键。这条守住了，第 14 步换成真 token 时下层是零改动；守不住，就会有一半的表挂着别人系统的字符串 id。

同理，`CurrentUser` 里**没有** Logto 的 `scope`、`organization_id` 这些字段。缝的形状只描述「我们的用户」，不描述「IdP 怎么表达用户」。

**这个假实现必须能关掉。** 加一个 `settings.allow_header_auth`，默认只在 `ENVIRONMENT == "local"` 为真；非 local 环境读到 header 假用户直接 401。否则第 14 步接了 Logto，这个后门还留在生产里，等于没有认证。

这是整条学习路径里最重要的缝。后面的租户、审计、Casbin、Logto 都插在这里。

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

解析 Bearer Token、接 Logto、任何和 IdP 通信的代码。

---

## 第 7 步：租户落在查询上

**做什么**

只在下层「拿得到 tenant_id」还不够。规则尽早定死：

- 所有业务表带 `tenant_id`，并建 `(tenant_id, ...)` 复合索引——租户条件在每个查询里，索引不带它等于白建
- 查询默认带租户条件
- 创建时自动写入当前租户，**忽略请求体里的 `tenant_id`**（不然任何人都能往别人租户里塞数据）
- 跨租户直接 404，不要 403（避免探测别人有没有这条数据）

这一步的迁移是重点练习：给已有表加非空 `tenant_id`，正确写法是「加可空列 → 回填 → 改成非空」三步，而不是直接加 `nullable=False`（有数据的表会直接失败）。同时把第 2 步的部分唯一索引改成 `(tenant_id, name) WHERE deleted_at IS NULL`。

仍然不需要接 Logto。Header 里的假用户就够练。

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

## 第 9 步：角色 + Casbin 守卫（文件策略）

**做什么**

先有策略，再写守卫，否则你在测空气。这一步的 seed 只放**角色和策略**（还没有用户表，用户第 10 步才建）：

- `rbac_model.conf` + `policy.csv`
- 角色：`admin`、`member`
- 策略：`admin` 能 `project:write`，`member` 只能 `project:read`

守卫分两层，不要一上来全塞进 Casbin：

1. 认证依赖：拿不到 `CurrentUser` 就 401（现在检查 header，第 14 步检查 Logto 的 token）
2. 授权依赖：`require_perm(Perm.PROJECT_WRITE)`，内部问 Casbin

**权限点是代码，不是数据。** 把 `project:write` 这些字符串定成枚举放 `core/permissions.py`，`require_perm` 只接受枚举成员。第 11 步的管理后台也只能从这个枚举里勾选，不能自由输入——否则早晚出现 `porject:write` 这种拼错的策略，它永远不匹配、也永远不报错，而你以为权限已经配好了。定成枚举之后改名字时 mypy 会替你找出全部引用。

**三样东西分开放，以后只有中间那样要搬进库：**

| 关系 | Casbin 里 | 放哪 | 变更频率 |
|---|---|---|---|
| 用户 → 角色 | 不进 Casbin | `CurrentUser.roles`（第 9 步来自 header，第 10 步来自 `users` 表） | 天天变 |
| 角色 → 权限 | `p` | 第 9 步 `policy.csv`，第 11 步 `casbin_rule` 表 | 偶尔变 |
| 权限点清单 | 没有 | `core/permissions.py` 的枚举 | 跟着发版 |

**用户→角色不要进 Casbin 的 `g`。** `CurrentUser.roles` 已经拿到了，`require_perm` 里对每个角色试一次 `e.enforce(role, obj, act)`，任一个通过就放行。这样「天天变」的那部分完全在 Casbin 之外：改一个人的角色不需要动 enforcer 内存、不需要 `build_role_links()`、不需要任何刷新，下一个请求查库就是新的。留在 Casbin 里的只剩偶尔变的角色→权限，第 11 步的刷新问题也就只剩这一小块。

**用 `casbin.SyncedEnforcer`，不要用 `casbin.Enforcer`。** 本项目是同步 `def` 路由，FastAPI 把它丢线程池，所以 enforce 天然是多线程并发的；第 11 步还会加一个后台线程定期重载策略。`SyncedEnforcer` 是加了读写锁的同一套 API，改动就是类名一行；漏了是随机读到半加载的策略，这种 bug 不会在测试里出现，只在生产偶发。现在就定死。

**enforcer 藏在依赖后面。** lifespan 里建一次存 app state，路由通过 `get_enforcer()` 依赖拿，不要在模块顶层 `import` 一个全局 enforcer 对象。这和第 6 步的 `CurrentUser` 是同一个套路：第 11 步换成从库加载时只改 `get_enforcer()` 和 lifespan，`require_perm` 和路由一行不动；测试里也能靠 `dependency_overrides` 塞一份自己的策略。

**角色和策略留在自己库里，不用 Logto 的 RBAC。** Logto 自己有 role / permission，也能把角色塞进 token 的自定义 claim，本项目**不用**这条路。三个理由：策略要跟业务资源（project、dataset、file）一起演进，放进 IdP 等于把业务模型劈到两个系统；改一次权限要去改 IdP 配置，而且旧 token 里的角色要等它过期才失效；测试里改一行 `policy.csv` 立刻见效这件事也没了。

分工一句话：**Logto 只回答「你是谁」，Casbin 回答「你能做什么」。** token 里除了身份，其它字段一律不当授权依据。

角色的来源会随步骤变，但 `require_perm` 一行不用改：

| 步骤 | `CurrentUser.roles` 从哪来 |
|---|---|
| 9 | header 里的 `X-Roles`（假的） |
| 10 | 本地 `users` 表的角色字段 |
| 14 | 还是本地 `users` 表——认到人之后查库，不读 token 里的 scope |

**租户不进 Casbin 策略。** 租户是「你只能看见自己租户的行」，由第 7 步的查询条件保证；Casbin 回答的是「这个角色能不能做这个动作」。两件事混进 `rbac_with_domains` 会让策略数量随租户数膨胀，而且租户隔离一旦漏在策略里就是数据泄露。等真出现「A 租户的自定义角色」再谈 domain。

**装什么**

```bash
uv add casbin
```

**写到哪些文件**

- `app/infra/casbin/model.conf`、`policy.csv`、`enforcer.py`（`SyncedEnforcer` + `get_enforcer()` 依赖）
- `app/core/permissions.py`：权限点枚举 + `require_perm(...)`
- `scripts/seed.py`：只写角色和策略，幂等
- 改 `app/main.py`：lifespan 里初始化 enforcer
- 改 `app/modules/projects/router.py`：路由上挂认证/授权 Depends
- 加 `tests/api/test_permissions.py`

**对应 Nest**

`Guard` + `@Roles()` 装饰器 + Casbin/RBAC module。FastAPI 的 Guard 是「依赖失败就 `raise`」，不是返回 boolean。

**过关标准**

同一个接口，`X-Roles: admin` 得 200，`X-Roles: member` 得 403；没有身份得 401。改一行 `policy.csv`，测试结果跟着变。往 `require_perm` 里传一个不在枚举里的字符串，mypy 报错。

**这一步不做**

策略存库、权限管理接口、多实例刷新（三样都在第 11 步）、租户内自定义角色、数据范围（本人/本项目）、前端菜单树。

---

## 第 10 步：用户资源（Logto 映射）+ `/me` + 真 seed

**做什么**

补上「用户」这个资源。它是本地的账户实体，**不是 Logto 用户的副本**，仍然可以不接 Logto：

- 用户表字段：`id`（本地 UUID 主键）、`tenant_id`、`logto_user_id`、角色、状态、`email`、`display_name`
- **没有 `password_hash`，也没有任何密码相关列。** 这不是「以后再补」，是这条路线的结论：密码存在 Logto 那边，你的库里根本不该出现它。哪天真要自己接管登录，那是加一张表，不是现在留个空列等着
- `logto_user_id` **全局唯一**（不按租户，因为它是 Logto 那边的主键），并且**可空**——管理员先建人、人还没第一次登录时它是空的。Postgres 的唯一索引允许多行 NULL，正好符合这个语义，不用额外处理；软删后要能用同一个 Logto 账号重新建人，所以这条索引同样得带 `WHERE deleted_at IS NULL`
- `email` 是从 Logto 抄过来的**快照**，用于列表展示和搜索。它随时可能在 Logto 那边被改掉而你不知道，所以：不要用它当登录标识，不要用它做关联键。唯一性最多按 `(tenant_id, email)` 建部分索引来防止后台重复录入，但要接受它可能和 Logto 不一致（同步靠第 14 步的每次登录刷新，或者以后接 webhook）
- 管理员对用户的 CRUD（受第 9 步的 Casbin 保护）：能建人、能改角色、能停用。**不能改密码**——那个入口在 Logto
- `GET /me`：返回当前 `CurrentUser` 对应的资料
- seed 脚本从「只写策略」升级为「写一个管理员 + 一个普通用户」，header 里的 user id 要对得上

`/me` 放在 users 模块。**本项目不会有 `modules/auth/`**：没有登录、注册、改密码接口要写。

**两条建人的路，现在就想清楚哪条是主路**（第 14 步要落地成代码）：

| 方式 | 怎么工作 | 代价 |
|---|---|---|
| 管理员先建，登录时认领 | 后台建一行（`logto_user_id` 空），第一次带有效 token 进来时按 email 匹配并写入 `logto_user_id` | 要处理「认领时 email 不匹配」；但角色是先定好的，符合后台系统的实际流程 |
| JIT（首次登录自动建） | token 验过之后查不到映射就建一行 | 简单，但新人默认零角色，得有人去后台给权限；并发下靠 `logto_user_id` 唯一索引兜 |

学习阶段选 **JIT**，因为它不需要先有后台建人流程就能跑通。两条路都要求：**认证成功 ≠ 有权限**，新建用户默认没有任何角色。

**写到哪些文件**

- `app/modules/users/{router,schemas,models,service}.py`
- 改 `app/api/router.py`：挂上 users
- `app/db/seeds.py` 或 `scripts/seed.py`：可重复执行（幂等），跑两次不报错、不产生重复数据
- 加 `tests/api/test_users.py`

**对应 Nest**

User module + 当前用户接口。它是 Casbin 的数据来源，也是 Logto 身份落到本地的锚点，不是 token 的附属品。

**过关标准**

管理员身份能建用户，普通角色建用户得 403；`/me` 能返回当前假用户；seed 连跑两次结果一致；**全库搜不到 `password` 这个词**；两个租户各建一个人，`logto_user_id` 撞了要被唯一约束拦下（同一个 Logto 用户不能同时是两个本地账号）。

**这一步不做**

接 Logto、改密码、用户-角色多对多（先一人一角色字段）、从 Logto 反向同步用户列表。

---

## 第 11 步：策略搬进库 + 权限管理接口 + 多实例刷新

**做什么**

第 9 步的 `policy.csv` 改一次要发一次版，这一步把它变成后台能改的数据。**只搬「角色 → 权限」这一层**——用户→角色在第 10 步已经是 `users` 表的数据了，本来就不在 Casbin 里。

- 装官方 `casbin-sqlalchemy-adapter`（同步版，正好配本项目的同步 Session），enforcer 从 `SyncedEnforcer(model.conf, adapter)` 建，`policy.csv` 删掉
- 策略行住在 `casbin_rule(id, ptype, v0..v5)` 表里。**adapter 自带的 `create_table()` 不要用**——它绕过 Alembic，模型和迁移当场就漂移了，违反开工前定死的「永远不 `create_all`」。手写一条建表迁移，把它当自己的表管
- `scripts/seed.py` 从「写 csv」改成「往库里写默认策略」，仍然幂等
- 管理接口自己也挂 `require_perm`（权限点例如 `Perm.POLICY_WRITE`）：
  - `GET /permissions`：列出全部权限点。**数据源是第 9 步那个枚举，不是库**
  - `GET /roles/{role}/permissions`：这个角色现在有哪些
  - `PUT /roles/{role}/permissions`：整体覆盖。传进来的每一项都要能在枚举里查到，查不到就 422
- 写策略调 `e.add_policy()` / `e.remove_policy()`（`auto_save` 默认开），一次调用同时改内存和落库
- 策略变更写第 8 步的审计表。权限改动是整个系统最该留痕的东西

**不要自己维护一张 `role_permissions` 表再同步到 `casbin_rule`。** 两套真相的同步一定会漏，而漏掉的表现是「某个人的权限不对」，属于最难查的一类 bug。要么 `casbin_rule` 就是唯一真相（本项目选这条），要么自己写 adapter 让 `load_policy` 从你的表读出来喂给 model——后者也只准这一个方向，Casbin 是你表的投影，不是副本，绝不能反向写回。

**「刷新一下内存」在多 worker 下是错的。** `uvicorn --workers 4` 是四个进程、四份独立的 enforcer 内存。你在处理请求的那个进程里调了 `load_policy()`，另外三个还是旧策略，表现就是「改完权限刷新页面有时生效有时不生效」。分三档：

| 部署形态 | 怎么做 | 代价 |
|---|---|---|
| 单进程（本地、小实例） | 什么都不用做，`add_policy()` 本身就即时生效 | 无 |
| 多 worker / 多实例，能接受几秒延迟 | `start_auto_load_policy(interval)`，后台线程定期从 adapter 全量重载 | 改完最多等一个 interval；每个进程按 interval 读一次策略表 |
| 要即时 | `set_watcher()` + Redis pub/sub 或 Postgres `LISTEN/NOTIFY` | 多一个依赖。Redis 在「学习阶段不做」清单里，这档留给完整项目 |

学习阶段做到第二档：`start_auto_load_policy` 在 lifespan 里启，关闭时 `stop_auto_load_policy()`，interval 从 Settings 来。这也是第 9 步为什么要求 `SyncedEnforcer`——重载跑在后台线程、enforce 跑在请求线程池，没有读写锁就是数据竞争。

**策略是全局的，所以 `Perm.POLICY_WRITE` 不能发给租户管理员。** `casbin_rule` 里没有租户维度（第 9 步刻意不加 domain），A 租户的人改了「标注员能删项目」，B 租户的标注员立刻也能删——这是越权，而且从审计表里看只是一行正常的策略变更。这个权限点只给平台管理员。想让每个租户自己配角色，走的是下面那条 domain 的路，不是在这一步偷偷给 `casbin_rule` 加个 `tenant_id` 列：加了它 `p` 的匹配规则和 `require_perm` 的签名都要跟着改，第 9 步那个「零改动」的承诺就没了。

**角色本身仍然是代码里的常量。** 这一步做完你能配「标注员能不能删项目」，但不能凭空造一个新角色。跨过去要加 `roles` 表 + 用户与角色的关联 + 租户维度的策略（也就是 Casbin 的 domain，以及第 9 步刻意避开的策略膨胀问题），是独立一步的工作量。角色数量少而稳定的时候，这条线划在这里是划得住的。

**装什么**

```bash
uv add casbin-sqlalchemy-adapter
```

**写到哪些文件**

- 改 `app/infra/casbin/enforcer.py`：换成 adapter + 自动重载，删掉 `policy.csv`
- `app/modules/roles/{router,schemas,service}.py`：权限点和策略的管理接口
- 手写一条 `alembic/versions/xxxx_add_casbin_rule.py`
- 改 `scripts/seed.py`：默认策略写库
- 改 `app/core/config.py`：策略重载间隔
- 加 `tests/api/test_policy_admin.py`
- `core/permissions.py` 的 `require_perm` **不改**

**对应 Nest**

把 `policy.csv` 换成 TypeORM adapter + 一个 `RolesController`。Nest 那边同样要处理多实例策略缓存不一致，这不是 Python 特有的问题。

**过关标准**

改一条策略，下一个请求就生效（同进程）；起两个 worker，在一个上改策略，另一个在 interval 内跟上；`PUT` 一个不存在的权限点得 422；改策略的动作在审计表里留了一行；`casbin_rule` 是 Alembic 建的、`alembic downgrade` 能删掉；重启进程策略还在（不再依赖 csv）。第 9 步的 `tests/api/test_permissions.py` **只改造策略那一处 fixture**（从写 csv 变成 `add_policy`）就全部通过。

**这一步不做**

租户内自定义角色、Casbin domain、watcher / Redis 即时失效、数据范围（本人/本项目）、前端菜单树、按钮级权限码。

---

## 第 12 步：文件上传

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

## 第 13 步：跨表事务

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

## 第 14 步：接入 Logto（验真 token 换掉假 header）

**做什么**

只改 `get_current_user` 这一个依赖。Router / service / Casbin / 审计一行不改。

登录不在你这边发生：前端跑 Logto 的 SDK 走授权码 + PKCE，拿到 access token，之后每个请求带 `Authorization: Bearer <token>`。后端只做四件事——**验签、验声明、拿 `sub`、换成本地 `CurrentUser`**。

- **先在 Logto 里注册一个 API resource**，indicator 用绝对 URI（例如 `https://api.myapp.com`），前端换 token 时必须带上这个 `resource` 参数。不带 resource 拿到的 access token 是**不透明字符串，不是 JWT**，后端没法本地验签，只能去调 introspection 端点，等于每个请求多一次网络往返。这是接 Logto 最常踩的坑，值得在第一次联调前就确认清楚
- **校验四件事**：签名（公钥取自 Logto 的 `/oidc/jwks`）、`iss` 等于 `{LOGTO_ENDPOINT}/oidc`、`aud` 包含你注册的那个 indicator、`exp` 未过期。算法必须写成白名单常量（Logto 给 API resource 发的是 RS256），**绝不能拿 token header 里的 `alg` 去选算法**，也绝不能为了跑通而关掉验签
- `iss` 和 JWKS 地址可以从 `{LOGTO_ENDPOINT}/oidc/.well-known/openid-configuration` 发现，也可以按上面的规则直接拼。JWKS 要缓存（`PyJWKClient` 自带缓存），但要能在 Logto 轮换签名密钥后自动重取——别自己写一个永不过期的全局字典
- **`aud` 必须验。** 不验它，任何一个同 Logto 租户下、发给别的 API 的 token 都能拿来打你的接口
- **映射**：`sub` 是 Logto 的用户 id，用它查本地 `users.logto_user_id`，得到本地 `user_id` / `tenant_id`，`roles` 从本地表读。`CurrentUser` 的形状不变，所以下层什么都不用改
- **`tenant_id` 不从 token 读。** 它只由本地映射决定。token 里若出现任何租户字段一律当不存在——那是客户端能影响的输入，信它就等于把第 7 步的租户隔离拆了
- **token 里的 `scope` 不当权限用**（理由见第 9 步）。授权仍然只问 Casbin
- **查不到映射时怎么办**：按第 10 步选的 JIT 建一行，必须幂等，靠 `logto_user_id` 唯一索引兜并发（两个请求同时到达时，撞约束的那一个重查一次即可）。新建用户默认零角色，所以它能过认证、但会被 Casbin 挡在 403——这是对的
- **JIT 的 `tenant_id` 从哪来**：这是这一步唯一的真空。学习阶段用 `settings.default_tenant_id`（单租户起步），并在代码注释里写明这是简化。真要多租户自助注册时，换成 Logto organizations：给 organization 建立 `logto_org_id → tenant_id` 的映射表，从组织 token 的 `organization_id` claim（或 `aud` 里的 `urn:logto:organization:<id>`）读出组织再翻成本地租户。**不要**跳过映射表直接把 Logto 的组织 id 当 `tenant_id` 用，理由和不用它的用户 id 当主键一样
- 第 6 步的 header 假实现留作 local 开发开关，两条路汇进同一个 `CurrentUser`
- Swagger 上配 Bearer（或 OAuth2 + PKCE）安全方案，`/docs` 里能贴 token 直接点

**测试不要连真 Logto。** 在 conftest 里自己生成一对 RSA 密钥，签一个「长得像 Logto」的 token（`iss`、`aud`、`exp`、`sub` 都按真格式填），把取签名公钥的那一处 override 成本地公钥。这样测试离线可跑、CI 不依赖外部服务，而且能造出**过期 / `aud` 不对 / 签名被换 / `sub` 查不到映射**这四种用例——连真 Logto 反而造不出前三种。

**装什么**

```bash
uv add "pyjwt[crypto]"
```

`[crypto]` 装的是 `cryptography`，没有它验不了 RS256。测试里签 token 用同一个包，不用额外装。**注意这里没有 `pwdlib` / `argon2` / `bcrypt`——不存密码就不需要哈希库。**

**写到哪些文件**

- `app/core/security.py`：JWKS 客户端 + token 校验，返回 claims。这个文件里**没有密码哈希函数**，也**没有签发 token 的函数**——你不是发证方
- 改 `app/deps.py`：`get_current_user` 改成「读 Bearer → 验 token → 查本地映射」，header 假实现留作 local 开关
- 改 `app/core/config.py`：`logto_endpoint`、`logto_audience`、`default_tenant_id`
- 改 `app/modules/users/service.py`：按 `logto_user_id` 查或建本地用户（幂等），顺手刷新 email 快照
- 改 `app/main.py`：Swagger 安全方案
- 改 `tests/conftest.py`：`auth_client` 从「塞 header」改成「签自制 token」
- **不建 `app/modules/auth/`**：没有登录接口要写
- `modules/projects`、`modules/users` 的业务 service **不改**

**对应 Nest**

`passport-jwt` + `jwks-rsa` 换掉占位 Guard——是这个组合，而不是自己 `JwtModule.sign()`。业务代码无感知。

**过关标准**

第 3–13 步的测试**只改 conftest 里造身份的那一个 fixture** 就全部通过。过期 token 401；签名被换 401；`aud` 是别的 API 的 token 401；没有 `Authorization` 头 401；token 里塞 `tenant_id` 不生效（仍然只能看到映射到的那个租户的数据）。另外验一件事：**把 Logto 停掉，已经拿到的 token 仍然能用**——验签是本地的，这正是它比「每个请求回问 IdP」强的地方（代价是撤销不即时，靠短 token 缓解）。

**这一步不做**

自己写登录 / 注册 / 找回密码 / MFA / 社交登录（Logto 的活）、刷新令牌轮换和登出（前端 SDK + Logto 的活）、用 Management API 反向同步用户列表、webhook 接 `User.Created`、organizations 多租户、把 Logto 的 scope 当权限用。

---

## 第 15 步：应用日志

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

一次失败请求的日志能对上响应里的 `request_id`；日志里搜不到任何 token 或 `Authorization` 头的内容（token 解出来的 claims 也不要整段打出去，只留 `sub`）。

**这一步不做**

完整可观测平台、链路采样、ELK、指标大盘、APM。

---

## 第 16 步：上线前收口

到这里功能齐了，但还不能对外。这一步专门补「不做就会出事」的东西，都很小：

**做什么**

- **CORS**：显式 origin 白名单。带 `allow_credentials=True` 时不能配 `allow_origins=["*"]`（浏览器会拒，且本身不安全）
- **安全头**：一个小中间件加 `X-Content-Type-Options: nosniff`、`X-Frame-Options: DENY`、`Referrer-Policy`、HTTPS 环境下的 HSTS。对应 Nest 的 helmet
- **请求体上限 / 超时**：上传接口以外的请求体限死；这两件更适合在网关（nginx / ingress）做，应用里至少兜一层
- **限流**：公开接口按 IP 限流。登录爆破归 Logto 管了，你这边要防的是被拿到 token 之后的滥刷——按 `user_id` + 路由限流比按 IP 更准
- **连接池调参**：`pool_size`、`max_overflow`、`pool_pre_ping=True`、`pool_recycle`。算一下 `worker 数 × pool_size` 有没有超过 Postgres 的 `max_connections`
- **探活分层**：`/health/live` 只回自己活着，不碰数据库（数据库抖一下不该让编排系统把进程杀了重启）；`/health/ready` 探数据库，决定要不要往这个实例打流量
- **JWKS 的失败姿势**：拉不到 Logto 的公钥时必须返回 5xx，**绝不能退化成「跳过验签」或「放行」**。启动时不要强依赖它能拉通（Logto 慢启动会让你起不来），但要给它超时和重试；缓存里已有的 key 在拉取失败时继续用
- **探活不要去探 Logto**：第三方挂了不该让编排系统把你的实例全摘掉。它的可用性反映在请求的 401/5xx 上，不该反映在 `/health/ready` 上
- **优雅关闭**：lifespan 关闭时 `engine.dispose()`；确认收到 SIGTERM 后是把在途请求做完再退
- **配置的启动断言**：prod 环境下 `allow_header_auth` 必须 false、`LOGTO_ENDPOINT` 必须是 https 且不是示例值、`LOGTO_AUDIENCE` 必须非空、`DEBUG` 必须 false、`DATABASE_URL` 不能指向 localhost。用 Pydantic 的 `model_validator` 在启动时炸，而不是上线后才发现。**`LOGTO_AUDIENCE` 空着最危险**：验签会过，但任何一个发给别的 API 的 token 都能打进来
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

把 `ENVIRONMENT=prod` 且 `ALLOW_HEADER_AUTH=true`（或 `LOGTO_AUDIENCE` 留空）启动，应用**拒绝启动**。停掉数据库，`/health/live` 仍 200、`/health/ready` 变 503。把 `LOGTO_ENDPOINT` 指到一个不通的地址，业务接口返回 5xx 而不是放行。跨域请求从未授权 origin 被拒。

**这一步不做**

WAF、DDoS 防护、密钥托管系统（Vault / KMS）——那些是基础设施的事。

---

## 第 17 步：交付

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
- Casbin 的进阶授权：租户内自定义角色和 domain、watcher（Redis / `LISTEN-NOTIFY`）做策略即时失效、数据范围（本人 / 本项目）、前端菜单树和按钮级权限码
- Logto 的进阶能力：organizations 多租户、Management API 反向同步、webhook 接 `User.Created`、企业 SSO、MFA 策略
- 对象存储、WebSocket 协同
- 邮件、i18n
- k8s、多环境流水线、全量测试金字塔

「刷新令牌、登出、改密码」不在这个清单里，因为它们不再是你的工作量——前端 SDK 和 Logto 分掉了。你要接的是它们的**结果**：用户在 Logto 那边改了邮箱、被停用、被删号，你本地那行怎么跟上（webhook 或每次登录刷新快照）。

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
| TypeORM casbin adapter + 策略缓存 | `casbin-sqlalchemy-adapter` + `SyncedEnforcer.start_auto_load_policy` |
| `@Req()` / CLS | `Depends` + `ContextVar` |
| `ConfigModule` + validation schema | `pydantic-settings` + `model_validator` |
| `passport-jwt` + `jwks-rsa` | 一个 `Depends`：验 Logto 的 token + 查本地映射 |
| 自己写的 `AuthModule` / 登录接口 | 没有。登录在 Logto，后端只验 token |
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

一次只做一步。做完看「过关标准」，通过再往下。第 3 步之后，「过关标准」优先落成测试而不是手点 Swagger。不要跳步去接 Logto 或写日志——第 6 步的 header 假用户能把你一路撑到第 13 步。

文件不知道放哪时查 [03-project-structure.md](./03-project-structure.md)，不要另开一套目录。完整系统还要哪些能力，看 [02-full-project-features.md](./02-full-project-features.md)——那份清单里标了「学习路径已覆盖」和「完整项目再做」。

走完 16 步，你手里是一个**能上线但功能只有一个资源**的服务：底座是生产级的，业务是最小的。之后按 02 的第 9 节往上长业务，底座不用重做。
