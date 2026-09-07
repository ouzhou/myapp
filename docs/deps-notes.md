# 依赖笔记

主闸是类型检查器：`uv run mypy <路径>`。它开了 `deprecated` 错误码，能把 PEP 702 标注的旧版本 API 直接报成错误，并给出官方替代写法。**写完代码跑它，比查文档可靠。**

这个文件只记类型检查器**结构性抓不到**的东西，不重复它能报的：

- 语义过时但类型合法的 API（旧写法和新写法都能通过检查）
- 没有 `py.typed` 的包（检查器对它沉默）
- 跨库集成的弃用（只在运行时警告，不是类型错误）

选型决定写在 `project-conventions.mdc`，不在这里重复。包装上之后才记它，不提前写。

---

## Starlette 1.6.0 + httpx 0.28.1

**待决问题，会影响测试地基（学习路径第 4 步）。**

导入 `starlette.testclient` 时实测抛出：

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

`project-conventions.mdc` 定的是「pytest + httpx `TestClient`」，而 Starlette 1.6 已把 httpx 1.x 这条路标记为弃用、指向 `httpx2`。类型检查器不会报这个。写测试地基之前先定走哪条路，别等一批测试写完再换。

FastAPI 0.141.1 的 `TestClient` 转发自 Starlette，同一个问题。

---

## Pydantic 2.13.5

V1 的方法和装饰器在 V2 里仍可导入，但都带 PEP 702 弃用标记，`mypy` 会逐条报错并给出替代写法，不需要在这里维护对照表。

唯一的例外是 `class Config`：静态检查完全沉默，只在运行时发 **`UserWarning`**（不是 `DeprecationWarning`）：

```
UserWarning: Valid config keys have changed in V2: 'orm_mode' has been renamed to 'from_attributes'
```

V2 的写法是 `model_config = ConfigDict(...)`。等 pytest 配置建起来后，用 `filterwarnings = ["error"]` 兜住这类——**只写 `error::DeprecationWarning` 会漏掉它**。
