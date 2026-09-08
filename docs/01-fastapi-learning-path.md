# FastAPI 学习流程

面向已经会 NestJS 的人。终点是**一个能交付给别人在生产跑的服务**，路径是每一步都能在 `/docs` 里点通、并且有一个测试盯着，再进入下一步。

原则：

- 先有能跑的接口，再补横切能力。
- 先挖缝（seam），再换实现。认证、日志都是替换，不是推翻。
- **认证自己不写。** 密码、找回密码、验证码、社交登录、MFA 全部交给 Logto。本项目只负责两件事：把外部身份认到本地 `users` 表的一行上（认证），以及这一行在某个租户里能做什么（授权）。
- **授权自己写。** 「谁能做什么」是业务模型，留在自己库里，用普通表和一次 join 解决，不引入策略引擎（理由见第 10 步）。
- 生产启动顺序是 认证 → 用户 → 守卫 → 业务。学习顺序相反：业务 → 信封 → 用户缝 → 用户表 → 守卫 → 最后才把 Logto 插进缝里。
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
| 授权 | **自己的四张表 + 一次 join**（无 Casbin、无 OPA、无策略引擎） | 需求是「每个租户自定义自己的角色」，角色就成了租户数据而不是策略。数据用表存，不用把它塞进策略引擎的内存（理由见第 10 步） |
| Lint / 类型 | Ruff + mypy | 对应 ESLint + tsc |

不要一上来用 SQLModel。它把 Entity 和 DTO 糊在一起，和 Nest 里养成的分层是反的。（官方 FastAPI skill 会推荐 SQLModel，本项目忽略这条。）

---

## 开工前必须定死的九件事

这些改起来最贵：一旦写了十个文件再回头改，等于重写。第 0–1 步就定，之后不再讨论。

| 决策 | 本项目定为 | 为什么现在定 |
|---|---|---|
| 身份从哪来 | **外部 IdP（Logto）发 token，本地 `users` 表只存 `idp_subject` 映射** | 这条直接决定有没有 `password_hash` 列、有没有 `POST /auth/login`、测试怎么造身份。定晚了要删列、删接口、重写全部测试 fixture。注意「不自己管密码」不等于「不要自己的用户表」：租户、角色、审计、项目成员的外键都得挂在自己的 UUID 主键上，不能挂在别人系统的字符串 id 上。列名叫 `idp_subject` 而不是 `logto_user_id`，这样哪天换 IdP 只改一处配置，不用改列名和它的全部引用 |
| 用户和租户的关系 | **多对多，`memberships` 表**（`users` 表上**没有** `tenant_id` 列） | 「一个人只属于一个租户」是最贵的假设之一：它会让 `tenant_id` 长在 `users` 上、让角色挂在用户上，等真出现跨租户的人（顾问、代运营、平台客服）时要拆表、改全部外键、重写身份装配。表结构现在就按多对多建，产品行为可以先只支持一个（见下一行） |
| 当前请求在哪个租户 | **`X-Tenant-Id` header 声明 + 服务端校验成员关系**，缺省回落到 `users.last_selected_tenant_id`，再回落到最早的一个 membership | 一个用户能属于多个租户，所以「当前租户」必须显式化。放在 header 而不是 URL，是为了让业务路由签名一直不变；放在 header 而不是 token，是因为切租户不该要求换 token。**安全性不来自「不信客户端」，而来自「每个请求校验成员关系」**——这一点和第 7 步的「忽略请求体里的 `tenant_id`」不矛盾，区别是这里校验、那里丢弃 |
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
9   用户 + 租户 + 成员关系（多对多）+ /me + 真 seed
10  租户内自定义角色与权限 + 守卫 + 权限管理接口
11  文件上传
12  跨表事务
13  应用日志
14  接入 Logto：验真 token 换掉假 header
15  上线前收口：CORS / 安全头 / 限流 / 连接池 / 探活分层
16  交付：Dockerfile / compose / 迁移执行 / CI
```

第 0–2 步是「让一条竖线通到底」，第 3 步开始每一步都要留下一个测试，第 15–16 步把它变成能交给别人跑的东西。

**为什么 Logto 排在第 14 步、而不是更后面。** 前 13 步全靠第 6 步的 header 假用户撑着，所以它确实可以一直拖。但它不能拖到第 15 步之后：第 15 步收口要断言「prod 下假用户后门必须关、`LOGTO_AUDIENCE` 必须非空、JWKS 拉不到时必须 5xx 而不是放行」，这些断言的前提是认证已经是真的。14 是它能待的最后一个位置。

每一步都写六件事：**做什么、装什么、写到哪些文件、对应 Nest 什么、过关标准、这一步刻意不做**。

文件路径以 [03-project-structure.md](./03-project-structure.md) 为准。本文件管顺序，那份管目录。按步建文件，不要提前建空包。

FastAPI 没有 Nest 那种模块化 DI 容器。不要复刻 `providers` / `Module`。按「路由 → 服务 → ORM」三层即可。Guards、当前用户、DB Session、权限校验、token 校验，全部是 `Depends`。

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
- 序列化脱敏：读库结果必须变成 `XxxRead`，禁止直接 `return entity`。内部字段（软删标记、以后的 `idp_subject`）默认不出站。

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
CurrentUser = { user_id, tenant_id, membership_id, permissions[], is_platform_admin }
```

