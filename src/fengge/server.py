from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings, load_settings
from .retrieval import rrf_fuse

try:  # 和 cli 一致：命令行/服务启动时都先读 .env
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:  # pragma: no cover
    pass

WEB_DIR = Path(__file__).resolve().parents[2] / "web"


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    va, vb = list(a), list(b)
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def index_text(record: dict[str, Any]) -> str:
    parts = [
        record.get("abstract_question") or "",
        " ".join(record.get("tags") or []),
        record.get("question_verbatim") or "",
        record.get("answer_summary") or "",
        record.get("question_type") or "",
    ]
    return " ".join(p for p in parts if p)


@dataclass
class Hit:
    record: dict[str, Any]
    score: float


class Index:
    def __init__(
        self,
        records: list[dict[str, Any]],
        vectors: list[list[float]],
        embed: Callable[[list[str]], list[list[float]]],
        threshold: float = 0.62,
    ):
        self.records = records
        self.vectors = vectors
        self.embed = embed
        self.threshold = threshold
        self.abstractor: Callable[[str], str] | None = None
        self.reranker: Callable[[str, list[Hit]], dict[str, Any] | None] | None = None
        self._bm25: Any = None
        self._by_bvid: dict[str, dict[str, Any]] = {}
        for r in records:
            self._by_bvid.setdefault(r.get("source_bvid") or "", r)

    @classmethod
    def build(
        cls,
        records: list[dict[str, Any]],
        embed: Callable[[list[str]], list[list[float]]],
        threshold: float = 0.62,
    ) -> "Index":
        vectors = embed([index_text(r) for r in records]) if records else []
        return cls(records, vectors, embed, threshold)

    def search(self, question: str, k: int = 3) -> list[Hit]:
        return self.search_multi([question], k)

    def _vector_ranking(self, texts: list[str], k: int = 50) -> list[tuple[int, float]]:
        if not self.records or not texts:
            return []
        vectors = self.embed(texts)
        scored = [
            (i, max(cosine(q, doc) for q in vectors))
            for i, doc in enumerate(self.vectors)
        ]
        scored.sort(key=lambda pair: -pair[1])
        return scored[:k]

    @property
    def bm25(self) -> Any:
        if self._bm25 is None:
            from .retrieval import BM25

            self._bm25 = BM25([index_text(r) for r in self.records])
        return self._bm25

    def search_multi(self, texts: list[str], k: int = 3) -> list[Hit]:
        vector = self._vector_ranking(texts, max(k, 50))
        if not vector:
            return []
        lexical = self.bm25.search(" ".join(texts), 50)
        fused = rrf_fuse([vector, lexical], size=max(k, 12))
        similarity = dict(vector)
        return [
            Hit(self.records[index], similarity.get(index, 0.0))
            for index, _ in fused[:k]
        ]

    def answer(self, question: str, k: int = 8) -> dict[str, Any]:
        started = time.perf_counter()
        question = (question or "").strip()
        if not question:
            raise ValueError("empty question")

        abstracted = self.abstractor(question) if self.abstractor else question
        if isinstance(abstracted, str):
            variants = [abstracted]
        else:
            variants = list(abstracted or [])
        if question not in variants:
            variants.append(question)
        texts = variants[:4]
        abstracted = texts[0]

        hits = self.search_multi(texts, max(k, 8))
        best = hits[0] if hits else None

        verdict = None
        if self.reranker and hits:
            verdict = self.reranker(question, hits)
        if verdict and verdict.get("verdict") != "no":
            chosen = next(
                (h for h in hits if h.record.get("id") == verdict.get("id")), best
            )
            if chosen is not None:
                hits = [chosen] + [h for h in hits if h is not chosen]
                best = chosen
            found = True
        elif verdict and verdict.get("verdict") == "no":
            found = False
        else:
            found = bool(best and best.score >= self.threshold)

        return {
            "found": found,
            "threshold": self.threshold,
            "abstracted": abstracted,
            "verdict": verdict,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "best": _hit_payload(best) if best else None,
            "results": [_hit_payload(h) for h in hits],
        }

    def topics(self) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in self.records:
            groups.setdefault(record.get("question_type") or "其他", []).append(record)
        ordered = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        return [
            {
                "type": qtype,
                "count": len(items),
                "samples": [i.get("abstract_question") for i in items[:2]],
                "cover": f"/clips/{items[0].get('source_bvid')}.jpg",
            }
            for qtype, items in ordered
        ]

    def topic_items(
        self, qtype: str, limit: int = 24, offset: int = 0
    ) -> dict[str, Any]:
        items = [
            r for r in self.records if (r.get("question_type") or "其他") == qtype
        ]
        items.sort(key=lambda r: (-(r.get("quality") or 0), r.get("id") or ""))
        page = items[offset : offset + limit]
        return {
            "type": qtype,
            "total": len(items),
            "items": [
                {**_hit_payload(Hit(r, 0.0)), "answer": (r.get("answer_summary") or "")[:140]}
                for r in page
            ],
        }


