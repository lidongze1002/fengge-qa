# 架构与技术细节

## 1. 总体结构

整套系统分三层：**离线数据流水线**、**在线检索服务**、**前端展示**。

```
src/fengge/
├── discover.py     B 站投稿发现（wbi 签名、分页）
├── download.py     yt-dlp 下载 + 风控处理
├── asr.py          faster-whisper 转写
├── transcode.py    ffmpeg 归档（裁切 + 校验）
├── structure.py    LLM 从转写里抽问答
├── filter.py       内容过滤 / 去重
├── export.py       导出 jsonl + 报告 + 抽检表
├── retrieval.py    BM25 + 向量 + RRF 融合
├── query.py        提问改写 / 复核 prompt
├── embed.py        本地 fastembed / OpenAI embedding
├── server.py       FastAPI
└── pipeline.py     状态机驱动五个阶段
```

## 2. 数据流水线

### 2.1 状态机

每条投稿在 `data/state.db`（SQLite）里一行，`state` 字段推进：

```
discovered → downloaded → asr_done → archived → accepted / rejected
```

| 状态 | 含义 | 谁写入 |
|---|---|---|
| `discovered` | 投稿已入表，还没下载 | `discover` |
| `downloaded` | 视频落盘，时长已校验 | `download` |
| `asr_done` | 音频转写完成，`data/asr/*.json` | `asr` |
| `archived` | 被裁成 ≤600 秒的片段并转码归档 | `archive` |
| `accepted` / `rejected` | LLM 抽问答的结果 | `structure` |

约束：`structure` **只消费 `archived`**，保证数据集里不会出现「有问答但没视频」。

所有阶段幂等：中断后重跑跳过已完成的行。`attempts` 计数 + `last_error` 记录，
失败 3 次后停在 `failed`，不再无限重试。

### 2.2 各阶段要点

| 阶段 | 关键设计 |
|---|---|
| `discover` | B 站 `space/wbi/arc/search` 需要 wbi 签名（`w_rid = md5(query + mixin)`），用浏览器登录态取 cookie |
| `download` | yt-dlp 单线程 + 3~6 秒随机间隔；连续 3 次 403 抛 `RateLimited` 整批停机（主号被限没有退路） |
| `asr` | faster-whisper large-v3，GPU + VAD 过滤；显存不够自动回 CPU int8 |
| `archive` | 只保留 ≤600 秒；ffmpeg 转码后校验时长 ±0.5s，通过才删原始文件 |
| `structure` | DeepSeek 从逐句转写里抽「问题 + 回答要点 + 金句」；抽不出就 `rejected` |

### 2.3 归档阶段的队列饿死 bug（已修）

归档查询原本是 `state IN ('asr_done','rejected') LIMIT 120`。
`rejected` 归档后**状态仍是 rejected**（只写了 `clip_path`），下一轮又会被同一条 SQL
捞出来，再被 Python 层过滤掉——每轮有 100+ 个名额被这些已完成的行白占。

结果：ASR 每轮产出 120 条，归档只能处理 7~24 条，`asr_done` 越积越多。

修法是把过滤下推到 SQL：

```sql
AND (clip_path IS NULL OR clip_path = '')
```

## 3. 检索链路

```
用户提问
  → ① LLM 改写成 3 条不同问法（口语/抽象/关键词）
  → ② 每条分别跑「向量检索」和「BM25」，用 RRF 融合排名
  → ③ 取 top-k 交给 LLM 复核：这段到底有没有正面回答？
  → ④ answers / partial / no，no 就明确拒答
```

| 环节 | 取值 |
|---|---|
| 向量模型 | `BAAI/bge-small-zh-v1.5`（fastembed，ONNX，CPU 也能跑） |
| 融合 | RRF（Reciprocal Rank Fusion，k=60） |
| 判定阈值 | 0.62 |
| 复核模型 | DeepSeek（`deepseek-chat`） |

**为什么加 LLM 复核**：纯检索的 top-1 经常是「语义相近但没回答问题」的片段。
加了复核之后，边缘题的正确拒答率从 5/10 提到 10/10——宁可说「他没聊过」，
也不给一段答非所问的视频。

