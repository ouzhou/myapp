# 依赖笔记

主闸是类型检查器：`uv run mypy <路径>`。它开了 `deprecated` 错误码，能把 PEP 702 标注的旧版本 API 直接报成错误，并给出官方替代写法。**写完代码跑它，比查文档可靠。**

这个文件只记类型检查器**结构性抓不到**的东西，不重复它能报的：

- 语义过时但类型合法的 API（旧写法和新写法都能通过检查）
- 没有 `py.typed` 的包（检查器对它沉默）
- 跨库集成的弃用（只在运行时警告，不是类型错误）

选型决定写在 `project-conventions.mdc`，不在这里重复。包装上之后才记它，不提前写。

---

## Starlette 1.6.0 + TestClient

`fastapi.testclient.TestClient` 转发自 Starlette。Starlette 1.6 要求 **httpx2**；继续装 `httpx` 会在导入时发 `StarletteDeprecationWarning`。测试地基走 `uv add --dev pytest httpx2`，测试代码仍写 `TestClient`，不要直接 `import httpx2`。

类型检查器不会报这条弃用。导入 `TestClient` 时 Starlette 还会发一条 **anyio** 的 `DeprecationWarning`（`anyio.abc.BlockingPortal` 改到 `anyio.from_thread.BlockingPortal`），同样不是类型错误。第 4 步若 `filterwarnings = ["error"]`，两条都要处理，不要只转 `DeprecationWarning` 里的 httpx。

---

## FastAPI 0.141.1：`get_db` 的收尾 commit 跑在响应发出之后

带 `yield` 的依赖，退出段是在响应已经发送之后才 unwind 的。所以 `get_db` 里 `yield` 之后那句 `session.commit()` 失败时，客户端**已经拿到了成功响应**。实测让收尾抛异常：

```
status = 201
body   = {"code":0,"message":"ok","data":{"id":"8e818fb1-...", ...}}
```

500 handler 确实被调用了（日志里有 `unhandled error`），但响应已发送，它返回的 `JSONResponse` 被丢弃。客户端拿到 201 和一个 id，数据却被回滚了。

类型检查器和测试都抓不到这个：happy path 和现有用例全绿。现在能压住风险只是因为 service 每个写路径都 `flush()`，约束会在路由内先炸出来；剩下的暴露面是延迟约束、触发器、以及 commit 阶段连接断开。

**第 13 步（事务）要收口这个**：把 commit 提到响应序列化之前（route 级依赖或显式 UoW），而不是留在依赖退出段。在那之前不要新增「只在 commit 时才会违约」的约束。

同一条的推论：`logger.exception()` 在这个位置打出的是 `NoneType: None`——它读 `sys.exc_info()`，而收尾阶段那里已经清空。handler 里一律写 `logger.error(..., exc_info=exc)`，用传进来的异常对象。

---

## FastAPI 0.141.1：同一路由不能挂两个 Query 模型

`Annotated[SomeModel, Query()]` 在**只有一个**模型时会把字段摊成 `?page=&page_size=`。同一路径再挂第二个 Query 模型，FastAPI 不再摊平，而是把参数名当成必填查询键（`pagination` / `query`），缺省直接 422。

分页用 `Depends(pagination_params)`（每个字段自己 `Query()`），过滤/排序仍用一个 `Annotated[ProjectQuery, Query()]`。不要再给 `Pagination` 套一层 `Query()`。

类型检查器看不到这条，只有请求打过来才炸。

---

## FastAPI 0.141.1：sync `yield` 依赖里不要 `ContextVar.reset`

`def` 路由和它的 sync `yield` 依赖会被丢进线程池。`anyio` 进线程时 copy 一份 Context，依赖退出段再 copy 一次。`ContextVar.set` 拿到的 Token 和 `reset` 不在同一个 Context 里，直接：

```
ValueError: Token was created in a different Context
```

第 6 步只 `set`、不 `reset`。真正的绑定/清理放到第 15 步的异步中间件里做——那边跑在同一条 async Context 上。

类型检查器看不到这条。

---

V1 的方法和装饰器在 V2 里仍可导入，但都带 PEP 702 弃用标记，`mypy` 会逐条报错并给出替代写法，不需要在这里维护对照表。

唯一的例外是 `class Config`：静态检查完全沉默，只在运行时发 **`UserWarning`**（不是 `DeprecationWarning`）：

```
UserWarning: Valid config keys have changed in V2: 'orm_mode' has been renamed to 'from_attributes'
```

V2 的写法是 `model_config = ConfigDict(...)`。等 pytest 配置建起来后，用 `filterwarnings = ["error"]` 兜住这类——**只写 `error::DeprecationWarning` 会漏掉它**。

---

## Logto OSS 1.x：API resource access token 是 ES384

学习路径写的是 RS256。本机 `svhd/logto:1`（Console 1.43）发给 API resource 的 access token 是 **ES384**（`typ: at+jwt`），JWKS 里对应 EC 公钥。`jwt.decode` 的 `algorithms` 必须是白名单，只写 `RS256` 会把真 token 验成 401。测试仍用自制 RSA 签 RS256，所以白名单是 `RS256` 和 `ES384`，不要按 token header 里的 `alg` 动态选。
