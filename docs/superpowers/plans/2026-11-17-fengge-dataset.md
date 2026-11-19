# 峰哥问答数据集 —— 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 B 站 UP 主「卡秃噜皮君」的 3339 条视频变成一份带转写、带抽象问题、可检索的问答数据集。

**Architecture:** 单进程流水线，SQLite 作为唯一状态源。下载 → 抽音频 → ASR → 结构化 → 过滤去重 → 导出，
每个阶段只认数据库里的状态推进，进程随时可以杀掉重开。重活（yt-dlp / ffmpeg / whisper）
全部通过 subprocess 或库调用包在可注入的薄封装里，单元测试不碰网络和 GPU。

**Tech Stack:** Python 3.10、SQLite（标准库 `sqlite3`）、yt-dlp、ffmpeg、faster-whisper、
OpenAI Python SDK（`gpt-4o-mini` + `text-embedding-3-small`）、pytest。

**Spec:** `docs/superpowers/specs/2026-11-17-fengge-dataset-design.md`

## Global Constraints

- 解释器：Python 3.10（`C:\Users\ldz\AppData\Local\Microsoft\WindowsApps\python.exe`），每个模块首行 `from __future__ import annotations`
- 平台：Windows，路径一律用 `pathlib.Path`，不拼字符串
- 所有 JSON 落盘用 `ensure_ascii=False`；jsonl 每行一个对象，行尾 `\n`
- 时间单位一律**秒（float）**；`pubdate` 是 Unix 秒（int）
- 下载**单 worker**，每条之间 `random.uniform(3.0, 6.0)` 秒；出现连续 3 次 403 立即停线
- LLM 模型 `gpt-4o-mini`，embedding `text-embedding-3-small`
- whisper `large-v3`，`compute_type="int8_float16"`，`language="zh"`，`vad_filter=True`，
  `condition_on_previous_text=False`
- 12 类话题枚举，取值逐字照抄：
  `职业发展 | 搞钱赚钱 | 情感两性 | 婚姻家庭 | 人际关系 | 城市与去留 | 学历与教育 | 自我认同 | 身心健康 | 社会议题 | 生活方式 | 其他`
- 去重阈值：余弦相似度 `> 0.92` 视为重复
- 所有目录常量由 `config.Settings` 提供，业务代码里不出现硬编码路径

---

## Review Focus

实现时最容易被漏掉、但一定会咬到人的六种情况。每条都在下面指定了负责它的任务。

1. **一条视频含多个问答**：LLM 返回数组，导出成 `bvid_p1` / `bvid_p2`，两条的 `trim` 不能重叠，
   `segments` 要按各自的 `trim` 裁开 —— Task 7、Task 9
2. **下载到 0 字节或只有几 KB 的错误页**：yt-dlp 退出码 0 但文件不可用，必须按文件大小和
   时长双重校验判失败，否则后面 ffmpeg 会炸在半夜 —— Task 4
3. **whisper 在静音/音乐段反复输出同一句话**：同一句连续出现 ≥ 3 次视为幻觉，必须清掉 —— Task 6
4. **断点续跑**：进程被 kill 后重开，已 `accepted` 的行不能被重新处理，`attempts` 不能被重置 —— Task 2、Task 10
5. **cookie 过期**：表现为连续 403，必须整批停机并明确报错，不能把 3339 条全标成 `failed` —— Task 4、Task 10
6. **同一 bvid 重复入库**：manifest 重跑时 `upsert` 必须幂等，且不能覆盖已推进的状态 —— Task 2

---

## 文件结构

```
D:\fengge-rag\
  .env.example
  requirements.txt
  pytest.ini
  README.md
  src\fengge\
    __init__.py
    config.py        # Settings + load_settings
    models.py        # ClipMeta 数据类
    db.py            # SQLite 状态机
    discover.py      # 枚举投稿 → manifest
    download.py      # 视频 + 封面下载
    transcode.py     # 720p 归档
    asr.py           # 抽音频 + whisper
    structure.py     # LLM 结构化
    filter.py        # 过滤 + 去重
    export.py        # 数据集导出
    verify.py        # 检索小验证
    pipeline.py      # 编排
    cli.py           # 命令行入口
  tests\
    test_config.py
    test_db.py
    test_discover.py
    test_download.py
    test_transcode.py
    test_asr.py
    test_structure.py
    test_filter.py
    test_export.py
    test_verify.py
    test_pipeline.py
```

按职责切分而不是按技术层：`download` / `transcode` / `asr` 各自封装一个外部工具，
`structure` / `filter` / `export` 是纯数据变换，`pipeline` 只负责把状态往前推。

---

### Task 1: 项目骨架与配置

**Files:**
- Create: `requirements.txt`, `.env.example`, `pytest.ini`, `src/fengge/__init__.py`
- Create: `src/fengge/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.Settings`（frozen dataclass，字段见下）、`config.load_settings(root: Path | None = None, env: Mapping[str, str] | None = None) -> Settings`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_config.py
from pathlib import Path
from fengge.config import load_settings

def test_load_settings_builds_paths_under_root(tmp_path):
    s = load_settings(root=tmp_path, env={"OPEN_API_KEY": "sk-test"})
    assert s.root == tmp_path
    assert s.data_dir == tmp_path / "data"
    assert s.clips_dir == tmp_path / "data" / "clips"
    assert s.db_path == tmp_path / "data" / "state.db"
    assert s.dataset_dir == tmp_path / "dataset"

def test_load_settings_defaults(tmp_path):
    s = load_settings(root=tmp_path, env={})
    assert s.up_mid == "433004026"
    assert s.llm_model == "gpt-4o-mini"
    assert s.embedding_model == "text-embedding-3-small"
    assert s.whisper_model == "large-v3"
    assert s.whisper_compute_type == "int8_float16"
    assert s.download_delay == (3.0, 6.0)
    assert s.trial_size == 300

def test_load_settings_reads_env_overrides(tmp_path):
    s = load_settings(root=tmp_path, env={"BILI_BROWSER": "chrome", "TRIAL_SIZE": "50",
                                          "LLM_MODEL": "gpt-4.1-mini"})
    assert s.browser == "chrome"
    assert s.trial_size == 50
    assert s.llm_model == "gpt-4.1-mini"

