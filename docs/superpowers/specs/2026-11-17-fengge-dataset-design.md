# 峰哥问答视频数据集 —— 设计文档

日期：2026-11-17
状态：已批准（2026-11-17，使用者确认「按推荐」）
项目路径：`D:\fengge-rag`

---

## 1. 意图与为什么

峰哥（B 站 UP 主「卡秃噜皮君」，mid `433004026`，34.9 万粉，3339 个投稿）的直播切片，
已经在回答年轻人反复提出的同类问题。目标是：**把用户的新提问抽象成通用问题，检索到峰哥
已经回答过同类问题的片段，直接拿他的原话回答。**

本阶段只做这件事的地基：**把 3339 条投稿变成一份可被检索、可溯源、可出片的数据集**。
没有干净的数据集，后面的 RAG 和视频合成都是空中楼阁。

## 2. 目标 / 非目标 / 反目标

### 目标
1. 抓到 UP 主全部投稿的元信息（bvid、标题、时长、发布时间、封面）
2. 下载视频并压缩存档，保证第二阶段还能拿到原片
3. 对每条视频做中文语音识别，产出带时间戳的逐句转写
4. 用 LLM 把「标题 + 转写」结构化成一条条问答记录，核心字段是**抽象问题**
5. 过滤掉不是问答的内容，产出 `dataset/clips.jsonl` 和统计报告
6. 留一个 20 条问题的检索小验证，证明这份数据集真的能被检索用

### 非目标（本阶段不做）
- 不做 RAG 检索服务、向量库、API
- 不做视频合成/出片（拼接、字幕烧录、TTS 串场）
- 不做画面理解（人脸、场景、OCR），只做语音 + 标题
- 不做实时增量更新，只做一次全量快照 + 可重跑的增量入口

### 反目标（就算技术能跑也算失败）
- **数据不能用的"全量"**：3339 条里塞满段子和整活，检索出来牛头不对马嘴。宁可 1500 条精准。
- **绕风控**：不搞多账号轮询、不伪造请求头、不破解。只用正常登录态 + 限速。
- **丢溯源**：每条必须保留原始 bvid 和链接，随时能回到原视频。

## 3. 约束（实测）

| 项 | 实际情况 |
|---|---|
| B 站 API | 直连投稿列表接口两次被拦：`-799 请求过于频繁`、`-412 request was banned`。必须带登录 cookie + 限速 |
| 视频形态 | 竖屏 720×1568，多为 30s~90s，绝大多数已经是「一条一个问题」 |
| 字幕 | 搬运切片基本没有 CC 字幕，必须自己跑 ASR |
| 磁盘 | D 盘剩余 92.6 GB，必须边处理边压缩，控制峰值 |
| GPU | RTX 4060 Laptop 8 GB，驱动 610.88，**无 CUDA Toolkit、无 cuDNN**，当前 torch 是 CPU 版 |
| CPU / 内存 | 16 GB RAM |
| 工具链 | 无 ffmpeg、无 yt-dlp、无 faster-whisper；有 dotnet 9、git、winget、Python 3.10 |
| LLM | 环境变量 `OPEN_API_KEY` 可用（OpenAI 官方，已验证 200） |

## 4. 方案选择

### 方案 A：先全量存档，再统一处理
全部下载完再跑 ASR、结构化。
- 优点：流程最直白，失败重试简单
- 缺点：峰值占盘 ~55 GB，链条串行，约 2.5~3 天

### 方案 B：边下边处理（**已选**）
每条下完立刻抽音频 → ASR → 结构化 → 原片压成 720p 存档，SQLite 记录每条状态。
- 优点：峰值占盘降到 ~20 GB；断点续跑；几小时后就能看到前几百条的真实数据集并校验质量
- 缺点：多一层状态机，单条失败要重入队列

### 方案 C：只抓音频建文本库，视频按需回源
- 优点：全量文本索引只要 2~3 GB，一天建完
- 缺点：搬运号视频有下架风险，等真要出片时可能找不到原片，和最终目标冲突

**选择理由**：B 在磁盘、可恢复性、早期可见性三方面都最好，代价只是多写一个状态机。

## 5. 采用的设计

### 5.1 目录结构