代价是每次提问要 2~3 次 LLM 调用（改写 + 复核），约 2~4 秒。

## 4. 服务端

FastAPI，`python -m fengge.server`，默认 `127.0.0.1:8000`。

| 路由 | 作用 |
|---|---|
| `POST /api/ask` | 主检索接口 |
| `GET /api/health` | 记录数 / 阈值 / 可用片段数 |
| `GET /api/topics` | 话题聚合 |
| `GET /api/comments/<bvid>` | 缓存的热评 |
| `GET /api/live2d/models` | 扫 `web/vendor/live2d/models/` 生成模型列表 |
| `GET /clips/<file>` | 视频/封面静态文件，支持 Range 请求 |

启动时把 `dataset/clips.jsonl` 读进内存建索引（1460 条，冷启动约 3 秒）。

## 5. 前端

`web/index.html` 单文件，无构建步骤：

- 浅色 + 毛玻璃 + 极光粒子背景
- 提问 → 播放器自动定位到 `trim.start`，到 `trim.end` 暂停
- 「原话逐句」可点击跳转
- 看板娘：`.model3.json` 走 pixi + Cubism 4，`.model.json` 走 live2d-widget，按扩展名自动分流

### 5.1 Live2D 动画为什么一开始是静止的

库的 `Live2DModel.update()` 累加的是**毫秒**，内部 `_render` 再 `/1000` 转秒。
最初传的是 `deltaMS / 1000`（秒），导致模型内部时钟慢 1000 倍——看起来完全不动。
改成 `m.update(app.ticker.deltaMS)` 之后正常。

另外 `autoUpdate` 挂在 `PIXI.Ticker.shared` 上，和 `app.ticker` 不是同一个；
窗口被遮挡时浏览器还会把 rAF 降到 ~1fps。所以现在是自己用 `app.ticker` 驱动，
再加一个 250ms 的补帧兜底。

## 6. 静态导出

`tools/export_static.py` 把在线服务压成纯静态：

| 产物 | 大小 | 说明 |
|---|---|---|
| `data/clips.json` | 0.41 MB | 瘦身记录（去掉 segments/transcript） |
| `thumbs/*.jpg` | 11 MB | 240px 缩略图，懒加载 |
| `vendor/live2d/` | 8 MB | 只带峰哥模型 + 渲染库 |
| `index.html` | 12 KB | 浏览器内检索 |

### 浏览器内检索：字符二元组 BM25

中文没有空格，浏览器里又不想装分词器，所以用**字符二元组**（`"送外卖"` → `送外/外卖`）：

```
idf = log(1 + (N - df + 0.5) / (df + 0.5))
score = Σ idf · tf·(k1+1) / (tf + k1·(1 - b + b·dl/avgdl))
k1 = 1.4, b = 0.72
```

1460 条文档建索引约 40 ms，查询 <5 ms，索引常驻内存约 8 MB。

**代价**：没有 LLM 改写和复核，命中率从 8/10 掉到 6~7/10，边缘题更容易误判。

### 视频怎么办

18.5 GB 视频不可能塞进 Pages。所以静态版用 **B 站官方内嵌播放器**：

```
https://player.bilibili.com/player.html?bvid=BVxxx&page=1&t=62&autoplay=0&danmaku=0
```

搜索出来就把最相关那条加载进页面里的播放器，点其它结果切换。
好处：零存储、零带宽、不二次分发。

## 7. 测试

142 个测试，覆盖：过滤器、去重、状态机、下载重试、ASR 参数、导出、
混合检索排序、API 路由、数据迁移。

```powershell
python -m pytest -q
```

## 8. 关键取舍

| 决策 | 理由 |
|---|---|
| 归档在抽问答之前 | 避免「有问答没视频」的悬空记录 |
| 只保留 ≤600 秒 | 长视频转写成本高、检索粒度差 |
| LLM 复核而非纯阈值 | 语义相似 ≠ 回答了这个问题的 |
| 静态版丢 LLM | 部署成本从 $5/月 降到 0 |
| 视频走 B 站外链 | 版权 + 带宽 + 存储三重考虑 |
| 模型不做成独立 neck 零件 | `image2live2d` 会把它压到衣服后面，永远露不出来 |
