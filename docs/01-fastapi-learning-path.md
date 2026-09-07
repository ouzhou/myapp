# FastAPI 学习流程

面向已经会 NestJS 的人。目标不是一次做成生产系统，而是按顺序长出代码：每一步都能在 `/docs` 里点通，再进入下一步。

原则：

- 先有能跑的接口，再补横切能力。
- 先挖缝（seam），再换实现。JWT、日志、真登录都是替换，不是推翻。
- 生产启动顺序是 JWT → 用户 → 守卫 → 业务。学习顺序相反：业务 → 信封 → 用户缝 → 守卫 → 再把 JWT 插进缝里。

技术选型（学习阶段固定，避免来回换）：

| 用途 | 选择 | 原因 |
|---|---|---|
| Web | FastAPI | 当前项目 |
| DTO / 校验 | Pydantic v2 | 对应 Nest DTO + class-validator |
| ORM | SQLAlchemy 2.0 | Entity 和 DTO 分开，接近 TypeORM |
| 迁移 | Alembic | 没有迁移就没有模型版本 |
| 配置 | pydantic-settings | 对应 ConfigModule |
| 授权 | Casbin（先文件策略） | 先学「怎么问策略」，后学「策略怎么存」 |

不要一上来用 SQLModel。它把 Entity 和 DTO 糊在一起，和 Nest 里养成的分层是反的。

---

## 总览

```text
0   骨架 / settings / health
1   DB session + Alembic + 探活 health
2   第一个资源 CRUD + 软删除字段
3   统一信封 + 校验错误 + 409 + 序列化脱敏
4   列表：分页 + 白名单 filter/sort
5   CurrentUser 缝（header 假用户）
6   租户落在查询上
6.5 操作审计日志
7   Seed 用户/角色/策略 → Casbin 守卫
7.5 用户资源 + /me（仍可不解 JWT）
8   文件上传
8.5 跨表事务
9   JWT 替换 CurrentUser
10  应用日志
```

每一步都写五件事：**做什么、写到哪些文件、对应 Nest 什么、过关标准、这一步刻意不做**。

文件路径以 [03-project-structure.md](./03-project-structure.md) 为准。本文件管顺序，那份管目录；内容没变，只是每一步长到同一棵树上。按步建文件，不要提前建空包。

FastAPI 没有 Nest 那种模块化 DI 容器。不要复刻 `providers` / `Module`。按「路由 → 服务 → ORM」三层即可。Guards、当前用户、DB Session、Casbin、JWT，全部是 `Depends`。

---

## 第 0 步：能启动的骨架

**做什么**

- 用工厂函数创建 app，挂 `lifespan`（启动/销毁）。
- 用 `pydantic-settings` 读环境变量，先只放应用名、环境、后面要用的 `DATABASE_URL`。
- 用 `APIRouter` 按模块挂载。
- 留一个 `GET /health`，先返回静态 `{ "status": "ok" }`。

**写到哪些文件**

- `app/main.py`：`create_app()`、`lifespan`
- `app/core/config.py`：Settings
- `app/api/router.py`：只 `include_router`
- `app/modules/health/router.py`：health 接口

**对应 Nest**

`main.ts` + `ConfigModule` + 根模块里 `imports` 各个 Controller。

**过关标准**

`uv run fastapi dev` 能起来，打开 `/docs`，health 能点通。

**这一步不做**

业务路由、数据库、统一返回信封。

---

## 第 1 步：DB Session + 迁移 + 探活

**做什么**

- 配置 SQLAlchemy engine 和 session factory。
- 写 `get_db()`：`yield` session，请求结束自动关闭。这是 FastAPI 版的「请求作用域 provider」。
- 接入 Alembic。模型变更只走迁移，不靠删库重建。
- 做一个 `TimestampMixin`：`id`、`created_at`、`updated_at`。
- 把 `/health` 改成真探活：能连上数据库才算健康。

**写到哪些文件**