```
D:\fengge-rag\
  docs\superpowers\specs\        # 本文档
  .env.example                   # 配置模板（cookie、key、路径）
  requirements.txt
  src\
    config.py                    # 读 .env，路径常量
    db.py                        # SQLite 状态机
    discover.py                  # 枚举投稿 → manifest
    download.py                  # 下载（yt-dlp 主 / BBDown 兜底）
    transcode.py                 # 720p 压缩存档
    asr.py                       # faster-whisper
    structure.py                 # LLM 结构化
    filter.py                    # 质量过滤
    export.py                    # 导出 dataset/
    pipeline.py                  # 编排：下载→ASR→结构化 三条队列
    verify.py                    # 20 条检索小验证
  data\
    manifest.jsonl
    state.db
    raw\<bvid>.mp4               # 临时，处理完删除
    audio\<bvid>.flac            # 临时，处理完删除
    clips\<bvid>.mp4             # 720p 存档（长期）
    asr\<bvid>.json              # 逐句转写
    structured\<bvid>.json       # LLM 结果
  dataset\
    clips.jsonl                  # 最终数据集
    rejected.jsonl               # 被拒的 + 原因
    report.md                    # 统计报告
  logs\
```

### 5.2 状态机

`state.db` 一张表 `clips`，字段：

```
bvid PK, aid, title, duration, pubdate, cover_url,
state, attempts, last_error,
raw_path, audio_path, clip_path, cover_path, asr_path, structured_path,
asr_chars, asr_lang_prob, quality, reject_reason,
created_at, updated_at, archived_at
```

状态流转：

```
discovered → downloaded → asr_done → structured → accepted → archived
                                  ↘ rejected
任意状态 --失败--> 原状态（attempts+1），attempts ≥ 3 标记 failed
```

- `downloaded` 的含义：**raw 视频与封面 jpg 都已落盘**。封面是下载阶段的一部分，不是可选步骤。
- `archived` 的含义：720p 存档已生成并校验（时长与源一致 ±0.5s、能解码），此时才允许删除 `raw/` 与 `audio/`。
- 转码失败不得删除 raw；宁可重跑转码，也不要重下（下载是全流程最贵、最招风控的一环）。

所有阶段只认「状态 + 失败次数」，不认内存，保证进程随时杀掉重开都能续。

一条 bvid 可以产出 **多条问答记录**，因此问答记录不建在这张表里，而是导出时的
`records`（见 5.9）；`clips` 表只负责「这条视频处理到哪一步了」。

### 5.3 枚举（discover）

- 主路径：`yt-dlp --flat-playlist -J https://space.bilibili.com/433004026/video --cookies-from-browser edge`
- 兜底：`BBDown space 433004026 -info` 解析
- 产出 `manifest.jsonl`，去重后写入 `clips` 表
- 验收：条目数 ≥ 3000，缺的记入报告

### 5.4 下载（download）

- 主：`yt-dlp -f "bv*[height<=1080]+ba/b" --merge-output-format mp4 -o raw/<bvid>.mp4`
- 兜底：`BBDown <bvid> --work-dir raw --file-pattern <bvid>`
- cookie：`--cookies-from-browser edge`，失败时用 `.env` 里的 `BILI_COOKIE`
- 限速：单 worker，每条之间随机 sleep 3~6s；412/-799 时指数退避（30s→2min→5min）
- 不并发下载，避免整号被 ban
- 封面：下载 `cover_url` 存 `data/clips/<bvid>.jpg`，去掉 B 站 CDN 的 `@` 裁剪参数取原图
- **处理顺序：按 `pubdate` 倒序**。先集中跑最近 300 条作为「试点批次」，第 5 小时即可按验收标准
  抽查；试点通过后再放开跑完全部，不通过就停下来改 prompt 或参数。

### 5.5 转码存档（transcode）

- 竖屏统一 `scale=720:-2`，横屏 `scale=-2:720`
- `libx264 -crf 26 -preset veryfast`（先求稳；若确认 nvenc 可用再切 `h264_nvenc`）
- 音频 `aac 96k`
- 预计单条 30~90s 压到 5~12 MB，全量 ~30 GB

### 5.6 ASR

- faster-whisper `large-v3`，`compute_type=int8_float16`，`vad_filter=True`，`language=zh`
- 需要 `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` 才能跑 GPU；装完先跑一条自检，
  **GPU 不可用则整体降级方案见 8.1 风险**
- `initial_prompt` 注入领域词：峰哥、B 友、连麦、老哥、牛马、躺平、搞钱 等，降低错字
- 输出 `asr/<bvid>.json`：`{segments:[{start,end,text}], text, duration}`
- 单条转写后立刻删除 `audio/` 下的临时文件

### 5.7 结构化（structure）

输入：标题 + 带时间戳的完整转写 + 时长。**一条视频允许产出 0~N 个问答**，所以 LLM 返回的是数组，
用 `response_format=json_schema` 强约束：

```json
{
  "items": [
    {
      "is_qa": true,
      "question_verbatim": "峰哥，年轻人做什么工作最好",
      "abstract_question": "年轻人应该如何选择职业方向",
      "question_type": "职业发展",
      "answer_summary": "峰哥认为先看行业周期，别迷信努力……",
      "key_claims": ["选行业比努力重要", "别在小地方耗着"],
      "quote": "选择大于努力，你先看看这个行业还剩几年",
      "tags": ["职业", "择业", "小城市"],
      "emotion": "劝退",
      "quality": 4,
      "reject_reason": null,
      "trim": {"start": 2.4, "end": 52.1}
    }
  ]
}
```

