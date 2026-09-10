# 分片上传调研：OSS / S3，前后端怎么拆

面向本仓库后续的对象存储（[02-full-project-features.md](./02-full-project-features.md) 第 5 节：对象存储是完整项目，直传是按需）。学习路径第 11 步仍是本地落盘，`app/infra/storage/` 的 `save / open / delete` 不够覆盖分片直传，直传时业务模块不应再把文件字节送进 FastAPI。

结论先说：**浏览器大文件不要过后端。后端只鉴权、定 object key、签单或发 STS、完成后落库；字节走 OSS/S3。** S3 和 OSS 的分片协议几乎同构，可以一套接口切驱动。

---

## 1. 协议：两边都是三步

S3 和 OSS 都把一个对象拆成多个 Part，独立上传，最后按 **part number**（不是上传顺序）拼成对象。

| 步骤 | S3 | OSS |
|---|---|---|
| 初始化，拿到 `uploadId` | `CreateMultipartUpload` | `InitiateMultipartUpload` |
| 上传每一片 | `UploadPart`（`partNumber` + `uploadId`） | `UploadPart` |
| 提交 Part 列表（number + ETag）拼对象 | `CompleteMultipartUpload` | `CompleteMultipartUpload` |
| 取消并删已传碎片 | `AbortMultipartUpload` | `AbortMultipartUpload` |
| 列出已传 Part | `ListParts` | `ListParts` |