第一版从 header 读，例如 `X-User-Id`、`X-Tenant-Id`、`X-Permissions`。
Service 只依赖 `CurrentUser`，不依赖 header，更不依赖 token。

**`user_id` 是本地 `users` 表的 UUID 主键**（那张表第 9 步才建），不是 IdP 的 `sub`。IdP 的 id 只出现在第 14 步的映射查询里，绝不进 `CurrentUser`、不进审计表、不进任何外键。这条守住了，第 14 步换成真 token 时下层是零改动；守不住，就会有一半的表挂着别人系统的字符串 id。

同理，`CurrentUser` 里**没有** Logto 的 `scope`、`organization_id` 这些字段。缝的形状只描述「我们的用户」，不描述「IdP 怎么表达用户」。

三个字段的形状值得现在就解释，因为它们各自堵住一类返工：

- **`membership_id`**：`(user_id, tenant_id)` 那一行的主键。第 10 步的角色授予挂在它上面，而不是挂在 `user_id` 上——挂 membership 才能让「这个人在哪个租户」和「这个角色属于哪个租户」天然一致。审计表记 `user_id` + `tenant_id` 就够，不用记它。
- **`permissions` 而不是 `roles`**：装配这个对象时就把「该成员在该租户内的权限点集合」算好，之后守卫只做集合判断。带 `roles` 进来的坏处是有人会忍不住写 `if "admin" in user.roles`，那是把角色名硬编码进业务——而角色名从第 10 步起是租户自己起的，随时能改名甚至删掉。角色名要展示就让 `/me` 单独查。
- **`is_platform_admin`**：跨租户的平台身份（谁能建租户）。它不能由任何租户内的角色配置授予，所以单独一个字段，不混进 `permissions`。

`tenant_id` 这一版直接信 header。第 9 步建了 `memberships` 表之后，它变成「header 声明 → 校验成员关系 → 解析出 membership」，`CurrentUser` 的形状不变。

**这个假实现必须能关掉。** 加一个 `settings.allow_header_auth`，默认只在 `ENVIRONMENT == "local"` 为真；非 local 环境读到 header 假用户直接 401。否则第 14 步接了 Logto，这个后门还留在生产里，等于没有认证。

这是整条学习路径里最重要的缝。后面的租户、审计、权限守卫、Logto 都插在这里。

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

解析 Bearer Token、接 Logto、任何和 IdP 通信的代码。校验 header 里的租户是不是真的（没有 `memberships` 表可校验，第 9 步补）。