def _hit_payload(hit: Hit) -> dict[str, Any]:
    r = hit.record
    return {
        "id": r.get("id"),
        "score": round(hit.score, 4),
        "question": r.get("abstract_question"),
        "question_verbatim": r.get("question_verbatim"),
        "answer": r.get("answer_summary"),
        "quote": r.get("quote"),
        "key_claims": r.get("key_claims") or [],
        "type": r.get("question_type"),
        "tags": r.get("tags") or [],
        "title": r.get("title"),
        "source_bvid": r.get("source_bvid"),
        "source_aid": r.get("source_aid"),
        "source_url": r.get("source_url"),
        "clip_url": f"/clips/{r.get('source_bvid')}.mp4",
        "cover_url": f"/clips/{r.get('source_bvid')}.jpg",
        "trim": r.get("trim") or {},
        "segments": (r.get("segments") or [])[:40],
        "transcript": (r.get("transcript") or "")[:400],
    }


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def build_index(settings: Settings) -> Index:
    from .embed import get_embedder
    from .query import expand_query, rerank
    from .structure import LLMClient

    records = load_records(settings.dataset_dir / "clips.jsonl")
    index = Index.build(records, get_embedder(settings), settings.verify_threshold)

    if settings.openai_api_key:
        llm = LLMClient(
            settings.openai_api_key,
            settings.llm_model,
            settings.openai_base_url,
            timeout=25.0,
        )
        cache: dict[str, list[str]] = {}

        def abstract(question: str) -> list[str]:
            if question not in cache:
                cache[question] = expand_query(llm, question)
            return cache[question]

        index.abstractor = abstract
        index.reranker = lambda question, hits: rerank(llm, question, hits)
    return index


class Question(BaseModel):
    question: str


REPLY_URL = "https://api.bilibili.com/x/v2/reply"


def comment_session(settings: Settings):
    import requests

    from .discover import UA, _load_cookie_file

    session = requests.Session()
    session.headers.update(
        {"User-Agent": UA, "Referer": "https://www.bilibili.com/"}
    )
    _load_cookie_file(session, settings.cookie_file)
    return session


def fetch_comments(session, aid: int, ps: int = 20) -> list[dict[str, Any]]:
    if not aid:
        return []
    payload = session.get(
        REPLY_URL,
        params={"type": 1, "oid": aid, "sort": 2, "ps": ps, "pn": 1},
        timeout=15,
    ).json()
    if payload.get("code") != 0:
        return []
    out: list[dict[str, Any]] = []
    for reply in ((payload.get("data") or {}).get("replies") or []):
        message = ((reply.get("content") or {}).get("message") or "").strip()
        if not message:
            continue
        out.append(
            {
                "user": ((reply.get("member") or {}).get("uname") or ""),
                "content": message,
                "like": int(reply.get("like") or 0),
                "ctime": int(reply.get("ctime") or 0),
            }
        )
    out.sort(key=lambda c: -c["like"])
    return out