- `app/db/session.py`：engine、`get_db()`
- `app/db/base.py`：`DeclarativeBase`、`TimestampMixin`（软删 mixin 也可以一起放）
- `alembic.ini`、`alembic/`：迁移
- 改 `app/modules/health/router.py`：探数据库
- 这一步还没有 `app/deps.py`。health 先直接依赖 `get_db`，第 5 步再包成 `DbSession`

**对应 Nest**

`TypeOrmModule.forRoot` + 请求作用域 provider + TypeORM migration + `TerminusModule` 的 TypeORM health indicator。

**过关标准**

空库跑一次迁移成功；health 在数据库关闭时失败，打开时成功。

**这一步不做**

业务表可以还没有。先让「连库 + 迁移」这条管子通。

---

## 第 2 步：第一个资源的 CRUD + 软删除字段

**做什么**

只做一个资源，例如「标注项目」。四个 DTO 分开：

- `XxxCreate`
- `XxxUpdate`
- `XxxRead`
- `XxxQuery`（列表查询参数，这一步可以很薄）

分层：

- 路由：校验入参、调 service、返回。
- Service：业务。
- Model：只描述表。

模型上带 `deleted_at`。删除走软删。这一阶段返回值可以先是 Pydantic 对象，先不要追求完美信封。

**写到哪些文件**

- `app/modules/projects/router.py`
- `app/modules/projects/schemas.py`
- `app/modules/projects/models.py`
- `app/modules/projects/service.py`
- 改 `app/api/router.py`：挂上 projects
- 软删字段用 `app/db/base.py` 的 mixin，不要每个表手写一遍
- 查询先写在 service 里，不要新建 `repository.py`

**对应 Nest**

Controller + Service + Entity + DTO；软删除对应 TypeORM `@DeleteDateColumn`。

**过关标准**

增删改查在 Swagger 里都能走通；删除后普通列表看不到，数据库行还在。

**这一步不做**

统一信封、权限、JWT、完美的通用查询器。

---

## 第 3 步：统一返回 + 统一错误 + 序列化脱敏

**做什么**

约定一种信封，成功和失败同一张皮：

```json
{ "code": 0, "message": "ok", "data": {} }
```

```json
{ "code": 40001, "message": "项目不存在", "data": null, "details": [] }
```

三处错误都收进同一套 handler：

| 来源 | 处理 |
|---|---|
| 参数校验失败 | 捕获 `RequestValidationError` |
| 业务错误 | 自定义 `AppError` + `exception_handler` |
| 未处理异常 | 捕获 `Exception`，对外只给通用信息 |
| 唯一索引冲突 | 捕获数据库完整性错误，转成 409 |

同时做两件小事：

- `request_id`：从 header 读或生成，放进错误体。这是协议字段，不是日志系统。
- 序列化脱敏：读库结果必须变成 `XxxRead`，禁止直接 `return entity`。密码、内部字段、软删标记默认不出站。

**写到哪些文件**

- `app/core/exceptions.py`：`AppError` 和各类 handler
- `app/core/response.py`：统一信封
- 改 `app/main.py`：注册 handler
- 改 `app/modules/projects/service.py`：业务失败抛 `AppError`
- 改 `app/modules/projects/router.py`：只返回信封和 Read DTO

**对应 Nest**

全局 `ExceptionFilter` + 包装返回的 Interceptor + `ClassSerializerInterceptor` + 把 `QueryFailedError` 转 409。

**过关标准**

故意传错参数、查一个不存在的 id、创建一个重名项目：三种响应形状和成功时一样；响应里看不到实体内部字段。

**这一步不做**

结构化日志框架。`request_id` 先挂在信封上即可。

---

## 第 4 步：列表查询（分页 + 白名单 filter/sort）

**做什么**

后台第一个真实痛点通常是列表，不是单条 CRUD。做成通用能力：

- `PageResult[T]`：`items`、`total`、`page`、`page_size`
- `pagination_params` 依赖
- 过滤、排序走白名单，不要把前端字段直接拼进 SQL
- 默认过滤已软删数据