- `question_type` 是**受控词表（枚举，单选）**，固定 12 类：
  `职业发展 | 搞钱赚钱 | 情感两性 | 婚姻家庭 | 人际关系 | 城市与去留 | 学历与教育 |
   自我认同 | 身心健康 | 社会议题 | 生活方式 | 其他`。
  改词表要重跑 prompt，不允许模型自由发挥，否则统计报告会被几百个单例标签淹没。
- `tags` 允许自由文本，但要求 2~4 个、每个不超过 6 字，用于细粒度检索。
- `trim` 让 LLM 从带时间戳的句子区间里挑出这组问答的首尾，用于后续精准切条。
- 模型：`gpt-4o-mini`（默认，便宜且中文够用），可换 `gpt-4.1-mini`
- 并发 8，失败重试 3 次；`items` 为空数组视为无有效问答，直接进 `rejected`（`reject_reason=no_qa`）
- 成本估算：3339 条 × 约 2k input tokens ≈ 7M tokens，约 2~4 美元
- 合规：转写内容来自公开视频，允许发送至 OpenAI 做结构化；**数据集本身不对外发布**，
  这条界线以本节为准

### 5.8 过滤（filter）

过滤分两层。

**视频层**（不产生任何记录，整条进 `rejected.jsonl`）：

- 转写字数 < 30
- 时长 < 15s
- ASR 语言概率 < 0.6
- LLM 返回 `items: []`

**问答层**（逐条判断，被拒的进 `rejected.jsonl`，不影响同一视频的其它条目）：

- `is_qa = false`（纯段子、连麦整活、没有提问）
- `quality < 3`
- `abstract_question` 为空或与 `question_verbatim` 完全一致（说明没抽象成功）
- 时长 > 300s 的视频，只有 `quality ≥ 4` 才放行

**去重层**（导出前跑）：按 `abstract_question` 做 embedding 聚类，余弦相似度 > 0.92 视为同一条，
保留 `quality` 高的、`play` 高的；其余标 `duplicate_of` 留在 `rejected.jsonl` 里可追溯。
这一层是必须的——搬运号会把同一段直播切片换个标题反复发，只按 bvid 去重挡不住。

所有拒绝都必须写 `reject_reason`，取值来自固定枚举，便于统计。

### 5.9 数据集导出（export）

记录单位是**一条问答**，不是一条视频。`id = <bvid>_p<序号>`，同一 bvid 的第 2 个问答就是 `..._p2`。
`dataset/clips.jsonl` 每行：

```json
{
  "id": "BV1QR446eEMm_p1",
  "source_bvid": "BV1QR446eEMm",
  "source_url": "https://www.bilibili.com/video/BV1QR446eEMm",
  "author": "卡秃噜皮君",
  "title": "“峰哥，年轻人做什么工作最好？”",
  "duration": 30,
  "pubdate": "2026-11-05",
  "clip_path": "data/clips/BV1QR446eEMm.mp4",
  "cover_path": "data/clips/BV1QR446eEMm.jpg",
  "trim": {"start": 2.4, "end": 22.1},
  "transcript": "……",
  "segments": [{"start": 2.4, "end": 5.1, "text": "……"}],
  "question_verbatim": "……",
  "abstract_question": "……",
  "question_type": "职业发展",
  "answer_summary": "……",
  "key_claims": ["……"],
  "quote": "……",
  "tags": ["……"],
  "emotion": "……",
  "quality": 4
}
```

同一条视频的多个问答共用同一个 `clip_path`，靠各自的 `trim` 区分；第二阶段出片时按 `trim` 切。
`transcript` 存这条问答对应的片段文本，`segments` 只保留落在 `trim` 区间内的句子。

`dataset/report.md`：总量、各状态分布、拒绝原因分布、时长分布、话题分布、
ASR 字数分布、失败清单、磁盘占用。

### 5.10 检索小验证（verify）

- 20 个测试问题**必须在结构化开跑之前写好并冻结**，写题时不许看数据集内容，避免倒推
- 10 个「明显有对应」、10 个「边缘/无对应」
- 用 `text-embedding-3-small` 对 `abstract_question + tags + answer_summary` 建临时索引
- 输出 top-3 命中，人工标注是否答得上
- 「无直接答案」的判定阈值**不在测试题上调**：另标 30 对（问题, 片段）作为 dev 集，
  在 dev 集上选一个 top1 余弦阈值（预计 0.60~0.68 区间），定完冻结并写进 `report.md`。
  测试时 top1 低于该阈值即输出「没有直接答案」
