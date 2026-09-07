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

## Pydantic 2.13.5

V1 的方法和装饰器在 V2 里仍可导入，但都带 PEP 702 弃用标记，`mypy` 会逐条报错并给出替代写法，不需要在这里维护对照表。

唯一的例外是 `class Config`：静态检查完全沉默，只在运行时发 **`UserWarning`**（不是 `DeprecationWarning`）：

```
UserWarning: Valid config keys have changed in V2: 'orm_mode' has been renamed to 'from_attributes'
```

V2 的写法是 `model_config = ConfigDict(...)`。等 pytest 配置建起来后，用 `filterwarnings = ["error"]` 兜住这类——**只写 `error::DeprecationWarning` 会漏掉它**。