def test_settings_dirs_are_derived_not_hardcoded(tmp_path):
    s = load_settings(root=tmp_path, env={})
    for d in (s.data_dir, s.clips_dir, s.raw_dir, s.audio_dir, s.asr_dir,
              s.structured_dir, s.dataset_dir):
        assert str(d).startswith(str(tmp_path))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_config.py -v`
Expected: 4 failed，`ModuleNotFoundError: No module named 'fengge'`

- [ ] **Step 3: 实现 `config.py`**

`Settings` 字段：`root, data_dir, clips_dir, raw_dir, audio_dir, asr_dir, structured_dir,
dataset_dir, logs_dir, db_path, manifest_path, up_mid, browser, cookie, openai_api_key,
openai_base_url, llm_model, embedding_model, whisper_model, whisper_compute_type,
download_delay, trial_size, dedupe_threshold, verify_threshold`。

`verify_threshold` 默认 `0.62`，对应 spec §5.10 在 30 对 dev 集上校准后冻结的值。

`load_settings` 读 `env`（默认 `os.environ`），支持覆盖：`BILI_BROWSER`、`BILI_COOKIE`、
`OPEN_API_KEY`、`OPENAI_BASE_URL`、`LLM_MODEL`、`WHISPER_MODEL`、`TRIAL_SIZE`、`UP_MID`。
`download_delay` 固定 `(3.0, 6.0)`，不开放配置（限速是硬约束，见 spec §8.6）。
`openai_base_url` 缺省为空字符串，非空时传给 SDK。

`requirements.txt`：

```
yt-dlp>=2024.8.6
openai>=1.40.0
faster-whisper>=1.0.3
requests>=2.31.0
python-dotenv>=1.0.1
pytest>=8.0.0
```

`.env.example` 列出上面所有变量并注明默认值（`OPEN_API_KEY` 沿用系统里已有的变量名，
不要改名）。`cli.main` 启动时先 `dotenv.load_dotenv()`；`load_settings` 的 `env` 参数
默认取 `os.environ`，测试里显式传 `{}` 就完全隔离，不读磁盘上的 `.env`。

`pytest.ini`：

```ini
[pytest]
testpaths = tests
pythonpath = src
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_config.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add requirements.txt .env.example pytest.ini src/fengge/__init__.py src/fengge/config.py tests/test_config.py
git commit -m "feat: 项目骨架与配置加载"
```

---

### Task 2: SQLite 状态机

**Files:**
- Create: `src/fengge/models.py`, `src/fengge/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `config.Settings`（只用 `db_path`）
- Produces:
  - `models.ClipMeta(bvid: str, aid: int, title: str, duration: float, pubdate: int, cover_url: str)`
  - `db.STATES: tuple[str, ...]` = `("discovered","downloaded","asr_done","structured","accepted","archived","rejected","failed")`
  - `db.Database(path: Path)`，方法：
    - `init_schema() -> None`
    - `upsert_clip(meta: ClipMeta) -> bool`（新插入返回 True；已存在只更新标题/时长等元信息，**不动 state/attempts**）
    - `get(bvid: str) -> dict | None`
    - `set_state(bvid: str, state: str, **fields) -> None`
    - `fail(bvid: str, error: str, max_attempts: int = 3) -> str`
    - `next_batch(state: str, limit: int) -> list[dict]`
    - `counts() -> dict[str, int]`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_db.py
import pytest
from fengge.db import Database
from fengge.models import ClipMeta

@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "state.db")
    d.init_schema()
    return d

def meta(bvid="BV1", title="t"):
    return ClipMeta(bvid=bvid, aid=1, title=title, duration=30.0, pubdate=100, cover_url="u")

def test_upsert_is_idempotent_and_keeps_state(db):
    assert db.upsert_clip(meta()) is True
    db.set_state("BV1", "downloaded")
    assert db.upsert_clip(meta(title="新标题")) is False
    row = db.get("BV1")
    assert row["state"] == "downloaded"
    assert row["title"] == "新标题"
    assert row["attempts"] == 0

def test_fail_increments_and_caps(db):
    db.upsert_clip(meta())
    db.set_state("BV1", "downloaded")
    assert db.fail("BV1", "boom") == "downloaded"
    assert db.get("BV1")["attempts"] == 1
    db.fail("BV1", "boom")
    assert db.fail("BV1", "boom") == "failed"
    assert db.get("BV1")["state"] == "failed"