- 通过线：10 个明显题里 ≥ 8 个 top-3 命中；10 个边缘题里至少 6 个能触发「无直接答案」

### 5.11 人工抽检（review）

结构化结果**随机抽 50 条**人工过一遍，检查 `abstract_question` 是否真的抽象掉了人名/情绪/具体场景，
`answer_summary` 是否忠于原话。抽检用 `review_sample.csv` 导出（带原视频链接和 trim 时间点），
人工打 `pass / fail`，`fail` 率超过 20% 就停下来改 prompt 重跑，而不是继续跑完全量。
这一关不做自动化替代——它是唯一能发现「模型看起来全对但全错」的环节。

## 6. 运行与资源预算

| 阶段 | 耗时估算 | 说明 |
|---|---|---|
| 装环境 | 0.5 h | ffmpeg、yt-dlp、faster-whisper、CUDA 运行库 |
| 枚举 | 10 min | 分页拉 3339 条 |
| 下载 | 5~8 h | 单 worker + 限速，含封面，最慢的一环 |
| ASR | 6~8 h | 50 h 音频 / 约 8x 实时 |
| 转码 | 3~4 h | 与下载/ASR 并行 |
| 结构化 | 1~2 h | 8 并发 |
| 导出 + 检验 | 0.5 h | |
| 人工抽检 | 1~2 h | 50 条，人在环 |

总体：**一到两个通宵跑完**。磁盘峰值约 20 GB，稳态约 35 GB。

## 7. 验收标准

1. manifest 覆盖 ≥ 95% 的投稿（≥ 3170 条）
2. 下载成功率 ≥ 90%，封面齐全
3. 随机抽 20 条人工核对转写，字错率主观可读，无整段幻觉
4. 最终可用问答 ≥ 1500 条，`reject_reason` 分布合理，`question_type` 无长尾碎标签
5. 50 条结构化抽检 fail 率 < 20%
6. 20 条检索验证达标（见 5.10）
7. `dataset/clips.jsonl` 能被一个 20 行的脚本读出来并打印成可读摘要

## 8. 风险与应对

### 8.1 GPU 跑不起来
cuDNN/cuBLAS 版本不匹配是高频坑。应对顺序：
1. `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` 并把 `site-packages/nvidia/*/bin` 加入 PATH
2. 仍失败 → 用 `medium` 模型 GPU int8；再失败 → 用 `small`
3. 最后兜底 → OpenAI `whisper-1` API（50 h ≈ 18 美元），只对失败条目用

### 8.2 风控
- 严格单线程 + 随机间隔；遇 412 停 10 分钟再继续
- cookie 过期会表现为全部 403，报告里单独告警，不静默失败

### 8.3 视频被删
下载即存档，不延后；manifest 里保留 `state=failed` 的条目和原因，便于日后补

### 8.4 ASR 幻觉
whisper 在静音/音乐段会编词。用 `vad_filter` + `condition_on_previous_text=False`，
并把「字数异常多但时长很短」的条目标记复核

### 8.5 版权与合规
仅个人研究用途；每条保留原作者、原链接；不二次发布原片；数据集不外传。
「不外传」指的是**数据集不对外发布**，不限制把公开视频的转写发给 OpenAI 做结构化。

### 8.6 账号风险
全流程使用使用者本人主号（已确认接受该风险）。主号被限不会有多账号轮换的退路，
因此限速是硬约束，不是可调参数；一旦出现连续 403，必须停机而不是降级硬刷。

## 9. 已拍板的决定

| # | 问题 | 决定 |
|---|---|---|
| 1 | 记录单位 | 一条问答一条记录，`id = bvid_pN`；导出前按抽象问题聚类去重（>0.92 视为重复） |
| 2 | 账号 | 用主号 + 浏览器登录态，接受风险；限速不可调 |
| 3 | 人工校验 | 随机抽 50 条，fail 率 >20% 就停线改 prompt |
| 4 | 转写外发 | 允许发给 OpenAI 做结构化 |
| 5 | 封面 | 下载阶段一并落盘，进状态机 |
| 6 | raw 删除时机 | 新增 `archived` 状态，转码校验通过才删 |
| 7 | 无答案判定 | 阈值在独立 dev 集上校准后冻结，测试题提前冻结 |
| 8 | 话题标签 | 12 类受控枚举，自由标签另设字段 |
| 9 | 首批范围 | 按发布时间倒序，先跑最近 300 条做试点 |

## 10. 留给实现者的决定

- SQLite 具体 schema 细节、索引
- BBDown 与 yt-dlp 的具体调用参数和重试策略实现
- 是否引入 `h264_nvenc` 加速转码
- LLM prompt 的具体措辞与 few-shot 例子
- 日志格式、进度条形式
- 是否把 `trim` 真正切出一个独立短片（建议做，但不阻塞数据集）