---

## 第 7 步：租户落在查询上

**做什么**

只在下层「拿得到 tenant_id」还不够。规则尽早定死：

- 所有业务表带 `tenant_id`，并建 `(tenant_id, ...)` 复合索引——租户条件在每个查询里，索引不带它等于白建
- 查询默认带租户条件
- 创建时自动写入当前租户，**忽略请求体里的 `tenant_id`**（不然任何人都能往别人租户里塞数据）
- 跨租户直接 404，不要 403（避免探测别人有没有这条数据）

这一步的迁移是重点练习：给已有表加非空 `tenant_id`，正确写法是「加可空列 → 回填 → 改成非空」三步，而不是直接加 `nullable=False`（有数据的表会直接失败）。同时把第 2 步的部分唯一索引改成 `(tenant_id, name) WHERE deleted_at IS NULL`。

**`tenant_id` 现在还没有 `tenants` 表可以做外键。** 这一版它就是个裸 UUID 列，第 9 步建了 `tenants` 表之后再补外键约束——那也是一条正常的迁移练习。别为了「现在就能加外键」把建租户表提前到这一步，那会把第 9 步的身份模型拆成两半。

区分两件容易混的事：**请求体里的 `tenant_id` 一律丢弃**（创建时用当前租户覆盖），而**header 里的 `X-Tenant-Id` 是当前租户的声明**，第 9 步起要校验成员关系。前者没有任何合法用途，后者是多租户系统的正常输入。

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

## 第 9 步：用户 + 租户 + 成员关系 + `/me` + 真 seed

**做什么**

补上身份模型。它是本地的账户实体，**不是 IdP 用户的副本**，而且仍然不接 Logto——header 假用户继续用，只是它声明的租户从这一步开始要对着库校验。

```text
tenants      id, slug(唯一), name, status
users        id, email(全局唯一), display_name, status, is_platform_admin,
             idp_subject(可空、全局唯一), last_selected_tenant_id(可空)
memberships  id, user_id, tenant_id, status    UNIQUE(user_id, tenant_id)
```

外加一条迁移：把第 7 步那个裸 `projects.tenant_id` 列补上指向 `tenants` 的外键。

字段级的决定，每条都在堵一类返工：

- **`users` 上没有 `tenant_id`。** 用户是全局的，「在哪个租户」是 `memberships` 的事。
- **`email` 全局唯一，不是 `(tenant_id, email)`。** 这是多对多的直接后果：同一个人在两个租户里必须是同一行 `users`，否则 `memberships` 就没意义了。它仍然是 IdP 那边的**快照**（第 14 步每次登录刷新），所以不要拿它当关联键，只用于展示和搜索。
- **没有 `password_hash`，没有任何密码列。** 密码在 IdP 那边。哪天真要自己接管登录，那是加一张表，不是现在留个空列等着。
- **`idp_subject` 可空 + 全局唯一 + 部分索引。** 这一列现在全是空的，第 14 步才写入。可空是因为「管理员先建人、人还没第一次登录」；全局唯一（不按租户）是因为它是别人系统的主键；索引带 `WHERE deleted_at IS NULL`，这样软删之后同一个 IdP 账号还能重新建人。
- **`last_selected_tenant_id` 可空，外键 `ON DELETE SET NULL`。** 它是「上次选的租户」，不是权限。它可能指向一个用户已经被移出的租户，所以每次读都要重新校验成员关系，失效就往下回落。

**租户解析的三级回落**，写在 `deps.py` 里，只有这一处：

| 顺序 | 输入 | 处理 |
|---|---|---|
| 1 | 有 `X-Tenant-Id` | 按 `(user_id, 该租户)` 查 `memberships`，查到就用，查不到 **403** |
| 2 | 无 header，`last_selected_tenant_id` 有值 | 同样校验成员关系（人可能已被移出），通过才用 |
| 3 | 上面都没有 | 取该用户**最早**的一个 membership（按 `created_at`，必须稳定排序） |
| 4 | 一个 membership 都没有 | **403**，这个人还没被加进任何租户 |