不要复刻完整的 `@nestjsx/crud`。只要 filter / sort / page 三件套，每个资源声明自己允许哪些字段。

**写到哪些文件**

- `PageResult`、分页参数放进 `app/core/response.py`（或同目录一个小文件，不要新开顶层包）
- 过滤/排序白名单写在 `app/modules/projects/schemas.py` 的 Query DTO
- 拼查询仍在 `app/modules/projects/service.py`

**对应 Nest**

`@nestjsx/crud` 的 query 协议（filter、sort、page），但只取其受控的那一部分。

**过关标准**

列表返回 `items + total + page`；非法排序字段被拒绝；软删数据默认不出现。

**这一步不做**

任意 join、任意 select、把查询语言做成前端万能协议。

---

## 第 5 步：CurrentUser 缝（先不解析 JWT）

**做什么**

先定义接口，再写假实现：

```text
CurrentUser = { user_id, tenant_id, roles[] }
```

第一版从 header 读，例如 `X-User-Id`、`X-Tenant-Id`。  
Service 只依赖 `CurrentUser`，不依赖 header，更不依赖 JWT。

这是整条学习路径里最重要的缝。后面的租户、审计、Casbin、JWT 都插在这里。

**写到哪些文件**

- `app/core/context.py`：`CurrentUser` 数据结构
- `app/deps.py`：从 header 组装 `CurrentUser`，并把 `get_db` 包成 `DbSession`
- 改 `app/modules/projects/router.py`：注入 `CurrentUser`
- 改 `app/modules/projects/service.py`：接收 `CurrentUser`，不要自己读 header

**对应 Nest**

先挂一个占位 Guard / `@Req()` 上的 user，再换 Passport 策略。FastAPI 里就是换一个 `Depends`。

**过关标准**

Service 里能用到 `user_id`、`tenant_id`；换一组 header，数据跟着变。

**这一步不做**

解析 Bearer Token、登录接口、密码校验。

---

## 第 6 步：租户落在查询上

**做什么**

只在下层「拿得到 tenantId」还不够。规则尽早定死：

- 所有业务表带 `tenant_id`
- 查询默认带租户条件
- 创建时自动写入当前租户
- 跨租户直接 404，不要 403（避免探测）

仍然不需要 JWT。Header 里的假用户就够练。

**写到哪些文件**

- 改 `app/modules/projects/models.py`：加 `tenant_id`，再出一条 Alembic
- 改 `app/modules/projects/service.py`：查、改、删都带租户条件
- 不要新建 repository；租户条件先集中在这一个 service 里

**对应 Nest**

多租户中间件 / CLS + 在 repository 里默认加 tenant 条件。本项目没有 repository，条件写在 service。

**过关标准**

租户 A 的数据，用租户 B 的 header 看不到、改不了。

**这一步不做**

每租户一个数据库、动态切连接串。

---

## 第 6.5 步：操作审计日志

**做什么**

这不是 access log。记的是业务动作：

- 谁（user_id）
- 在哪个租户
- 对哪个资源、哪条 id
- 做了 create / update / delete
- 改前 / 改后（可以先做精简字段）
- request_id、IP（有就记）

第一版可以在 service 写库，不必上事件总线。写审计失败不能把主流程打挂，但开发期要能看见失败原因。

**写到哪些文件**

- `app/modules/audit/models.py`：审计表
- `app/modules/audit/service.py`：一个写入函数即可，不必先做完整 CRUD
- 改 `app/modules/projects/service.py`：写操作后调用审计
- 审计还没有对外路由，不要挂到 `api/router.py`

**对应 Nest**

Audit Interceptor + 一张 audit 表。它依赖当前用户，不依赖日志框架。

**过关标准**

改一条项目，审计表多一行；能对上 user_id 和资源 id。

**这一步不做**

回滚到历史版本、完整 diff UI、把审计和 stdout 日志混成一套。

---

## 第 7 步：Seed + Casbin 守卫

**做什么**

