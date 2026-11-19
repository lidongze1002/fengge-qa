# 峰哥解答世间万物

> 把 B 站 UP 主「卡秃噜皮君」的直播切片，变成一套**可检索、可回源、能开口说话**的问答系统：
> 问一句话 → 在他的 950 多个切片里找到真正回答过的那一段 → 当场播出来。

![看板娘](docs/images/model.png)

- **1460 条问答**，来自 **951 个切片**，覆盖 3339 条投稿里筛出的内容
- 检索链路：LLM 改写 → 向量 + BM25 混合（RRF）→ LLM 复核，阈值 0.62，宁可拒答也不硬凑
- 看板娘是**峰哥本人的 Live2D 模型**（真 `.moc3`，26 个部件、34 个参数、24 组动作）
- 两种形态：本地全功能（FastAPI + 就地播放 + LLM 复核）、纯静态（19.5 MB，浏览器里检索，B 站内嵌播放）

---

## 一眼看懂架构

```
┌────────────────────────── 数据流水线（离线，一次性） ──────────────────────────┐
│                                                                              │
│  discover          download           asr              archive        structure│
│  B 站投稿列表  →   yt-dlp 拉视频  →  faster-whisper →  ffmpeg 转码  →  LLM 抽问答│
│  3339 条           单线程+随机间隔      large-v3 (GPU)    校验时长       问题/要点 │
│                                                                     ↓         │
│                                                          dataset/clips.jsonl   │
└──────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌──────────────────────────── 检索（在线） ────────────────────────────────────┐
│                                                                              │
│  提问 ──→ LLM 改写 3 条 ──→ 向量检索 ─┐                                      │
│                        └──→ BM25 ────┴─→ RRF 融合 ──→ LLM 复核 ──→ 播放片段   │
│                                          (0.62 阈值)    answers/partial/no    │
└──────────────────────────────────────────────────────────────────────────────┘
                                    ↓
        ┌───────────────────────┴────────────────────────┐
   本地全功能版                                    纯静态版
   FastAPI + mp4 就地播放                    浏览器 BM25 + B 站内嵌播放器
   19 GB 视频 / 需要 API key                 19.5 MB / 零后端 / 零成本
```

详细设计见 [docs/architecture.md](docs/architecture.md)。

---

## 快速开始

### 1. 只想看页面（零依赖）

```powershell
cd dist
python -m http.server 8080
# http://127.0.0.1:8080
```

`dist/` 是已经导出好的静态站，19.5 MB，检索在浏览器里跑。

### 2. 跑完整版（含本地视频）

```powershell
python -m pip install -r requirements.txt
winget install --id Gyan.FFmpeg -e          # ffmpeg + ffprobe 都要进 PATH
python -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # GPU 跑 ASR 用

copy .env.example .env                      # 填 B 站 cookie / DeepSeek key
$env:PYTHONPATH = "$PWD\src"
python -m fengge.cli check                  # 环境自检

python -m fengge.server                     # http://127.0.0.1:8000
```

### 3. 自己造一遍数据

```powershell
python -m fengge.cli discover               # 拉投稿清单
python -m fengge.cli run --limit 300        # 先跑 300 条试点
python -m fengge.cli export                 # 导出 + 抽检表
python -m fengge.cli run                    # 全量（断点续跑）
python -m fengge.cli verify                 # 20 题检索验收
```

单阶段也能跑：`download` / `asr` / `archive` / `structure`。
分批扩语料的脚本是 `tools/expand.py`（幂等，中断重跑即可）。

---

## 数据集现状

| 指标 | 值 |
|---|---|
| 投稿发现 | 3339 条 |
| 已归档切片 | 1213 条（0 失败） |
| 可用问答 | **1460 条**（一个切片可出多条） |
| 覆盖切片 | 951 个 |
| 被拒 | 488 条（无问答 / 质量低 / 转写过短 / 重复） |
| 回答平均长度 | 78 字 |
| 话题分布 | 情感两性 340、社会议题 302、搞钱 132、生活方式 125、人际关系 116、职业发展 107 |
| 检索验收 | 有答案 8/10 命中，边缘题 10/10 正确拒答 |

产物：

| 路径 | 说明 |
|---|---|
| `dataset/clips.jsonl` | 1460 条问答（问题、回答要点、trim 区间、逐句转写） |
| `dataset/rejected.jsonl` | 被拒记录及原因 |
| `dataset/report.md` | 统计报告 |
| `data/state.db` | 全量状态机（SQLite） |
| `data/clips/` | 归档视频（**不进 Git**） |