class CommentStore:
    def __init__(
        self,
        directory: Path,
        session=None,
        fetcher=fetch_comments,
        session_factory=None,
    ):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.session = session
        self.fetcher = fetcher
        self.session_factory = session_factory

    def get(self, bvid: str, aid: int) -> tuple[list[dict[str, Any]], bool]:
        path = self.directory / f"{bvid}.json"
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8")), True
            except (OSError, json.JSONDecodeError):
                pass
        if not aid:
            return [], False
        if self.session is None and self.session_factory is not None:
            self.session = self.session_factory()
        try:
            comments = self.fetcher(self.session, aid)
        except Exception:  # noqa: BLE001
            return [], False
        if comments:
            path.write_text(
                json.dumps(comments, ensure_ascii=False), encoding="utf-8"
            )
        return comments, False


def create_app(index: Index | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    app = FastAPI(title="峰哥问答机")
    state: dict[str, Index | None] = {"index": index}
    lock = threading.Lock()

    def get_index() -> Index:
        if state["index"] is None:
            with lock:
                if state["index"] is None:
                    state["index"] = build_index(settings)
        return state["index"]  # type: ignore[return-value]

    @app.on_event("startup")
    def warmup() -> None:
        # 首次构建索引要加载 embedding 模型（约 20 秒），放到启动时做，
        # 否则第一个提问会卡在那里，并发请求还会重复加载。
        try:
            get_index()
        except Exception:  # noqa: BLE001
            pass

    @app.post("/api/ask")
    def ask(payload: Question) -> dict[str, Any]:
        try:
            return get_index().answer(payload.question)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        idx = get_index()
        return {
            "records": len(idx.records),
            "threshold": idx.threshold,
            "clips": sum(
                1 for r in idx.records if (settings.clips_dir / f"{r['source_bvid']}.mp4").is_file()
            ),
        }

    @app.get("/api/topics")
    def topics() -> dict[str, Any]:
        return {"topics": get_index().topics()}

    @app.get("/api/topics/{qtype}")
    def topic(qtype: str, limit: int = 24, offset: int = 0) -> dict[str, Any]:
        return get_index().topic_items(qtype, limit=limit, offset=offset)

    @app.get("/api/live2d/models")
    def live2d_models() -> dict[str, Any]:
        """扫描 web/vendor/live2d/models/ 下的模型，前端据此生成切换列表。"""
        root = Path(settings.root) / "web" / "vendor" / "live2d" / "models"
        web_root = Path(settings.root) / "web"
        models: list[dict[str, str]] = []
        if root.is_dir():
            for directory in sorted(p for p in root.iterdir() if p.is_dir()):
                candidates = sorted(directory.rglob("*.model3.json")) + sorted(
                    directory.rglob("*.model.json")
                )
                if not candidates:
                    continue
                models.append(
                    {
                        "name": directory.name,
                        "json": "/" + candidates[0].relative_to(web_root).as_posix(),
                    }
                )
        return {"models": models}

    store = CommentStore(
        Path(settings.data_dir) / "comments",
        session_factory=lambda: comment_session(settings),
    )

    @app.get("/api/comments/{bvid}")
    def comments(bvid: str) -> dict[str, Any]:
        idx = get_index()
        record = idx._by_bvid.get(bvid) or {}
        aid = int(record.get("source_aid") or 0)
        data, cached = store.get(bvid, aid)
        return {
            "bvid": bvid,
            "cached": cached,
            "count": len(data),
            "comments": data[:20],
        }

    clips_dir = Path(settings.clips_dir)
    if clips_dir.is_dir():
        app.mount("/clips", StaticFiles(directory=str(clips_dir)), name="clips")

    if WEB_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