第 3 条就是「暂时只会选第一个租户」：表结构已经是多对多，产品行为先只用回落。将来前端要切租户，调 `PUT /me/current-tenant` 写 `last_selected_tenant_id` 就行，**不用换 token**——这正是租户不进 JWT 的原因。

两个容易做错的地方：

- **别在每个请求里更新 `last_selected_tenant_id`。** 那等于给每个读请求都加一次写，白白制造行锁和 WAL。只有显式的切换接口才写它。
- **403 的文案不要区分「租户不存在」和「你不是这个租户的成员」。** 两种情况回同一句话，否则这个接口就成了探测租户是否存在的工具。这和第 7 步「跨租户返回 404」是同一个思路，那里藏的是数据，这里藏的是租户。

**平台管理员是 `users.is_platform_admin` 布尔，不是某个租户里的角色。** 谁能建租户、谁能跨租户排查问题，这件事不能由任何租户自己的角色配置授予。并且**平台管理员要操作某个租户的业务数据，也必须在那个租户里有 membership**——不给它开「跳过成员校验」的后门。这样成员校验在代码里只有一条路径、没有例外分支；平台自己的动作（建租户、停用租户）走单独的路由和单独的依赖。

这一步只暴露两个接口，都只涉及「我自己」：

- `GET /me`：当前用户资料 + 他的租户列表 + 当前生效的租户。**这个接口不要求 `X-Tenant-Id`**，因为前端得先拿到租户列表才知道能选什么。
- `PUT /me/current-tenant`：切租户，校验成员关系后写 `last_selected_tenant_id`。

**用户和成员的管理接口（建人、拉人进租户、移除）不在这一步。** 它们需要权限保护，而守卫是第 10 步的东西。这一步的写入只由 seed 脚本做，HTTP 上不留任何裸奔的写接口。

这也正是为什么把用户表排在守卫**之前**：第 10 步的角色表要挂 `tenant_id` 外键、授予表要挂 `membership_id` 外键，没有这三张表，权限模型没有地方落脚。

`/me` 放在 users 模块。**本项目不会有 `modules/auth/`**：没有登录、注册、改密码接口要写。

seed 建一个租户、一个平台管理员、一个普通用户，两个人都有该租户的 membership，header 里的 user id 要对得上。幂等——查不到才建。

**写到哪些文件**

- `app/modules/tenants/{router,schemas,models,service}.py`
- `app/modules/users/{router,schemas,models,service}.py`（`memberships` 表放这里，它描述的是「这个用户属于谁」）
- 改 `app/deps.py`：`CurrentUser` 从「直接信 header」变成「查库 + 校验成员关系 + 三级回落」
- 改 `app/api/router.py`：挂上 users
- 新的 Alembic 迁移：三张表 + 给 `projects.tenant_id` 补外键
- 改 `scripts/seed.py`：租户 + 两个人 + membership，幂等
- 加 `tests/api/test_me.py`、`tests/api/test_membership.py`
- 改 `tests/conftest.py`：`auth_client` 现在要先造出真的 user / tenant / membership 行，再塞 header

**对应 Nest**

User module + Organization/Membership module + 当前用户接口。它是权限模型的数据来源，也是外部身份落到本地的锚点，不是 token 的附属品。

**过关标准**

把同一个用户加进两个租户，`/me` 列出两个；不带 header 时落在最早那个；`PUT /me/current-tenant` 切过去之后，不带 header 的请求落在新租户；带一个自己不是成员的 `tenant_id` 得 403；把 membership 删掉之后，原来能看到的项目变成看不到。seed 连跑两次结果一致。**全库搜不到 `password` 这个词。**

**这一步不做**

接 Logto、角色和权限（第 10 步）、用户和成员的管理接口（第 10 步）、邀请邮件、租户配额、从 IdP 反向同步用户列表。