先 seed，再写守卫。否则你在测空气。

Seed 最少准备：

- 一个管理员、一个普通用户
- 角色
- Casbin 策略（先用 `rbac_model.conf` + `policy.csv`）

守卫分两层，不要一上来全塞进 Casbin：

1. 认证依赖：没有 `CurrentUser` 就 401（现在检查 header，以后检查 JWT）
2. 授权依赖：`require_perm("project", "write")`，内部问 Casbin

**写到哪些文件**

- `app/infra/casbin/model.conf`、`policy.csv`、`enforcer.py`
- `app/core/permissions.py`：`require_perm(...)`
- `app/db/seeds.py` 或 `scripts/seed.py`：管理员、普通用户
- 改 `app/modules/projects/router.py`：路由上挂认证/授权 Depends

**对应 Nest**

`Guard` + Casbin / RBAC module + 数据库 seed。FastAPI 的 Guard 是「依赖失败就抛」，不是返回 boolean。

**过关标准**

同一个接口，换角色 header，一个 200、一个 403。换一套 seed 策略，结果跟着变。

**这一步不做**

策略存数据库、权限管理后台、动态菜单树。

---

## 第 7.5 步：用户资源 + `/me`

**做什么**

补上「用户」这个资源，仍然可以不解 JWT：

- 用户表（归属租户、角色、状态）
- 管理员对用户的 CRUD（受 Casbin 保护）
- `GET /me`：返回当前 `CurrentUser` 对应的资料

Header 假用户此时应能对上 seed 出来的用户 id。`/me` 放在 users 模块，此时还没有 auth 模块。

**写到哪些文件**

- `app/modules/users/{router,schemas,models,service}.py`
- 改 `app/api/router.py`：挂上 users
- seed 改成写入这张用户表，header 里的 user id 要对得上

**对应 Nest**

User module + 当前用户接口。它是 Casbin 的数据来源，不是 JWT 的附属品。

**过关标准**

用管理员 header 能建用户；`/me` 能返回当前假用户；普通角色不能建用户。

**这一步不做**

登录、密码哈希、刷新令牌。

---

## 第 8 步：文件上传

**做什么**

做一个最小可用的上传切片，服务标注业务：

- 接收 multipart 文件
- 校验类型和大小
- 先落到本地磁盘（对象存储以后再换）
- 落一条文件记录：文件名、路径、uploader、tenant_id、资源关联（可选）

这是第二个垂直切片。有了它，后面的数据集导入才有地方放。

**写到哪些文件**

- `app/infra/storage/local.py`：落盘，以后换 S3 只改这里
- `app/modules/files/{router,schemas,models,service}.py`
- 改 `app/api/router.py`：挂上 files

**对应 Nest**

`FileInterceptor` / Multer；boilerplate 里常见的 local + S3 双驱动，学习期只做 local。

**过关标准**

Swagger 能上传一张图或一个 zip；用别的租户 header 看不到这条文件记录。

**这一步不做**

S3、图片转码、断点续传、直传签名。

---

## 第 8.5 步：跨表事务

**做什么**

选一个真实的跨表写：例如「创建项目 + 写入默认标签集」，或「上传文件 + 创建文件记录 + 挂到项目」。

整段放进同一个 SQLAlchemy session/transaction。失败则全部回滚，审计日志要么一起进事务，要么明确「主事务成功后再记」。

**写到哪些文件**

- 不新开目录。改已有 `modules/projects/service.py`（或 files 的 service）
- 默认标签如果只是项目附属，表可以先放在 `modules/projects/models.py`

**对应 Nest**

`@Transactional` / QueryRunner。

**过关标准**

人为让第二步失败（重复标签名等），项目行不会留下半成品。

**这一步不做**

分布式事务、跨服务 saga。

---

## 第 9 步：JWT 替换 CurrentUser

**做什么**

只改 CurrentUser 这一个依赖。Router / service / Casbin / 审计尽量一行不改。