每条记录都带 `source_bvid` 和 `trim.start/end`，可以直接回源到原视频那一刻。

---

## 网页

一个输入框：提问 → 检索 → 播放。

- **命中**：就地播放对应片段（自动跳到起点、到终点暂停），给出回答要点和原话
- **没命中**：明确告诉你「这个峰哥真没聊过」，并列出最接近的几段，不硬凑
- 右下角看板娘会跟着眨眼、呼吸、转头，提问时切 `Talk` 动作，答对切 `Smile`

接口：

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/ask` | `{"question": "..."}` → `found` / `best` / `results` / `verdict` |
| `GET` | `/api/topics` | 话题列表 |
| `GET` | `/api/comments/<bvid>` | 该视频的热评 |
| `GET` | `/api/live2d/models` | 扫描模型目录，供「换一个」使用 |
| `GET` | `/clips/<bvid>.mp4` | 归档视频（支持 206 分段） |

---

## 看板娘（峰哥 Live2D）

不是纸片人差分，是**真正的 Live2D Cubism 3 模型**：

| 项 | 值 |
|---|---|
| 格式 | `.moc3` + `model3.json` + `physics3.json` + `cdi3.json` |
| 部件 | 26 个（可独立驱动的图层） |
| 参数 | 34 个（`ParamAngleX/Y`、`ParamEyeLOpen`、`ParamMouthOpenY`…） |
| 动作 | 24 组（Idle / Talk / Smile / Angry / Sad / Blink / Head_yaw…） |
| 贴图 | 26 张，模型包 7.4 MB |
| 生成 | 单张 AI 立绘 → See-Through 语义分层 → image2live2d 自动绑骨导出 |

模型、素材和完整复现步骤见 [docs/model.md](docs/model.md)。渲染用
`pixi.js 6.5 + live2dcubismcore + pixi-live2d-display`，`?m=` 可切换模型，
「换一个」按钮循环，丢一个新模型目录进去刷新即可，不用改代码。

---

## 部署

| 方式 | 成本 | 能力 |
|---|---|---|
| **Cloudflare Pages**（推荐） | 免费 | 拖 `dist/` 上传，全球 CDN，浏览器检索 + B 站内嵌播放 |
| **GitHub Pages** | 免费 | 推 `gh-pages` 分支，同上 |
| **VPS**（$5/月那档） | 付费 | 代码原样跑，含 LLM 复核 + 本地视频播放 |

```powershell
python tools\export_static.py          # 生成 dist/
```

视频不打包：用 B 站官方播放器 `player.bilibili.com/player.html?bvid=...&t=62`
就地播放，版权和带宽都归 B 站。详细说明见 README 末尾「部署（纯静态）」。

---

## 目录

```
src/fengge/          数据流水线 + 检索 + FastAPI 服务
  discover.py        B 站投稿发现（wbi 签名）
  download.py        yt-dlp 下载，限速与风控处理
  asr.py             faster-whisper 转写
  transcode.py       ffmpeg 归档与时长校验
  structure.py       LLM 抽取问答
  retrieval.py       BM25 + 向量 + RRF
  query.py           提问改写 / 复核 prompt
  server.py          FastAPI：/api/ask 等
web/index.html       本地全功能前端
web/static/          静态版前端（浏览器内检索）
tools/               导出、扩语料、Live2D 修补脚本
docs/                架构、模型、Live2D 接入文档
dist/                导出好的静态站（构建产物）
tests/               142 个测试
```

---

## 文档

| 文档 | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | 系统架构、状态机、检索链路、关键决策与踩坑 |
| [docs/model.md](docs/model.md) | Live2D 模型：素材、工具链、五步流程、修补记录、接入方式 |
| [docs/live2d.md](docs/live2d.md) | live2d-widget 接入细节与 AI 建模方案调研 |

---

## 版权与免责

- 视频与直播内容的版权归 B 站 UP 主「卡秃噜皮君」及主播「峰哥亡命天涯」所有，本项目**不主张任何权利**。
- 本项目只做检索与学习研究：**不二次分发原片**、不用于商业用途。
- 数据集中的索引与文字由程序自动生成（语音识别 + 模型抽取），可能存在误差，**以原视频为准**。
- 每条记录都保留 `bvid` 与时间戳，便于回到出处核对。
- 如有侵权，请联系删除，会立刻下架相关条目与文件。

## 开发

```powershell
python -m pytest -q          # 142 passed
```