---

## 第 10 步：租户内自定义角色与权限 + 守卫 + 管理接口

**做什么**

这一步做完，每个租户能自己造角色、自己勾权限，改完下一个请求就生效。三张表：

```text
roles             id, tenant_id, code, name, is_system   UNIQUE(tenant_id, code)
role_permissions  role_id, permission                    PK(role_id, permission)
membership_roles  membership_id, role_id                 PK(membership_id, role_id)
```

**没有 `permissions` 表。** 权限点是代码里的枚举（`core/permissions.py`），`role_permissions.permission` 存的就是枚举的值。租户能自由组合权限，但不能新造权限点——`project:write` 这种字符串对应的是代码里真实存在的检查点，让租户自由输入的结果是早晚出现 `porject:write`，它永远不匹配、也永远不报错，而管理员以为权限已经配好了。定成枚举之后，改名字时 mypy 会替你找出全部引用。（业界通用做法里 `permissions` 往往也是租户数据，那是因为要支持租户自定义资源类型；本项目的资源类型 project / dataset / file 是代码定义的，所以这张表可以省掉。）

**授予关系挂 `membership_id`，不挂 `user_id`。** 这是整个模型最关键的一条：`membership_roles` 连的是「某人在某租户的身份」和「某租户的角色」，两边天然同租户。如果挂 `(user_id, role_id)`，那么「把 B 租户的角色授给只在 A 租户的人」在库层是完全合法的，只能靠代码自觉——而那正好是多租户权限系统最典型的越权 bug。

**库层再加一道租户一致性（推荐）。** 给 `roles` 和 `memberships` 各加一个冗余的 `UNIQUE(id, tenant_id)`，`membership_roles` 存 `(membership_id, role_id, tenant_id)` 并建两个复合外键分别指过去。这样 Postgres 直接保证两边租户相同，纯声明式、零运行时成本。租户边界值得被强制两次：一次在约束里，一次在运行时。

**权限点是代码，角色是数据。** 这条线划清了，剩下的都简单：

| 东西 | 住在哪 | 谁能改 | 变更频率 |
|---|---|---|---|
| 权限点清单 | `core/permissions.py` 的枚举 | 发版 | 跟着功能走 |
| 角色，和它有哪些权限 | `roles` + `role_permissions` | 租户管理员，通过接口 | 偶尔 |
| 谁是什么角色 | `membership_roles` | 租户管理员，通过接口 | 天天 |

**守卫分两层：**

1. 认证依赖：拿不到 `CurrentUser` 就 401（现在检查 header，第 14 步检查 token）
2. 授权依赖：`require_perm(Perm.PROJECT_WRITE)`，判断权限点在不在 `CurrentUser.permissions` 里，不在就 403

`require_perm` 只接受枚举成员，不接受字符串。

**权限集合在装配 `CurrentUser` 时一次查出来**：`membership_roles → role_permissions` 两表 join，按 `membership_id` 走主键索引，返回几十行。一个请求查一次，之后 `require_perm` 是纯内存的集合判断。这里不需要缓存、不需要把策略装进进程内存、不需要多进程同步——**你要的从来不是「全部租户的全部策略」，而是「这一个人在这一个租户的权限集合」。**

真到了这次 join 变成热点的那天，正确的缓存姿势是缓存「有效权限集合 per `(user_id, tenant_id)`」而不是缓存最终判断，cache key 必须带 `tenant_id`（漏了它，一个在 A 租户是管理员、在 B 租户只读的人最终会在两边都是管理员），失效靠给每个租户维护一个 `acl_version` 拼进 key。学习阶段不做，但要知道形状。

**系统预置角色**：建租户时自动创建 `owner` / `admin` / `member`，`is_system = true`，不能删、不能改 code。两条护栏现在就加，否则租户会把自己锁死：

- `owner` 的权限集合不可编辑（它恒等于全部权限点）
- 撤销角色时，如果这是租户里最后一个 `owner`，拒绝（409）