JWT 里读出 `sub`、`tenant_id`、`roles`，填进现有的 `CurrentUser`。Header 假实现留在测试或开发开关里。

可以顺手加上：

- `POST /auth/login`（校验用户表密码，签发 token）
- Swagger 的 Bearer 安全方案

刷新令牌、登出黑名单可以不做。

**写到哪些文件**

- `app/modules/auth/{router,schemas,service}.py`：登录
- `app/core/security.py`：签发/校验 JWT、密码哈希
- 改 `app/deps.py`：CurrentUser 改为读 Bearer，header 假实现留作开发开关
- 改 `app/api/router.py`、`app/main.py`：挂登录、Swagger Bearer
- `modules/projects` 和 `modules/users` 的 service **不改**

**对应 Nest**

Passport JWT 策略替换占位 Guard。业务代码无感知。

**过关标准**

用真 token 走通原来的 CRUD 和 `/me`；Service 代码无感知。Header 假用户可关。

**这一步不做**

社交登录、2FA、SSO、完整刷新令牌体系。

---

## 第 10 步：应用日志

**做什么**

现在才上结构化日志。此时已经有 `request_id`、`user_id`、`tenant_id`，日志终于有东西可绑。

只做这些：

- JSON 或结构化输出（标准 logging 或 structlog）
- 请求开始/结束：方法、路径、状态码、耗时
- 业务异常 warning，未知异常 exception
- 自动带上 `request_id` / `user_id` / `tenant_id`

**写到哪些文件**

- `app/core/logging.py`：配置
- 改 `app/main.py`：挂中间件或 lifespan 里初始化
- 不要和 `modules/audit` 混进同一个文件

**对应 Nest**

Pino / Winston + 请求日志中间件。和操作审计仍然分开：一个给开发排障，一个给后台追责。

**过关标准**

一次失败请求的日志能对上响应里的 `request_id`。

**这一步不做**

完整可观测平台、链路采样、ELK、指标大盘。

---

## 学习阶段明确不做

这些会把「先跑起来」拖死，放到《完整项目功能》里：

- Redis / 缓存
- Celery / 后台任务 / 定时任务
- Casbin 策略存库和权限管理后台
- 刷新令牌、SSO、完整注册登录产品化
- 对象存储、WebSocket 协同
- 邮件、i18n、限流、安全头（Helmet）
- Docker / CI 完善、全量测试金字塔

标注业务本身（数据集、预标注、质检流）当作第 2 步之后的「下一个资源」往上叠，不要和第 0–3 步的框架学习缠在一起。

---

## NestJS → FastAPI 对照

| NestJS | FastAPI |
|---|---|
| `Module` | 包 + `APIRouter` |
| `Controller` | `APIRouter` 上的函数 |
| `Injectable` Service | 普通 class / 函数，用 `Depends` 组装 |
| DTO + `class-validator` | Pydantic v2 |
| Entity + TypeORM | SQLAlchemy 2.0 model |
| `ExceptionFilter` | `exception_handler` |
| Interceptor（包装返回） | 统一返回模型 / 小工具函数 |
| `ClassSerializerInterceptor` | 强制走 Read DTO |
| `Guard` | 会 `raise` 的 `Depends` |
| `@Req()` / CLS | `Depends` + `ContextVar` |
| `ConfigModule` | `pydantic-settings` |
| Passport JWT | 一个 `Depends`，替换 CurrentUser |
| `TerminusModule` | health 里探数据库 |
| Multer | `UploadFile` |
| `@Transactional` | `session.begin()` / 同一 session 提交 |
| Audit Interceptor | service 写审计表，后期可改事件 |

---

## 怎么用这份文档

一次只做一步。做完看「过关标准」，通过再往下。不要跳步去写 JWT 或日志。文件不知道放哪时查 [03-project-structure.md](./03-project-structure.md)，不要另开一套目录。

完整系统还要哪些能力，看 [02-full-project-features.md](./02-full-project-features.md)。那份清单里标了「学习路径已覆盖」和「完整项目再做」。