def test_next_batch_only_returns_requested_state_ordered_by_pubdate_desc(db):
    for i, bv in enumerate(["BV1", "BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 100 + i, "u"))
    db.set_state("BV2", "downloaded")
    db.set_state("BV3", "downloaded")
    rows = db.next_batch("downloaded", 10)
    assert [r["bvid"] for r in rows] == ["BV3", "BV2"]

def test_set_state_writes_fields_and_timestamp(db):
    db.upsert_clip(meta())
    db.set_state("BV1", "downloaded", raw_path="data/raw/BV1.mp4", cover_path="c.jpg")
    row = db.get("BV1")
    assert row["raw_path"] == "data/raw/BV1.mp4"
    assert row["cover_path"] == "c.jpg"
    assert row["updated_at"] is not None

def test_counts_groups_by_state(db):
    for i, bv in enumerate(["BV1", "BV2"]):
        db.upsert_clip(ClipMeta(bv, i, "t", 30.0, 100, "u"))
    db.set_state("BV2", "downloaded")
    assert db.counts() == {"discovered": 1, "downloaded": 1}

def test_reopen_keeps_data(db, tmp_path):
    db.upsert_clip(meta())
    db.set_state("BV1", "accepted")
    again = Database(tmp_path / "state.db")
    again.init_schema()
    assert again.get("BV1")["state"] == "accepted"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_db.py -v`
Expected: 6 failed，`ModuleNotFoundError: No module named 'fengge.db'`

- [ ] **Step 3: 实现**

`models.py` 用 `@dataclass(frozen=True)` 定义 `ClipMeta`，六个字段，顺序与上面一致。

`db.py`：`sqlite3.connect(self.path)`，`row_factory = sqlite3.Row`，建表语句包含 spec §5.2 的
全部列，`bvid TEXT PRIMARY KEY`，`state TEXT NOT NULL DEFAULT 'discovered'`，
`attempts INTEGER NOT NULL DEFAULT 0`，`updated_at TEXT`。
`upsert_clip` 用 `INSERT ... ON CONFLICT(bvid) DO UPDATE SET title=excluded.title,
duration=excluded.duration, cover_url=excluded.cover_url`，靠 `cursor.rowcount` 和
`SELECT changes()` 无法区分插入/更新，改用先 `SELECT 1 FROM clips WHERE bvid=?` 判断。
`next_batch` 按 `pubdate DESC, bvid` 排序。`counts` 用 `GROUP BY state`。
每个写方法结尾 `commit()`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_db.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/models.py src/fengge/db.py tests/test_db.py
git commit -m "feat: SQLite 状态机"
```

---

### Task 3: 枚举投稿

**Files:**
- Create: `src/fengge/discover.py`
- Test: `tests/test_discover.py`

**Interfaces:**
- Consumes: `models.ClipMeta`
- Produces:
  - `discover.build_space_cmd(mid: str, browser: str) -> list[str]`
  - `discover.parse_space_json(payload: dict) -> list[ClipMeta]`（兼容 `entries` 结构，容忍缺字段）
  - `discover.write_manifest(metas: list[ClipMeta], path: Path) -> int`
  - `discover.discover(settings, runner=subprocess.run) -> list[ClipMeta]`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_discover.py
import json
from fengge.discover import build_space_cmd, parse_space_json, write_manifest

def test_build_space_cmd_uses_browser_cookies():
    cmd = build_space_cmd("433004026", "edge")
    assert cmd[0] == "yt-dlp"
    assert "--flat-playlist" in cmd
    assert "--cookies-from-browser" in cmd
    assert cmd[cmd.index("--cookies-from-browser") + 1] == "edge"
    assert cmd[-1] == "https://space.bilibili.com/433004026/video"

def test_parse_space_json_maps_entries():
    payload = {"entries": [
        {"id": "BV1", "title": " 峰哥 问答 ", "duration": 30, "timestamp": 1793862075,
         "thumbnails": [{"url": "http://x/cover.jpg"}]},
        {"id": "BV2", "title": "无封面", "duration": 61, "timestamp": 1793777218},
    ]}
    metas = parse_space_json(payload)
    assert len(metas) == 2
    assert metas[0].bvid == "BV1"
    assert metas[0].title == "峰哥 问答"
    assert metas[0].duration == 30.0
    assert metas[0].pubdate == 1793862075
    assert metas[0].cover_url == "http://x/cover.jpg"
    assert metas[1].cover_url == ""

def test_parse_space_json_skips_bad_entries():
    payload = {"entries": [{"title": "没有 id"}, {"id": "", "title": "空 id"}]}
    assert parse_space_json(payload) == []

def test_write_manifest_dedupes_by_bvid(tmp_path):
    from fengge.models import ClipMeta
    metas = [ClipMeta("BV1", 1, "a", 30.0, 2, ""), ClipMeta("BV1", 1, "a", 30.0, 2, "")]
    path = tmp_path / "manifest.jsonl"
    assert write_manifest(metas, path) == 1
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["bvid"] == "BV1"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_discover.py -v`
Expected: 4 failed

- [ ] **Step 3: 实现**

`build_space_cmd` 产出：
`["yt-dlp", "--flat-playlist", "-J", "--cookies-from-browser", browser, "--", url]`
（`-J` 输出单个 JSON）。`parse_space_json` 里 `aid` 取 `entry.get("aid", 0)` 或 0，
`thumbnails` 缺失时 `cover_url=""`。`write_manifest` 按 bvid 去重（保留第一次出现），
每行 `json.dumps(meta.__dict__, ensure_ascii=False)`。
`discover` 跑 `runner(cmd, capture_output=True, text=True, encoding="utf-8")`，
非 0 退出码抛 `RuntimeError` 带上 stderr 前 500 字。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_discover.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/discover.py tests/test_discover.py
git commit -m "feat: 投稿列表枚举"
```

---

### Task 4: 下载视频与封面

**Files:**
- Create: `src/fengge/download.py`
- Test: `tests/test_download.py`

**Interfaces:**
- Consumes: `models.ClipMeta`、`config.Settings`
- Produces:
  - `download.build_download_cmd(meta, out_path: Path, browser: str, cookie: str) -> list[str]`
  - `download.is_valid_video(path: Path, min_bytes: int = 10240) -> bool`
  - `download.find_output(raw_dir: Path, bvid: str) -> Path | None`
  - `download.cover_path(clips_dir: Path, bvid: str) -> Path`
  - `download.strip_cover_query(url: str) -> str`
  - `download.download_one(meta, settings, runner=subprocess.run, sleeper=time.sleep) -> dict`
    返回 `{"raw_path": str, "cover_path": str}`；失败抛 `DownloadError`（携带 `status` 属性）
  - `download.is_rate_limited(errors: list[DownloadError]) -> bool`（连续 3 条 403/412）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_download.py
import pytest
from pathlib import Path
from fengge.download import (build_download_cmd, is_valid_video, find_output,
                             cover_path, strip_cover_query, download_one, DownloadError)

def meta():
    from fengge.models import ClipMeta
    return ClipMeta("BV1QR446eEMm", 1, "t", 30.0, 1, "http://i0.hdslb.com/a.jpg@100w.jpg")

def test_cmd_prefers_mp4_and_sets_output():
    cmd = build_download_cmd(meta(), Path("raw/BV1QR446eEMm.mp4"), "edge", "")
    assert cmd[0] == "yt-dlp"
    assert "-o" in cmd and cmd[cmd.index("-o") + 1].endswith("BV1QR446eEMm.%(ext)s")
    assert "bv*[height<=1080]+ba/b" in cmd
    assert cmd[-1] == "https://www.bilibili.com/video/BV1QR446eEMm"

def test_cmd_uses_cookie_string_when_no_browser():
    cmd = build_download_cmd(meta(), Path("raw/x.mp4"), "", "SESSDATA=abc")
    assert "--add-header" in cmd
    assert "Cookie:SESSDATA=abc" in cmd

def test_is_valid_video_rejects_tiny_files(tmp_path):
    p = tmp_path / "a.mp4"
    p.write_bytes(b"0" * 100)
    assert is_valid_video(p) is False
    p.write_bytes(b"0" * 20000)
    assert is_valid_video(p) is True
    assert is_valid_video(tmp_path / "missing.mp4") is False

def test_find_output_matches_any_extension(tmp_path):
    (tmp_path / "BV1.mp4").write_bytes(b"x")
    assert find_output(tmp_path, "BV1").name == "BV1.mp4"
    assert find_output(tmp_path, "BV1.flv").name == "BV1.flv"
    assert find_output(tmp_path, "nope") is None

def test_strip_cover_query_removes_at_suffix():
    assert strip_cover_query("http://i0.hdslb.com/a.jpg@100w.jpg") == "http://i0.hdslb.com/a.jpg"

def test_download_one_fails_on_zero_byte_output(tmp_path):
    from fengge.config import load_settings
    s = load_settings(root=tmp_path, env={})
    def runner(cmd, **kw):
        (s.raw_dir).mkdir(parents=True, exist_ok=True)
        (s.raw_dir / "BV1QR446eEMm.mp4").write_bytes(b"")
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    with pytest.raises(DownloadError) as e:
        download_one(meta(), s, runner=runner, sleeper=lambda _: None)
    assert e.value.status == "invalid_file"

def test_download_one_reports_403(tmp_path):
    from fengge.config import load_settings
    s = load_settings(root=tmp_path, env={})
    def runner(cmd, **kw):
        return type("R", (), {"returncode": 1, "stdout": "",
                              "stderr": "ERROR: HTTP Error 403: Forbidden"})()
    with pytest.raises(DownloadError) as e:
        download_one(meta(), s, runner=runner, sleeper=lambda _: None)
    assert e.value.status == "forbidden"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_download.py -v`
Expected: 7 failed

- [ ] **Step 3: 实现**

`DownloadError(Exception)` 带 `status`（`"forbidden" | "invalid_file" | "other"`）和 `stderr`。

`build_download_cmd`：有 `browser` 时带 `--cookies-from-browser <browser>`；
否则有 `cookie` 时带 `--add-header "Cookie:<cookie>"`。其余：
`["yt-dlp","-f","bv*[height<=1080]+ba/b","--merge-output-format","mp4",
  "--no-playlist","--retries","3","-o", str(out_path.with_suffix(".%(ext)s")), url]`。

`download_one` 流程：先 `find_output`，已存在且 `is_valid_video` 就直接复用（断点续跑）；
否则跑命令，再 `find_output` 校验；`is_valid_video` 失败抛 `invalid_file`；
stderr 含 `403`/`412` 抛 `forbidden`。成功后下载封面（`requests.get`，失败只记警告不抛），
`cover_path` 返回绝对路径字符串。结尾 `sleeper(random.uniform(*settings.download_delay))`。

`is_rate_limited(errors)`：最近 3 条 `status == "forbidden"` 返回 True。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_download.py -v`
Expected: 7 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/download.py tests/test_download.py
git commit -m "feat: 视频与封面下载"
```

---

### Task 5: 720p 归档

**Files:**
- Create: `src/fengge/transcode.py`
- Test: `tests/test_transcode.py`

**Interfaces:**
- Produces:
  - `transcode.build_transcode_cmd(src: Path, dst: Path) -> list[str]`
  - `transcode.probe_duration(path: Path, runner=subprocess.run) -> float`
  - `transcode.verify_archive(src: Path, dst: Path, tol: float = 0.5, prober=probe_duration) -> bool`
  - `transcode.archive(src: Path, dst: Path, runner=subprocess.run, prober=probe_duration) -> bool`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_transcode.py
from pathlib import Path
from fengge.transcode import build_transcode_cmd, verify_archive

def test_cmd_scales_to_720_and_copies_audio():
    cmd = build_transcode_cmd(Path("raw/a.mp4"), Path("clips/a.mp4"))
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    vf = cmd[cmd.index("-vf") + 1]
    assert "720" in vf
    assert "libx264" in cmd and "aac" in cmd
    assert cmd[-1] == "clips/a.mp4"

def test_verify_archive_accepts_within_tolerance(tmp_path, monkeypatch):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x"); b.write_bytes(b"y")
    durs = {a: 30.0, b: 30.4}
    assert verify_archive(a, b, prober=lambda p, **kw: durs[p]) is True

def test_verify_archive_rejects_drift(tmp_path):
    a, b = tmp_path / "a.mp4", tmp_path / "b.mp4"
    a.write_bytes(b"x"); b.write_bytes(b"y")
    durs = {a: 30.0, b: 5.0}
    assert verify_archive(a, b, prober=lambda p, **kw: durs[p]) is False

def test_verify_archive_rejects_missing_dest(tmp_path):
    a = tmp_path / "a.mp4"; a.write_bytes(b"x")
    assert verify_archive(a, tmp_path / "nope.mp4", prober=lambda p, **kw: 30.0) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_transcode.py -v`
Expected: 4 failed

- [ ] **Step 3: 实现**

命令：`["ffmpeg","-y","-i",src,"-vf","scale='if(gte(iw,ih),-2,720)':'if(gte(iw,ih),720,-2)'",
"-c:v","libx264","-crf","26","-preset","veryfast","-c:a","aac","-b:a","96k",dst]`。
`probe_duration` 跑 `ffprobe -v error -show_entries format=duration -of csv=p=0 <path>`，
解析失败返回 `0.0`。`verify_archive`：目标存在且非空、时长差 `<= tol`。
`archive`：跑命令，返回 `verify_archive` 结果，**不删源文件**（删除由 pipeline 在
`archived` 状态写入后才做）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_transcode.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/transcode.py tests/test_transcode.py
git commit -m "feat: 720p 归档转码"
```

---

### Task 6: 抽音频与语音识别

**Files:**
- Create: `src/fengge/asr.py`
- Test: `tests/test_asr.py`

**Interfaces:**
- Produces:
  - `asr.build_extract_audio_cmd(src: Path, dst: Path) -> list[str]`
  - `asr.build_initial_prompt() -> str`
  - `asr.normalize_segments(raw: list[dict], min_chars: int = 2) -> list[dict]`
    每条 `{"start": float, "end": float, "text": str}`，同时清掉幻觉与空串
  - `asr.join_text(segments: list[dict]) -> str`
  - `asr.Transcriber(model_size, compute_type, device="cuda")`，方法 `transcribe(audio: Path) -> dict`
    返回 `{"segments": [...], "text": str, "duration": float, "lang_prob": float}`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_asr.py
from pathlib import Path
from fengge.asr import (build_extract_audio_cmd, normalize_segments, join_text,
                        build_initial_prompt)

def test_extract_audio_cmd_is_16k_mono():
    cmd = build_extract_audio_cmd(Path("a.mp4"), Path("a.flac"))
    assert cmd[0] == "ffmpeg"
    assert "-vn" in cmd
    assert cmd[cmd.index("-ar") + 1] == "16000"
    assert cmd[cmd.index("-ac") + 1] == "1"
    assert cmd[-1] == "a.flac"

def test_initial_prompt_contains_domain_words():
    p = build_initial_prompt()
    for w in ("峰哥", "B友", "连麦", "老哥", "牛马"):
        assert w in p

def test_normalize_drops_short_and_empty():
    raw = [{"start": 0.0, "end": 1.0, "text": "嗯"},
           {"start": 1.0, "end": 2.0, "text": "   "},
           {"start": 2.0, "end": 4.0, "text": "你说得对"}]
    out = normalize_segments(raw)
    assert [s["text"] for s in out] == ["你说得对"]

def test_normalize_collapses_repeated_hallucination():
    raw = [{"start": i, "end": i + 1, "text": "谢谢观看"} for i in range(5)]
    assert normalize_segments(raw) == []

def test_normalize_keeps_two_repeats():
    raw = [{"start": 0, "end": 1, "text": "对"}, {"start": 1, "end": 2, "text": "对"},
           {"start": 2, "end": 3, "text": "我跟你讲"}]
    assert len(normalize_segments(raw)) == 3

def test_join_text_strips_and_joins():
    segs = [{"start": 0, "end": 1, "text": " 你好 "}, {"start": 1, "end": 2, "text": "世界"}]
    assert join_text(segs) == "你好世界"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_asr.py -v`
Expected: 6 failed

- [ ] **Step 3: 实现**

`normalize_segments`：去空白、丢弃 `len(text) < min_chars`；幻觉判定用「同一 text 连续出现
≥3 次」→ 该 run 整段丢弃（对应 Review Focus 第 3 条）。
`build_initial_prompt` 返回包含上述领域词、并把 `嗯/啊/那个` 等口头词列进去的中文串。
`Transcriber.transcribe` 用 `faster_whisper.WhisperModel(model_size, device=device,
compute_type=compute_type)`，调用 `model.transcribe(str(audio), language="zh",
vad_filter=True, condition_on_previous_text=False, initial_prompt=build_initial_prompt())`，
把 `info.language_probability` 写进 `lang_prob`，`info.duration` 写进 `duration`。
构造函数里做一次 GPU 自检：`device="cuda"` 抛异常时降到 `"cpu"` + `compute_type="int8"`
并把实际设备记在 `self.device`（日志里警告）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_asr.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/asr.py tests/test_asr.py
git commit -m "feat: 语音识别封装"
```

---

### Task 7: LLM 结构化

**Files:**
- Create: `src/fengge/structure.py`
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: `asr.normalize_segments` 产出的 segment 形状
- Produces:
  - `structure.QUESTION_TYPES: tuple[str, ...]`（12 项，顺序照抄 spec）
  - `structure.build_messages(title: str, segments: list[dict], duration: float) -> list[dict]`
  - `structure.qa_json_schema() -> dict`
  - `structure.parse_llm_response(content: str) -> list[dict]`（非法 JSON 抛 `ValueError`）
  - `structure.structure_clip(client, model: str, title: str, segments, duration) -> list[dict]`
  - `structure.LLMClient(api_key: str, model: str, base_url: str = "")`，
    方法 `structure(title: str, segments: list[dict], duration: float) -> list[dict]`
    （`Pipeline` 只依赖这个方法的形状，方便测试替换）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_structure.py
import json
import pytest
from fengge.structure import (QUESTION_TYPES, build_messages, qa_json_schema,
                              parse_llm_response)

def test_twelve_controlled_types():
    assert len(QUESTION_TYPES) == 12
    assert QUESTION_TYPES[0] == "职业发展"
    assert QUESTION_TYPES[-1] == "其他"

def test_schema_restricts_question_type_to_enum():
    schema = qa_json_schema()
    item = schema["schema"]["properties"]["items"]["items"]
    assert item["properties"]["question_type"]["enum"] == list(QUESTION_TYPES)
    assert item["properties"]["quality"]["minimum"] == 1
    assert item["properties"]["quality"]["maximum"] == 5

def test_messages_include_timestamps_and_duration():
    segs = [{"start": 2.4, "end": 5.1, "text": "峰哥"}]
    msgs = build_messages("标题", segs, 30.0)
    assert msgs[0]["role"] == "system"
    assert "峰哥" in msgs[1]["content"] and "2.4" in msgs[1]["content"]
    assert "30" in msgs[1]["content"]

def test_parse_response_returns_items():
    body = {"items": [{"question_type": "职业发展"}]}
    assert parse_llm_response(json.dumps(body, ensure_ascii=False))[0]["question_type"] == "职业发展"

def test_parse_response_rejects_bad_json():
    with pytest.raises(ValueError):
        parse_llm_response("不是 json")

def test_parse_response_tolerates_markdown_fence():
    body = {"items": []}
    assert parse_llm_response("```json\n" + json.dumps(body) + "\n```") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_structure.py -v`
Expected: 6 failed

- [ ] **Step 3: 实现**

`build_messages` 的 user 内容逐句渲染成 `[2.4-5.1] 文本`，末尾给出总时长和 JSON 要求。
system 内容要求：判断是否真在回答提问；`abstract_question` 必须去掉人名、脏话、平台名、
具体地名和情绪词，改写成一句可复用的通用问题；一条视频里有多组问答就返回多个 item；
`trim` 的首尾必须落在给定时间戳范围内且不重叠。

`qa_json_schema` 返回 `{"name":"qa_items","schema":{"type":"object","properties":{"items":
{"type":"array","items":{...}}},"required":["items"],"additionalProperties":False}}`，
`item` 为 `required` 全部字段、`additionalProperties: False`、`question_type.enum` 用 `QUESTION_TYPES`。

`structure_clip` 调 `client.chat.completions.create(model=model,
messages=build_messages(...), response_format={"type":"json_schema",
"json_schema": qa_json_schema()}, temperature=0.2)`，返回 `parse_llm_response` 结果；
`items` 为空数组视为正常结果（由 Task 8 拒收）。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_structure.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/structure.py tests/test_structure.py
git commit -m "feat: LLM 结构化抽取"
```

---

### Task 8: 过滤与去重

**Files:**
- Create: `src/fengge/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Consumes: `structure.QUESTION_TYPES`
- Produces:
  - `filter.REJECT_REASONS: tuple[str, ...]` = `("too_short_transcript","too_short_video","low_lang_prob","no_qa","not_qa","low_quality","no_abstract","long_low_quality","duplicate")`
  - `filter.filter_video(text: str, duration: float, lang_prob: float) -> str | None`
  - `filter.filter_item(item: dict, duration: float) -> str | None`
  - `filter.dedupe(records: list[dict], embed, threshold: float = 0.92) -> tuple[list[dict], list[dict]]`
  - `filter.cosine(a: list[float], b: list[float]) -> float`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_filter.py
import pytest
from fengge.filter import filter_video, filter_item, dedupe, cosine

def good_item(**kw):
    base = {"is_qa": True, "question_verbatim": "峰哥我该考研吗",
            "abstract_question": "要不要继续读研", "question_type": "学历与教育",
            "answer_summary": "x", "quality": 4}
    base.update(kw)
    return base

def test_filter_video_rules():
    assert filter_video("太短", 30.0, 0.9) == "too_short_transcript"
    assert filter_video("这是一段足够长的转写文本内容", 10.0, 0.9) == "too_short_video"
    assert filter_video("这是一段足够长的转写文本内容", 30.0, 0.3) == "low_lang_prob"
    assert filter_video("这是一段足够长的转写文本内容", 30.0, 0.9) is None

def test_filter_item_rejects_non_qa():
    assert filter_item(good_item(is_qa=False), 30.0) == "not_qa"

def test_filter_item_rejects_low_quality():
    assert filter_item(good_item(quality=2), 30.0) == "low_quality"

def test_filter_item_rejects_same_as_verbatim():
    item = good_item(abstract_question="峰哥我该考研吗")
    assert filter_item(item, 30.0) == "no_abstract"

def test_filter_item_rejects_long_video_below_4():
    assert filter_item(good_item(quality=3), 400.0) == "long_low_quality"
    assert filter_item(good_item(quality=4), 400.0) is None

def test_filter_item_passes():
    assert filter_item(good_item(), 30.0) is None

def test_cosine_basic():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)

def test_dedupe_keeps_higher_quality():
    recs = [{"id": "a", "abstract_question": "要不要读研", "quality": 3},
            {"id": "b", "abstract_question": "该不该考研", "quality": 5},
            {"id": "c", "abstract_question": "怎么找对象", "quality": 4}]
    vecs = {"要不要读研": [1.0, 0.0], "该不该考研": [0.99, 0.14], "怎么找对象": [0.0, 1.0]}
    kept, dropped = dedupe(recs, embed=lambda texts: [vecs[t] for t in texts])
    assert [r["id"] for r in kept] == ["b", "c"]
    assert dropped[0]["id"] == "a"
    assert dropped[0]["reject_reason"] == "duplicate"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_filter.py -v`
Expected: 8 failed

- [ ] **Step 3: 实现**

规则顺序照测试：`too_short_transcript`（`len(text) < 30`）→ `too_short_video`（`duration < 15`）
→ `low_lang_prob`（`< 0.6`）→ None。
`filter_item`：`not_qa` → `low_quality`（`quality < 3`）→ `no_abstract`（空或与
`question_verbatim` 完全相同）→ `long_low_quality`（`duration > 300 and quality < 4`）→ None。
`dedupe` 先批量 embedding，再贪心：按 `quality DESC` 排序，与已保留项比较，
`cosine > threshold` 的丢进 dropped（`reject_reason="duplicate"`，附 `duplicate_of`）。
`cosine` 用纯 Python 实现，零向量返回 0.0。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_filter.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/filter.py tests/test_filter.py
git commit -m "feat: 过滤与去重"
```

---

### Task 9: 数据集导出

**Files:**
- Create: `src/fengge/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `models.ClipMeta`、segment 形状
- Produces:
  - `export.trim_segments(segments: list[dict], start: float, end: float) -> list[dict]`
  - `export.to_record(bvid: str, meta: ClipMeta, item: dict, segments: list[dict], index: int) -> dict`
  - `export.write_jsonl(path: Path, rows: list[dict]) -> int`
  - `export.build_report(records, rejected, counts) -> str`
  - `export.write_review_sample(records, path: Path, n: int = 50, seed: int = 42) -> int`
    （固定随机种子抽样，产出人工抽检用的 CSV，对应 spec §5.11）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_export.py
import json
from fengge.export import (trim_segments, to_record, write_jsonl, build_report,
                           write_review_sample)
from fengge.models import ClipMeta

SEGS = [{"start": 0.0, "end": 2.0, "text": "开场"},
        {"start": 2.0, "end": 5.0, "text": "峰哥我该考研吗"},
        {"start": 5.0, "end": 9.0, "text": "你得先看专业"},
        {"start": 9.0, "end": 12.0, "text": "结尾"}]

def meta():
    return ClipMeta("BV1", 1, "标题", 30.0, 1793862075, "u")

def item(quality=4):
    return {"is_qa": True, "question_verbatim": "峰哥我该考研吗",
            "abstract_question": "要不要继续读研", "question_type": "学历与教育",
            "answer_summary": "看专业", "key_claims": ["看专业"], "quote": "先看专业",
            "tags": ["考研"], "emotion": "劝退", "quality": quality,
            "trim": {"start": 2.0, "end": 9.0}}

def test_trim_segments_keeps_overlap_only():
    out = trim_segments(SEGS, 2.0, 9.0)
    assert [s["text"] for s in out] == ["峰哥我该考研吗", "你得先看专业"]

def test_to_record_id_has_page_suffix():
    r = to_record("BV1", meta(), item(), SEGS, 1)
    assert r["id"] == "BV1_p1"
    assert r["source_bvid"] == "BV1"
    assert r["source_url"].endswith("BV1")
    assert r["clip_path"].endswith("BV1.mp4")
    assert r["transcript"] == "峰哥我该考研吗你得先看专业"

def test_to_record_page_two():
    r = to_record("BV1", meta(), item(), SEGS, 2)
    assert r["id"] == "BV1_p2"

def test_write_jsonl_is_utf8_and_counts(tmp_path):
    p = tmp_path / "clips.jsonl"
    assert write_jsonl(p, [{"a": "峰哥"}]) == 1
    raw = p.read_text(encoding="utf-8")
    assert "峰哥" in raw and "\\u5cf0" not in raw
    assert json.loads(raw.strip())["a"] == "峰哥"

def test_report_mentions_counts_and_reasons():
    recs = [{"id": "a"}, {"id": "b"}]
    rejected = [{"reject_reason": "no_qa"}, {"reject_reason": "no_qa"},
                {"reject_reason": "duplicate"}]
    text = build_report(recs, rejected, {"discovered": 3, "accepted": 1})
    assert "2" in text and "no_qa" in text and "discovered" in text

def test_write_review_sample_is_deterministic_and_capped(tmp_path):
    recs = [{"id": f"BV{i}_p1", "title": "t", "abstract_question": "q",
             "trim": {"start": 0.0, "end": 1.0}, "source_url": "u"} for i in range(100)]
    p = tmp_path / "review_sample.csv"
    assert write_review_sample(recs, p, n=10) == 10
    first = p.read_text(encoding="utf-8")
    assert len(first.strip().splitlines()) == 11
    write_review_sample(recs, p, n=10)
    assert p.read_text(encoding="utf-8") == first
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_export.py -v`
Expected: 6 failed

- [ ] **Step 3: 实现**

`trim_segments` 保留与 `[start, end]` 有交集的句子（`s["end"] > start and s["start"] < end`），
并把首句 `start` 与末句 `end` 收拢到 `trim` 边界。
`to_record` 字段顺序照 spec §5.9；`pubdate` 转 `YYYY-MM-DD`（`datetime.fromtimestamp`）；
`clip_path` / `cover_path` 用相对 `root` 的 posix 路径字符串。
`build_report` 输出 markdown：总数、状态分布表、拒绝原因分布表（按次数降序）、
数据集中位时长、话题分布、磁盘占用（`shutil.disk_usage`）。
`write_review_sample` 用 `random.Random(seed).sample(records, min(n, len(records)))`，
用 `csv.DictWriter` 写列 `id,title,abstract_question,trim_start,trim_end,source_url,verdict`，
`verdict` 留空给人工填 `pass/fail`。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_export.py -v`
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/export.py tests/test_export.py
git commit -m "feat: 数据集导出"
```

---

### Task 10: 流水线编排与命令行

**Files:**
- Create: `src/fengge/pipeline.py`, `src/fengge/cli.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: 前九个任务的全部接口
- Produces:
  - `pipeline.RateLimited(Exception)`
  - `pipeline.Pipeline(settings, db=None, transcriber=None, llm=None)`，方法
    `run(stage: str, limit: int | None = None) -> dict`，`stage ∈ {"download","asr","structure","archive"}`
  - `pipeline.Pipeline.run_all(limit: int | None = None) -> dict`
  - `cli.main(argv: list[str]) -> int`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_pipeline.py
import json
import pytest
from fengge.db import Database
from fengge.models import ClipMeta
from fengge.pipeline import Pipeline, RateLimited

ASR_BODY = {"segments": [{"start": 0.0, "end": 3.0, "text": "峰哥我该考研吗"}],
            "text": "峰哥我该考研吗", "duration": 30.0, "lang_prob": 0.99}

class FakeTranscriber:
    device = "cpu"
    def transcribe(self, audio):
        return ASR_BODY

class FakeLLM:
    def structure(self, title, segments, duration):
        return [{"is_qa": True, "question_verbatim": "峰哥我该考研吗",
                 "abstract_question": "要不要继续读研", "question_type": "学历与教育",
                 "answer_summary": "看专业", "key_claims": [], "quote": "",
                 "tags": [], "emotion": "劝退", "quality": 4,
                 "trim": {"start": 0.0, "end": 3.0}}]

@pytest.fixture
def pipe(tmp_path):
    from fengge.config import load_settings
    s = load_settings(root=tmp_path, env={})
    db = Database(s.db_path); db.init_schema()
    db.upsert_clip(ClipMeta("BV1", 1, "t", 30.0, 100, ""))
    return Pipeline(s, db=db, transcriber=FakeTranscriber(), llm=FakeLLM()), db

def write_asr(settings, bvid="BV1"):
    settings.asr_dir.mkdir(parents=True, exist_ok=True)
    (settings.asr_dir / f"{bvid}.json").write_text(
        json.dumps(ASR_BODY, ensure_ascii=False), encoding="utf-8")

def test_structure_stage_moves_state_and_writes_file(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state("BV1", "asr_done", asr_chars=100)
    p.run("structure", limit=10)
    assert db.get("BV1")["state"] in ("accepted", "rejected")
    assert (p.settings.structured_dir / "BV1.json").exists()

def test_structure_stage_skips_already_done(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state("BV1", "accepted")
    before = db.get("BV1")["updated_at"]
    p.run("structure", limit=10)
    assert db.get("BV1")["updated_at"] == before

def test_failure_increments_attempts(pipe):
    p, db = pipe
    write_asr(p.settings)
    db.set_state("BV1", "asr_done")
    def boom(*a, **kw): raise RuntimeError("llm down")
    p.llm.structure = boom
    p.run("structure", limit=1)
    assert db.get("BV1")["attempts"] == 1
    assert db.get("BV1")["state"] == "asr_done"

def test_rate_limit_stops_batch(pipe):
    p, db = pipe
    for i, bv in enumerate(["BV2", "BV3"]):
        db.upsert_clip(ClipMeta(bv, i + 2, "t", 30.0, 100 + i, ""))
    from fengge.download import DownloadError
    p._download_one = lambda meta: (_ for _ in ()).throw(DownloadError("403", status="forbidden"))
    with pytest.raises(RateLimited):
        p.run("download", limit=5)
    for bv in ["BV1", "BV2", "BV3"]:
        assert db.get(bv)["state"] == "discovered"
        assert db.get(bv)["attempts"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 4 failed

- [ ] **Step 3: 实现**

`Pipeline` 里每个 stage 是一个循环：`db.next_batch(state, limit)` → 逐条处理 → 成功
`db.set_state(...)` / 失败 `db.fail(...)`。异常**不中断整批**（除 `RateLimited`），
继续下一条，最后返回 `{"processed": n, "failed": m}`。

构造函数把下载包成 `self._download_one(meta) -> dict` 这一个可替换的方法（内部转调
`download.download_one`），测试直接替换它。`transcriber` / `llm` 缺省时才按
`settings` 构造真家伙，这样单元测试永远不碰网络和 GPU。

`download` stage：`DownloadError(status="forbidden")` 连续 3 次 → 抛 `RateLimited`（Review Focus 第 5 条）。
`asr` stage：源文件不存在时直接 `db.fail`。
`structure` stage：读 `asr/<bvid>.json`，跑 `llm.structure`，把结果写 `structured/<bvid>.json`，
再逐条 `filter_item`，有通过的就 `accepted`、否则 `rejected`。
`archive` stage：`transcode.archive` 成功才 `set_state("archived")` 并删除 `raw/`、`audio/` 文件。

`cli.py` 子命令：`discover | download | asr | structure | archive | export | verify | run | check`，
`--limit` 可选；`run` 依次跑四个 stage，`--limit 300` 用于试点批次。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/pipeline.py src/fengge/cli.py tests/test_pipeline.py
git commit -m "feat: 流水线编排与命令行"
```

---

### Task 11: 检索小验证

**Files:**
- Create: `src/fengge/verify.py`
- Create: `docs/superpowers/specs/2026-11-17-verify-queries.md`
- Test: `tests/test_verify.py`

**Interfaces:**
- Produces:
  - `verify.top_k(query: list[float], docs: list[list[float]], k: int = 3) -> list[tuple[int, float]]`
  - `verify.no_answer(top1: float, threshold: float) -> bool`
  - `verify.load_queries(path: Path) -> list[dict]`（`{"query": str, "has_answer": bool}`）
  - `verify.evaluate(queries, records, embed, threshold, k=3) -> dict`

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_verify.py
import pytest
from fengge.verify import top_k, no_answer, evaluate

DOCS = [[1.0, 0.0], [0.0, 1.0], [0.7, 0.7]]

def test_top_k_sorted_desc():
    got = top_k([1.0, 0.0], DOCS, k=2)
    assert [i for i, _ in got] == [0, 2]
    assert got[0][1] == pytest.approx(1.0)

def test_no_answer_uses_threshold():
    assert no_answer(0.55, 0.62) is True
    assert no_answer(0.70, 0.62) is False

def test_evaluate_counts_hits_and_edge_signals():
    queries = [{"query": "要不要读研", "has_answer": True},
               {"query": "怎么造火箭", "has_answer": False}]
    records = [{"id": "a", "abstract_question": "要不要考研", "quality": 4},
               {"id": "b", "abstract_question": "怎么找对象", "quality": 3}]
    vecs = {"要不要读研": [1.0, 0.0], "怎么造火箭": [0.0, 1.0],
            "要不要考研": [1.0, 0.0], "怎么找对象": [0.1, 1.0]}
    res = evaluate(queries, records, embed=lambda ts: [vecs[t] for t in ts], threshold=0.9)
    assert res["answerable_hits"] == 1
    assert res["edge_no_answer"] == 1
    assert res["passed"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_verify.py -v`
Expected: 3 failed

- [ ] **Step 3: 实现**

`top_k` 用 `filter.cosine` 排序取前 k，返回 `(doc_index, score)`。
`evaluate` 对 `has_answer=True` 的题统计 top-k 是否命中（`score >= threshold` 且 doc 存在），
对 `has_answer=False` 的题统计是否触发 `no_answer`；通过线是 spec §5.10 的
`answerable_hits / n_has_answer >= 0.8` 且 `edge_no_answer / n_edge >= 0.6`。

`build_queries_file()` 生成 20 条题（10 有对应、10 边缘），**写死在文件里**，
运行 `verify` 之前就已存在，不允许看数据集后改题（spec §5.10）。
阈值取 `settings.verify_threshold`（默认 0.62），该值在另一份 30 对 dev 集上校准后冻结；
校准过程写进 `docs/superpowers/specs/2026-11-17-verify-queries.md` 的「阈值来源」一节，
运行期不得用这 20 条测试题反调阈值。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_verify.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/fengge/verify.py tests/test_verify.py docs/superpowers/specs/2026-11-17-verify-queries.md
git commit -m "feat: 检索验证"
```

---

### Task 12: 环境自检与试跑

**Files:**
- Create: `src/fengge/envcheck.py`
- Create: `README.md`
- Test: `tests/test_envcheck.py`

**Interfaces:**
- Produces:
  - `envcheck.check_ffmpeg(runner=subprocess.run) -> tuple[bool, str]`
  - `envcheck.check_ytdlp(runner=subprocess.run) -> tuple[bool, str]`
  - `envcheck.check_gpu() -> tuple[bool, str]`（把 cuDNN/cuBLAS 的可见性和实际能建模型一起判）
  - `envcheck.run_all() -> list[dict]`（每项 `{"name","ok","detail"}`）

- [ ] **Step 1: 写失败的测试**

```python
# tests/test_envcheck.py
from fengge.envcheck import check_ffmpeg, check_ytdlp, run_all

def test_check_ffmpeg_ok():
    r = lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "ffmpeg version 7", "stderr": ""})()
    ok, detail = check_ffmpeg(runner=r)
    assert ok is True and "7" in detail

def test_check_ffmpeg_missing():
    def r(cmd, **kw): raise FileNotFoundError()
    ok, detail = check_ffmpeg(runner=r)
    assert ok is False and "ffmpeg" in detail

def test_check_ytdlp_missing():
    def r(cmd, **kw):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "not found"})()
    ok, _ = check_ytdlp(runner=r)
    assert ok is False

def test_run_all_returns_named_items(monkeypatch):
    import fengge.envcheck as ec
    monkeypatch.setattr(ec, "check_ffmpeg", lambda **kw: (True, "ok"))
    monkeypatch.setattr(ec, "check_ytdlp", lambda **kw: (True, "ok"))
    monkeypatch.setattr(ec, "check_gpu", lambda: (False, "cpu fallback"))
    items = ec.run_all()
    assert {i["name"] for i in items} == {"ffmpeg", "yt-dlp", "gpu"}
    assert next(i for i in items if i["name"] == "gpu")["ok"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_envcheck.py -v`
Expected: 4 failed

- [ ] **Step 3: 实现**

三个 `check_*` 都返回 `(ok, detail)`，异常一律转成 `(False, 原因)`。
`check_gpu` 实际尝试 `faster_whisper.WhisperModel("tiny", device="cuda", compute_type="int8_float16")`
的构造，失败再试 `device="cpu"`，并把结论写成一句可读的说明（这台机器很可能落到 cpu）。
`run_all` 汇总。

`README.md` 写：安装命令（含 `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` 和
ffmpeg 安装说明）、`python -m fengge.cli check`、`python -m fengge.cli discover`、
`python -m fengge.cli run --limit 300` 的完整顺序、以及「先试点 300 条再全量」的说明。

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/test_envcheck.py -v`
Expected: 4 passed

- [ ] **Step 5: 全量测试与提交**

Run: `python -m pytest -q`
Expected: 全部 passed

```bash
git add src/fengge/envcheck.py tests/test_envcheck.py README.md
git commit -m "feat: 环境自检与使用说明"
```

---

## 执行顺序

1. Task 1~2（骨架 + 状态机）—— 没有数据库什么都推不动
2. Task 3~11 —— 十二条独立命令，按表格顺序
3. Task 12 —— 自检 + 文档
4. 之后才跑真实数据：`check` → `discover` → `run --limit 300` → 人工抽检 50 条 →
   通过则 `run` 全量 → `export` → `verify`