自定义角色就是 `is_system = false` 的行，租户管理员随便建，权限从枚举里勾。

**接口**（自己也挂 `require_perm`）：

- `GET /permissions`：列出全部权限点。**数据源是那个枚举，不是库**
- `GET /roles`、`POST /roles`、`PATCH /roles/{id}`、`DELETE /roles/{id}`：租户内角色 CRUD，全部带租户条件
- `PUT /roles/{id}/permissions`：整体覆盖。传进来的每一项都要能在枚举里查到，查不到就 422
- `GET /members`、`POST /members`、`DELETE /members/{id}`：第 9 步押后的成员管理，现在有权限保护了
- `PUT /members/{id}/roles`：给成员授角色。角色必须属于当前租户（库层有约束兜底，代码里也要查一次，为了回 422 而不是 500）

删角色靠外键 `ON DELETE CASCADE` 带走它的 `role_permissions` 和 `membership_roles` 行。这是自己建表相对于外挂策略引擎最实在的好处之一：不存在「角色删了但它的权限行还在」这种幽灵状态，也不会出现新角色复用了旧 id 就继承旧权限。

**所有权限变更都写第 8 步的审计表，而且在同一个事务里。** 权限行是你自己的表、用的是请求里那同一个 session，所以「改权限」和「记这笔改动」同生共死。权限改动是整个系统最该留痕的东西，不能出现「改成功了但没记上」。

**为什么不用 Casbin / OPA 这类策略引擎**

这不是「学习阶段先简化」，是这个需求下的结论，写下来免得以后有人来加：

- **策略引擎的内存模型是它的实现细节，不是你的需求。** Casbin 要把全量策略装进进程内存，因为它的引擎是「策略住在 model 里、matcher 逐行求值」。多租户下策略行数是「租户 × 角色 × 权限点」，每个 worker 一份，还得按 interval 全量重载。官方给的缓解手段是按 domain 过滤加载，但在一个「任意 worker 服务任意租户」的 web 应用里用不上——你没法预先知道该加载哪些租户。更麻烦的是 `SyncedEnforcer.start_auto_load_policy` 起的线程调的是全量 `load_policy()`，第一次 tick 就把过滤条件冲掉。
- **`casbin-sqlalchemy-adapter` 的 `add_policy()` 在它自己的 sessionmaker 上开事务并 commit**，和请求里那个 session 无关。于是「改权限 + 写审计」不可能同事务：审计插入失败回滚时，权限改动早就落库了。这一条同时违反「审计和主流程同生共死」和「commit 只在一个地方发生」两条约定。
- **同一个 adapter 的 `Adapter.__init__` 默认 `create_all_models=True`，构造时就 `Base.metadata.create_all(engine)`**，绕过 Alembic 直接建表。必须显式关掉才不违反「永远不 `create_all`」。
- **角色是数据，不是策略。** 「每个租户自定义角色」在策略引擎里反而是偏贵的需求（细粒度 ReBAC 系统里往往要求每个租户一份策略清单），在普通表里是最自然的。

**什么信号出现时该换成策略引擎**：权限不再只跟「角色」有关，而是跟「关系」有关——「只有这个项目的成员能看它的任务」「只能看自己创建的」「文件夹权限继承给子文件夹」。那类递归关系自己写会写成一堆递归 CTE，SpiceDB / OpenFGA / Oso 就是干这个的（Oso 甚至能返回 SQL WHERE 片段，让列表接口不用 N+1）。到那天要换的只有 `require_perm` 背后的实现，路由和 service 一行不动——这正是它必须是一个依赖、而不是散在各处的 `if` 的原因。

**写到哪些文件**