依据：[S3 Multipart Upload Overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)、[OSS 分片上传](https://www.alibabacloud.com/help/en/oss/user-guide/multipart-upload)、[S3 CreateMultipartUpload](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateMultipartUpload.html)、[OSS InitiateMultipartUpload](https://www.alibabacloud.com/help/en/oss/developer-reference/initiatemultipartupload)。

S3 写明：multipart 的每一跳都是普通请求，**各自单独签名**，没有特殊的「会话签名」；匿名用户不能 init。[CreateMultipartUpload](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CreateMultipartUpload.html)

Complete 时必须带自己记下的 `(partNumber, ETag)` 列表，**不要用 ListParts 的结果去 Complete**。[S3 MPU overview](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)

同一 `partNumber` 再传一次会覆盖旧 Part。[S3 UploadPart](https://docs.aws.amazon.com/AmazonS3/latest/API/API_UploadPart.html)、[OSS UploadPart](https://www.alibabacloud.com/help/en/oss/developer-reference/uploadpart)

---

## 2. 限制对照（选 partSize 时用）

两边都建议：**≥ 100 MB 才走分片**，更小的用单次 PUT。[S3 qfacts](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html)、[OSS Browser.js 分片上传](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)

| | S3 | OSS |
|---|---|---|
| 建议门槛 | 100 MB | 100 MB |
| 最大对象 | 48.8 TiB | 48.8 TB |
| Part 个数 | 1–10,000 | 1–10,000 |
| 非最后一片最小 | Complete 时校验，小于 5 MB 会 `EntityTooSmall` | 100 KB（UploadPart 时不校验，Complete 时才校验） |
| 单 Part 最大 | 文档表未在本次摘录里给全；SDK 示例常用 5 MB 起 | 5 GB |
| 最后一片 | 无最小限制 | 允许 &lt; 100 KB |
| 未 Complete / Abort 的碎片 | 继续计存储费；应用 lifecycle `AbortIncompleteMultipartUpload` | 继续计费；必须 Abort 或控制台/工具清碎片 |

依据：[S3 qfacts](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html)、[S3 CompleteMultipartUpload `EntityTooSmall`](https://docs.aws.amazon.com/AmazonS3/latest/API/API_CompleteMultipartUpload.html)、[OSS UploadPart](https://www.alibabacloud.com/help/en/oss/developer-reference/uploadpart)、[OSS 分片上传 Limits / 清理碎片](https://www.alibabacloud.com/help/en/oss/user-guide/multipart-upload)、[S3 abort incomplete lifecycle](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html)。

实践上的 partSize：

- 要对齐 S3 时用 **≥ 5 MiB**（例如 8 或 16 MiB），OSS 也能吃。
- 纯 OSS 可用 1 MiB（Browser.js SDK 默认 1 MB，最小 100 KB）。[OSS Browser.js](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)
- 片数 = `ceil(size / partSize)`，必须 ≤ 10,000。10 GB 文件用 8 MiB 大约 1280 片，没问题。

---

## 3. 三种落地方式

### A. 后端中转（不推荐做大文件）

浏览器把片 POST 到 FastAPI，FastAPI 再用 boto3 / oss2 调 `UploadPart`。

- 后端能扫毒、能严格限类型。
- API 进程吃带宽和内存；和本仓库「边读边计数、别 `await file.read()` 整文件进内存」同一类风险。
- 适合：服务端自己产生的文件（worker 导入、转码结果），不适合标注员从浏览器传视频。

服务端 SDK 已经封装好了：boto3 `upload_file` + `TransferConfig(multipart_threshold=...)` 自动切分；oss2 `resumable_upload` / 手写 `init_multipart_upload` + `upload_part` + `complete_multipart_upload`。[boto3 TransferConfig](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3.html)、[OSS Python SDK V1 示例](https://www.alibabacloud.com/help/en/oss/user-guide/multipart-upload)

### B. 前端直传 + 每片预签名 URL（推荐作为 S3/OSS 统一方案）

后端拿着长期密钥，只签发短时 URL；浏览器对 OSS/S3 发 PUT，字节不进 API。

```
前端                FastAPI                         OSS / S3
 |-- POST /uploads/init ---------------------------> CreateMultipartUpload
 |<-- { uploadId, key, partSize } --|
 |-- GET  /uploads/{id}/parts?n=1..N -------------> generate_presigned_url(upload_part)
 |<-- [url1, url2, ...] ------------|
 |-- PUT url_i  body=file.slice(...) -------------> UploadPart
 |<-- ETag -------------------------|
 |-- POST /uploads/{id}/complete { parts } -------> CompleteMultipartUpload
 |                                  |-------------> HeadObject 校验 size
 |                                  |-------------> 写 files 表
```

boto3 签单片：

```python
s3.generate_presigned_url(
    ClientMethod="upload_part",
    Params={"Bucket": bucket, "Key": key, "UploadId": upload_id, "PartNumber": n},
    ExpiresIn=3600,
)
```

`upload_file` 不能拿来 generate_presigned_url（那是高层封装，不是 Client API）。单文件直传用 `put_object` 或 `generate_presigned_post`。[boto3 presigned URLs](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-presigned-urls.html)、[S3 PUT presigned](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)、[boto3 issue #3708 的 upload_part 签法](https://github.com/boto/boto3/issues/3708)

预签名有效期：SDK 最长 7 天；用 STS/角色签出来的 URL，到期时间还要被凭证自己的过期截断。[S3 presigned URL expiration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)

优点：浏览器里没有云厂商密钥；key / Content-Type / 前缀全由后端定；OSS 开 S3 兼容或两边各写一个 signer 即可。

缺点：片数多时要签很多 URL（可一次批量签，或按窗口签下一批）；浏览器必须能读到响应头 `ETag`（见 CORS）。

### C. 前端 SDK + STS 临时凭证（OSS 官方推荐的浏览器路径）

后端 AssumeRole / 换 STS（AccessKeyId + Secret + SecurityToken，权限收窄到 `oss:PutObject` 且 Resource 限制到 `tenant_id/` 前缀）。前端：

```js
const client = new OSS({
  region, authorizationV4: true,
  accessKeyId, accessKeySecret, stsToken, bucket,
})
await client.multipartUpload(objectKey, file, {
  parallel: 4,
  partSize: 1024 * 1024,
  progress: (p, checkpoint) => { /* 把 checkpoint 存 localStorage */ },
})
```

`multipartUpload` 内部就是 Initiate → 并发 UploadPart → Complete。断点：把 `checkpoint` 再传进去即可续传；`client.cancel()` 暂停，`abortMultipartUpload(name, uploadId)` 放弃。[OSS Browser.js 分片](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)、[OSS Browser.js 断点续传](https://www.alibabacloud.com/help/en/oss/developer-reference/resumable-upload-9)

S3 对等物：浏览器拿临时凭证，用 [`@aws-sdk/lib-storage` 的 `Upload`](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpu-upload-object.html)。

官方硬性要求：

- **禁止把长期 AccessKey 放进浏览器**。[OSS Browser.js](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)
- Bucket 必须配 CORS；且 ExposeHeaders 要包含 `ETag` 和 `x-oss-request-id`，否则 SDK 报 `PLease set the etag of expose-headers`。[OSS Browser.js FAQ](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)

优点：续传、并发、进度都是 SDK 的事；前端代码短。

缺点：浏览器持有（虽短时）能写该前缀的凭证，策略必须锁死 key 前缀和动作为 Put；绑死厂商 SDK；Complete 发生在浏览器，后端要靠回调或前端再调「确认」才能落库。

---

## 4. 后端（FastAPI）该做什么

不管 B 还是 C，API 都不接收文件字节。对照本仓库现有规矩：

| 职责 | 做法 |
|---|---|
| 鉴权 / 租户 | 现有 `CurrentUser` + `require_perm`；上传权限点以后加 |
| object key | 服务端生成 `{tenant_id}/{uuid}`，原名只进 DB 展示字段（第 11 步已定，直传同样适用） |
| 大小 / 类型 | init 时就要申报 `size` + 声明的 mime；part 数超限直接拒签。真实类型仍只能 Complete 后 HeadObject / 抽头部字节再验，**不要信客户端 Content-Type** |
| 会话状态 | DB 记 pending：`upload_id`、`key`、`size`、`part_size`、`status`。Complete 成功再插 `files` 行 |
| 签单或发 STS | 只签当前用户、当前 key、当前 uploadId；不要签任意 key |
| Complete | 校验 parts 升序、片数匹配、可选 `x-amz-mp-object-size` / HeadObject Content-Length |
| Abort | 用户取消或过期任务调 Abort，避免碎片计费 |
| 副作用 vs 事务 | 对象已经在桶里了，DB rollback 不会删对象。和本地落盘一样：commit 后再认文件，配孤儿清理 |

`app/infra/storage/` 需要从 `save/open/delete` 扩成大约：

- `presign_put(key, content_type, expires)` — 小文件
- `create_multipart(key, content_type) -> upload_id`
- `presign_upload_part(key, upload_id, part_number) -> url`
- `complete_multipart(key, upload_id, parts)`
- `abort_multipart(key, upload_id)`
- `head(key) / delete(key) / presign_get(key)`

S3 驱动用 boto3；OSS 用官方 Python SDK，或 OSS 的 S3 兼容 endpoint 继续用 boto3（切换成本最低，行为以兼容层为准）。

业务模块（`modules/files`）只调这套接口，不 import boto3/oss2。

桶侧还要配：

1. CORS：允许前端 origin、`PUT`/`POST`/`GET`/`HEAD`，Expose `ETag`。
2. 生命周期：N 天后 abort 未完成 multipart。
3. 私有桶 + 下载也走短时 GET 签名，不裸链（功能清单第 5 节）。

---

## 5. 前端（React）该做什么

小文件（&lt; 100 MB）：要一张 PUT 预签名，`fetch(url, { method: "PUT", body: file, headers: { "Content-Type": 签发时同一个 } })`。Content-Type 必须和签名时一致，否则 `SignatureDoesNotMatch`。[S3 PUT presigned troubleshooting](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)

大文件，方案 B（自管分片）：

```ts
const partSize = 8 * 1024 * 1024
const parts: { partNumber: number; etag: string }[] = []
for (let i = 0; i < Math.ceil(file.size / partSize); i++) {
  const blob = file.slice(i * partSize, Math.min(file.size, (i + 1) * partSize))
  const res = await fetch(urls[i], { method: "PUT", body: blob })
  const etag = res.headers.get("ETag")
  if (!etag) throw new Error("missing ETag — check CORS ExposeHeaders")
  parts.push({ partNumber: i + 1, etag })
}
await api.completeUpload(uploadId, parts)
```

要点：

- `File.slice` 是零拷贝视图，不要 `FileReader.readAsArrayBuffer` 把整片读进大 ArrayBuffer 再发。
- 并发 3–4 片即可，和 OSS SDK 默认 `parallel: 4` 同量级。
- 失败只重试那一片（同一 partNumber 覆盖）。
- 刷新后续传：把 `uploadId` + 已成功的 partNumber 存下来，向后端 ListParts 或自己记的列表对齐后再签缺失片。
- 取消：调后端 Abort，不要只停 fetch。

大文件，方案 C：`npm install ali-oss`（或 `@aws-sdk/lib-storage`），STS 从后端接口拿，过期前刷新。进度和 checkpoint 走 SDK 回调。

无论 B/C，Complete 成功后都要让后端写入 `files` 记录，前端再拿文件 id 去挂项目/数据集。不要假设「桶里有对象 = 业务上已上传」。

---

## 6. 对本仓库的建议

功能清单已经把路径画好了：第 11 步本地 `save`；完整项目换对象存储；直传按需。分片直传就是把「按需」做实。

建议默认走 **B（每片预签名）**：

- 同时覆盖 OSS 和 S3，前端不绑 `ali-oss`。
- 密钥不出浏览器，和现有「后端签单、私有桶」一致。
- 存储适配层扩接口即可，`modules/files` 仍是唯一业务入口。

若确定只上阿里云、且要开箱断点续传，再在前端加 C 作为 OSS 专用实现，后端改为发 STS 而不是签 URL。两套不要混在同一条上传链路上。

不要做的：

- 大文件走 FastAPI multipart（`python-multipart` 那条是小文件学习切片）。
- 用用户文件名当 key。
- 不 Abort、不配 lifecycle，让碎片一直计费。
- 前端自己选任意 object key。
- Complete 时在请求里改存储类型（OSS：必须在 Initiate 时设，Complete 再设会报 *The operation is not supported for this resource*）。[OSS Browser.js FAQ](https://help.aliyun.com/zh/oss/developer-reference/multipart-upload-11)

---

## 7. 和现有学习路径的衔接

第 11 步过关标准不变（小图、拒超大、拒伪造扩展名、租户隔离）。对象存储和直传仍是第 11 步明确不做的。真正加的时候：

1. 先扩 `infra/storage` 接口 + S3 或 OSS 驱动，本地驱动继续给测试用 `tmp_path`。
2. 小文件预签名 PUT 打通 CORS / 落库。
3. 再加 multipart init / part-url / complete / abort。
4. 前端按 size 分流。
5. 生命周期清理 + 孤儿对象扫描。