- `app/core/permissions.py`：权限点枚举 + `require_perm(...)`
- `app/modules/iam/{router,schemas,models,service}.py`：角色、角色权限、成员授角色、成员管理
- 改 `app/modules/users/service.py`：装配 `CurrentUser` 时 join 出权限集合
- 改 `app/deps.py`：`CurrentUser.permissions` 填真值
- 新的 Alembic 迁移：三张表 + 冗余唯一约束 + 复合外键
- 改 `app/modules/projects/router.py`：路由上挂 `Depends(require_perm(...))`
- 改 `scripts/seed.py`：建租户时 seed 系统角色，给两个人授角色
- 加 `tests/api/test_permissions.py`、`tests/api/test_roles_admin.py`
- **没有 `app/infra/casbin/`**，也没有 `model.conf` / `policy.csv` / `casbin_rule` 表

**对应 Nest**

`Guard` + `@Roles()` 装饰器，但权限来自自己的表而不是装饰器参数。FastAPI 的 Guard 是「依赖失败就 `raise`」，不是返回 boolean。

**过关标准**

同一个接口，有 `project:write` 的角色得 200，只有 `project:read` 的得 403，没有身份得 401。在租户 A 里新建一个自定义角色、勾上 `project:write`、授给某人，那个人**下一个请求**就能写（不重启、不等任何 interval），租户 B 完全不受影响。往 `require_perm` 里传一个不在枚举里的字符串，mypy 报错；`PUT` 一个不存在的权限点得 422。把 B 租户的 role_id 授给 A 租户的成员，被数据库约束拦下。撤销租户里最后一个 owner 得 409。改一条权限，审计表多一行；让审计写入失败，权限改动也不留下。

**这一步不做**

数据范围（本人 / 本项目 / 本部门）、资源级 ACL、角色继承和层级、权限集合的 Redis 缓存、前端菜单树和按钮级权限码、角色模板（`is_system` 那三个够用了）、从 SSO 的 group 映射角色。

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

## 第 13 步：应用日志

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

## 第 14 步：接入 Logto（验真 token 换掉假 header）

**做什么**

只改 `get_current_user` 这一个依赖。Router / service / 权限守卫 / 审计一行不改。

登录不在你这边发生：前端跑 Logto 的 SDK 走授权码 + PKCE，拿到 access token，之后每个请求带 `Authorization: Bearer <token>`。后端只做四件事——**验签、验声明、拿 `sub`、换成本地 `CurrentUser`**。

- **先在 Logto 里注册一个 API resource**，indicator 用绝对 URI（例如 `https://api.myapp.com`），前端换 token 时必须带上这个 `resource` 参数。不带 resource 拿到的 access token 是**不透明字符串，不是 JWT**，后端没法本地验签，只能去调 introspection 端点，等于每个请求多一次网络往返。这是接 Logto 最常踩的坑，值得在第一次联调前就确认清楚
- **校验四件事**：签名（公钥取自 Logto 的 `/oidc/jwks`）、`iss` 等于 `{LOGTO_ENDPOINT}/oidc`、`aud` 包含你注册的那个 indicator、`exp` 未过期。算法必须写成白名单常量（Logto 给 API resource 发的是 RS256），**绝不能拿 token header 里的 `alg` 去选算法**，也绝不能为了跑通而关掉验签
- `iss` 和 JWKS 地址可以从 `{LOGTO_ENDPOINT}/oidc/.well-known/openid-configuration` 发现，也可以按上面的规则直接拼。JWKS 要缓存（`PyJWKClient` 自带缓存），但要能在 Logto 轮换签名密钥后自动重取——别自己写一个永不过期的全局字典
- **`aud` 必须验。** 不验它，任何一个同 Logto 租户下、发给别的 API 的 token 都能拿来打你的接口
- **映射**：`sub` 是 Logto 的用户 id，用它查本地 `users.idp_subject`，得到本地 `user_id`；租户和权限仍然走第 9、10 步那条路——**解析当前租户、校验成员关系、join 出权限集合，这三件事一行都不用改**。`CurrentUser` 的形状不变，所以下层什么都不用改
- **租户绝对不从 token 读。** 它由 `X-Tenant-Id` + 本地成员校验决定（第 9 步的三级回落）。token 里若出现任何租户字段一律当不存在：Logto 的组织 id 是另一个系统的标识，认它等于把成员关系的判断权交给 IdP
- **token 里的 `scope` 不当权限用**（理由见第 10 步）。授权仍然只查自己的表
- **查不到映射时怎么办**：走 JIT——验过 token 之后查不到 `idp_subject` 就建一行 `users`，必须幂等，靠 `idp_subject` 唯一索引兜并发（两个请求同时到达时，撞约束的那一个重查一次即可）
- **JIT 建出来的人默认没有任何 membership**，所以他能过认证、但会被第 9 步的租户解析挡在 403。这是对的：**认证成功 ≠ 属于任何租户，属于租户 ≠ 有权限**。要让他能干事，得有人在后台把他拉进租户并授个角色
- **另一条建人的路是「管理员先建、登录时认领」**：后台先建一行（`idp_subject` 空）并配好 membership 和角色，第一次带有效 token 进来时按 email 匹配并写入 `idp_subject`。它更符合后台系统的真实流程（人是被邀请进来的，不是自己注册的），代价是要处理「认领时 email 不匹配」。学习阶段先做 JIT，因为它不依赖后台建人流程就能跑通；这两条路可以共存，`idp_subject` 可空正是为它们两个都留了位置
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
- 改 `app/core/config.py`：`logto_endpoint`、`logto_audience`（**不需要 `default_tenant_id`**——租户由 `memberships` 决定，没有「默认租户」这个概念）
- 改 `app/modules/users/service.py`：按 `idp_subject` 查或建本地用户（幂等），顺手刷新 email 快照
- 改 `app/main.py`：Swagger 安全方案
- 改 `tests/conftest.py`：`auth_client` 从「塞 header」改成「签自制 token」
- **不建 `app/modules/auth/`**：没有登录接口要写
- `modules/projects`、`modules/users` 的业务 service **不改**

**对应 Nest**

`passport-jwt` + `jwks-rsa` 换掉占位 Guard——是这个组合，而不是自己 `JwtModule.sign()`。业务代码无感知。

**过关标准**

第 3–13 步的测试**只改 conftest 里造身份的那一个 fixture** 就全部通过。过期 token 401；签名被换 401；`aud` 是别的 API 的 token 401；没有 `Authorization` 头 401；token 里塞 `tenant_id` 或 `organization_id` 不生效（租户仍然只由 `X-Tenant-Id` + 成员校验决定）；JIT 建出来的新用户能过认证但拿不到任何租户（403）。另外验一件事：**把 Logto 停掉，已经拿到的 token 仍然能用**——验签是本地的，这正是它比「每个请求回问 IdP」强的地方（代价是撤销不即时，靠短 token 缓解）。

**这一步不做**

自己写登录 / 注册 / 找回密码 / MFA / 社交登录（Logto 的活）、刷新令牌轮换和登出（前端 SDK + Logto 的活）、用 Management API 反向同步用户列表、webhook 接 `User.Created`、organizations 多租户、把 Logto 的 scope 当权限用。

---

## 第 15 步：上线前收口

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
- 进阶授权：数据范围（本人 / 本项目 / 本部门）、资源级 ACL、角色继承、权限集合的 Redis 缓存和跨实例失效、前端菜单树和按钮级权限码
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
| 自己的 `RolesController` + 权限表 | `modules/iam/` + `roles` / `role_permissions` / `membership_roles` |
| 多租户中间件 / CLS 里的 tenant | `X-Tenant-Id` + `memberships` 校验，落在 `deps.py` 一处 |
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

走完 0–16 步，你手里是一个**能上线但业务只有一个资源**的服务：底座是生产级的，身份和权限是完整的（多租户、租户内自定义角色），业务是最小的。之后按 02 的第 9 节往上长业务，底座不用重做。
